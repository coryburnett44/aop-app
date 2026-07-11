"""Iter 123 — Admin-configurable per-role hours behavior.

Locks in:
  1. GET /api/hours/role-config returns the effective per-role map.
  2. Only Full Access admins can PUT the config.
  3. Overriding a role's `can_manage_others` flips the runtime permission
     enforced by `POST /hours/admin` (verified via Governor Manager
     round-trip: initial 403 → grant → allowed → revoke → 403).
  4. Adding a brand-new role key works (persisted with sensible defaults).
"""
from __future__ import annotations

import os
import sys
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


def test_role_config_returns_all_known_roles():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/hours/role-config", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    roles = {it["role"] for it in data["items"]}
    for expected in ("full", "operations_manager", "governor_manager", "membership_manager"):
        assert expected in roles, f"missing role {expected} in payload"
    for it in data["items"]:
        for k in ("role", "label", "can_manage_others", "default_mode"):
            assert k in it, f"item missing {k}: {it}"
    assert data["defaults"] == {"can_manage_others": False, "default_mode": "for_myself"}


def test_role_config_write_is_full_admin_only():
    """Only Full Access can PUT — other admin roles are rejected."""
    gov = _login("governor.tx@clubhaven.app", "Governor123!")
    r = gov.put(f"{BASE}/hours/role-config", json={
        "roles": {"governor_manager": {"can_manage_others": True}}
    }, timeout=15)
    assert r.status_code == 403


def test_role_config_override_flips_runtime_permission():
    """End-to-end: flipping `can_manage_others` for Governor Manager should
    open / close the `POST /hours/admin` gate without a code change."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    gov = _login("governor.tx@clubhaven.app", "Governor123!")

    me = gov.get(f"{BASE}/auth/me", timeout=15).json()
    gov_id = me["id"]
    gov_chapter = me.get("chapter_id")
    peer = next(
        (m for m in gov.get(f"{BASE}/members", timeout=15).json()
         if m["id"] != gov_id and m.get("chapter_id") == gov_chapter),
        None,
    )
    if peer is None:
        import pytest as _pytest
        _pytest.skip("no chapter peer available for Governor in this env")

    payload = {
        "user_id": peer["id"], "hours": 0.1, "date": "2026-07-11T00:00:00",
        "event_type": "other", "agency_name": "iter123", "activity": "iter123 test",
        "host_name": "h", "host_email": "h@x.com", "host_phone": "555-1234",
    }

    # Ensure baseline: gov = can_manage_others False (default).
    admin.put(f"{BASE}/hours/role-config", json={"roles": {"governor_manager": None}}, timeout=15)

    # 1) Baseline → 403.
    r = gov.post(f"{BASE}/hours/admin", json=payload, timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code}"

    # 2) Grant → success.
    r = admin.put(f"{BASE}/hours/role-config", json={
        "roles": {"governor_manager": {"can_manage_others": True}}
    }, timeout=15)
    assert r.status_code == 200
    r = gov.post(f"{BASE}/hours/admin", json=payload, timeout=15)
    assert r.status_code == 200, f"expected 200 after grant, got {r.status_code} · {r.text}"
    assert r.json()["user_id"] == peer["id"]

    # 3) Revoke → 403 again.
    r = admin.put(f"{BASE}/hours/role-config", json={
        "roles": {"governor_manager": None}
    }, timeout=15)
    assert r.status_code == 200
    r = gov.post(f"{BASE}/hours/admin", json=payload, timeout=15)
    assert r.status_code == 403


def test_role_config_add_unknown_role_key():
    """Adding a brand-new role key should persist and appear in the GET
    payload — no code change required for a new sub-role."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.put(f"{BASE}/hours/role-config", json={
        "roles": {"iter123_treasurer": {"can_manage_others": False, "default_mode": "for_myself"}}
    }, timeout=15)
    assert r.status_code == 200
    items = {it["role"]: it for it in r.json()["items"]}
    assert "iter123_treasurer" in items, "new role should surface in GET"
    assert items["iter123_treasurer"]["label"] == "Iter123 Treasurer"  # auto Title Case
    assert items["iter123_treasurer"]["can_manage_others"] is False
    # Cleanup — remove the role.
    admin.put(f"{BASE}/hours/role-config", json={"roles": {"iter123_treasurer": None}}, timeout=15)


def test_role_config_rejects_invalid_default_mode():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.put(f"{BASE}/hours/role-config", json={
        "roles": {"governor_manager": {"default_mode": "bogus"}}
    }, timeout=15)
    assert r.status_code == 400


def test_role_config_read_is_available_to_any_authenticated_user():
    """The frontend uses this endpoint to decide whether to render the
    Log Hours toggle for the current user. Any authenticated user must be
    able to read it (even a plain member)."""
    member = _login("member@clubhaven.app", "Member123!")
    r = member.get(f"{BASE}/hours/role-config", timeout=15)
    assert r.status_code == 200
    assert "items" in r.json()
