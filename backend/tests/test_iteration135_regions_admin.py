"""Iter 135 — Region CRUD + governor + member override tests."""
from __future__ import annotations

import io
import os
import sys
import uuid
from pathlib import Path

import requests

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


def _pick_member(admin, email: str = "member@clubhaven.app"):
    members = admin.get(f"{BASE}/members?limit=100", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    return next(m for m in members if m.get("email") == email)


def test_governor_assignment_flows_to_public_regions_endpoint():
    admin = _login("admin@clubhaven.app", "Admin123!")
    riley = _pick_member(admin)
    try:
        r = admin.put(f"{BASE}/admin/regions/gulf-coast", json={"governor_user_id": riley["id"]}, timeout=15)
        assert r.status_code == 200, r.text
        body = admin.get(f"{BASE}/regions", timeout=15).json()
        gc = next(x for x in body["regions"] if x["id"] == "gulf-coast")
        assert gc["governor_user_id"] == riley["id"]
        assert gc["governor"] is not None
        assert gc["governor"]["id"] == riley["id"]
    finally:
        admin.put(f"{BASE}/admin/regions/gulf-coast", json={"governor_user_id": ""}, timeout=15)


def test_member_override_moves_them_between_regions():
    admin = _login("admin@clubhaven.app", "Admin123!")
    members = admin.get(f"{BASE}/members?limit=100", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    # Pick a member with an existing region-mappable state (any Gulf Coast).
    victim = next((m for m in members if (m.get("state") or "").upper() in {"TX", "TEXAS", "LA", "AR", "OK", "MS"}), None)
    assert victim is not None
    baseline_body = admin.get(f"{BASE}/regions", timeout=15).json()
    baseline = {r["id"]: r["total"] for r in baseline_body["regions"]}
    try:
        # Move victim into Mid-Atlantic.
        r = admin.put(f"{BASE}/admin/members/{victim['id']}/region", json={"region_id": "mid-atlantic"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["region_override"] == "mid-atlantic"
        moved_body = admin.get(f"{BASE}/regions", timeout=15).json()
        moved = {r["id"]: r["total"] for r in moved_body["regions"]}
        assert moved["mid-atlantic"] == baseline["mid-atlantic"] + 1
        assert moved["gulf-coast"] == baseline["gulf-coast"] - 1
    finally:
        admin.put(f"{BASE}/admin/members/{victim['id']}/region", json={"region_id": ""}, timeout=15)


def test_region_crud_lifecycle():
    admin = _login("admin@clubhaven.app", "Admin123!")
    tag = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Test Region {tag}",
        "description": f"Regression test region {tag}",
        "emoji": "🧪",
        "color": "#123456",
        "order": 999,
        "states": [{"code": "CA", "name": "California"}],
    }
    created = admin.post(f"{BASE}/admin/regions", json=payload, timeout=45).json()
    rid = created["id"]
    try:
        assert rid.startswith(f"test-region-{tag.lower()}") or "test-region" in rid.lower()
        assert created["emoji"] == "🧪"
        assert any(s["code"] == "CA" for s in created["states"])
        # Update.
        r = admin.put(f"{BASE}/admin/regions/{rid}", json={"description": "updated"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["description"] == "updated"
        # Should show up in the public listing.
        body = admin.get(f"{BASE}/regions", timeout=15).json()
        assert any(x["id"] == rid for x in body["regions"])
    finally:
        del_r = admin.delete(f"{BASE}/admin/regions/{rid}", timeout=15)
        assert del_r.status_code == 200
        # Ensure it's gone.
        body = admin.get(f"{BASE}/regions", timeout=15).json()
        assert not any(x["id"] == rid for x in body["regions"])


def test_region_state_scoped_members_endpoint():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/regions/gulf-coast/members", timeout=15).json()
    assert r["region_id"] == "gulf-coast"
    assert r["count"] >= 1
    # Filter to TX specifically.
    r_tx = admin.get(f"{BASE}/regions/gulf-coast/members?state_code=TX", timeout=15).json()
    assert r_tx["state_code"] == "TX"
    # Every returned member should have TX (or Texas) as their state OR
    # be manually overridden into gulf-coast — but the endpoint filters
    # further to state_code=TX so state must be Texas variant.
    for m in r_tx["members"]:
        state_norm = (m.get("state") or "").strip().lower()
        # Allow either a Texas variant OR (a manual override AND state=tx)
        assert state_norm in {"texas", "tx", "tex."}, f"Unexpected state {state_norm!r}"


def test_governor_endpoint_400_on_unknown_user():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.put(f"{BASE}/admin/regions/gulf-coast", json={"governor_user_id": "nonexistent-user-id"}, timeout=15)
    assert r.status_code == 400


def test_region_endpoints_require_admin_scope():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.post(f"{BASE}/admin/regions", json={"name": "x"}, timeout=15)
    assert r.status_code == 403
    r = member.put(f"{BASE}/admin/regions/gulf-coast", json={}, timeout=15)
    assert r.status_code == 403
    r = member.delete(f"{BASE}/admin/regions/gulf-coast", timeout=15)
    assert r.status_code == 403
    # But the read endpoint is still accessible to any logged-in member.
    r = member.get(f"{BASE}/regions", timeout=15)
    assert r.status_code == 200


def test_delete_region_clears_member_overrides_pointing_to_it():
    admin = _login("admin@clubhaven.app", "Admin123!")
    tag = uuid.uuid4().hex[:8]
    created = admin.post(f"{BASE}/admin/regions", json={
        "name": f"Ephemeral {tag}", "description": "", "emoji": "💥",
        "color": "#0A2463", "states": [{"code": "CA", "name": "California"}],
    }, timeout=45).json()
    rid = created["id"]
    victim = _pick_member(admin)
    admin.put(f"{BASE}/admin/members/{victim['id']}/region", json={"region_id": rid}, timeout=15)
    # Delete the region.
    admin.delete(f"{BASE}/admin/regions/{rid}", timeout=15)
    # The member's override should be cleared.
    m = admin.get(f"{BASE}/members/{victim['id']}", timeout=15).json()
    assert (m.get("region_override") or "") == ""
