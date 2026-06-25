"""Iter82 — bulk Quick check-in for families + photos module modularization smoke.

A. Photos routes still work after being extracted from server.py to
   routes/photos.py (smoke-tests the major endpoints).

B. Bulk Quick check-in fires multiple /check-in POSTs sequentially — exercise
   the underlying contract by checking in a member + 2 of their guests in one
   loop, then verifying all three landed on the roster correctly.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "jordan.reed@clubhaven.app", "password": "Demo123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_s():
    return _login(ADMIN)


# ============================================================
# A — Photos routes still reachable after modularization
# ============================================================

def test_photos_module_endpoints_work(admin_s):
    """All photo endpoints registered by routes.photos.register() must respond."""
    r = admin_s.get(f"{API}/photos", timeout=15)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)

    r = admin_s.get(f"{API}/photos/albums", timeout=15)
    assert r.status_code == 200, r.text
    albums = r.json()
    assert isinstance(albums, list) and len(albums) > 0, "no albums returned"
    # Category filter still narrows results.
    r2 = admin_s.get(f"{API}/photos/albums", params={"category": "anniversary"}, timeout=15)
    assert r2.status_code == 200
    for a in r2.json():
        assert a["category"] == "anniversary"


def test_photos_module_create_and_delete_album(admin_s):
    """Round-trip: create custom album, edit category, delete it. Confirms the
    module forwards user identity correctly (admin/creator gating)."""
    name = f"iter82-album-{uuid.uuid4().hex[:6]}"
    r = admin_s.post(f"{API}/photos/albums", json={"name": name, "category": "other"}, timeout=15)
    assert r.status_code == 200, r.text
    aid = r.json()["id"]
    try:
        # Edit category
        r2 = admin_s.put(f"{API}/photos/albums/{aid}", json={"category": "conference"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["category"] == "conference"
    finally:
        r3 = admin_s.delete(f"{API}/photos/albums/{aid}", timeout=15)
        assert r3.status_code == 200


# ============================================================
# B — Quick (family) batched check-in flow
# ============================================================

def _iso_future(days=30, hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


@pytest.fixture
def family_event(admin_s):
    """Create event + RSVP the demo member with 2 guests. Yield (event, member)."""
    members = admin_s.get(f"{API}/members", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    target = next((m for m in members if m.get("email") == MEMBER["email"]), None)
    assert target
    ev = admin_s.post(f"{API}/events", json={
        "title": f"Iter82 Family Quick {uuid.uuid4().hex[:6]}",
        "description": "quick family check-in test",
        "location": "DC",
        "start_at": _iso_future(40),
        "end_at": _iso_future(40, 3),
        "category": "general",
        "capacity": 50,
    }, timeout=15).json()
    admin_s.post(f"{API}/events/{ev['id']}/admin-rsvp", json={
        "user_id": target["id"],
        "ticket_type": "general",
        "send_email": False,
        "guests": [
            {"name": "Family Alpha", "ticket_type": "guest"},
            {"name": "Family Bravo", "ticket_type": "guest"},
        ],
    }, timeout=20)
    yield ev, target
    admin_s.delete(f"{API}/events/{ev['id']}", timeout=10)


def test_quick_family_batch_checkin(admin_s, family_event):
    """Simulates what the Quick mode submit loop does: fires 3 /check-in POSTs
    (member + 2 guests) sequentially. All three must land."""
    ev, host = family_event
    payloads = [
        {"user_id": host["id"], "ticket_type": "general"},
        {"guest_name": "Family Alpha", "host_user_id": host["id"], "ticket_type": "guest"},
        {"guest_name": "Family Bravo", "host_user_id": host["id"], "ticket_type": "guest"},
    ]
    for p in payloads:
        r = admin_s.post(f"{API}/events/{ev['id']}/check-in", json=p, timeout=15)
        assert r.status_code == 200, f"check-in failed: {r.text}"
    # Verify roster reflects all three.
    roster = admin_s.get(f"{API}/events/{ev['id']}/check-in-roster", timeout=15).json()
    member_row = next((row for row in roster if row.get("kind") == "member" and row.get("user_id") == host["id"]), None)
    assert member_row and member_row["checked_in"], "host member missing from roster"
    for guest_name in ["Family Alpha", "Family Bravo"]:
        g = next((row for row in roster if row.get("kind") == "guest" and row.get("name") == guest_name), None)
        assert g and g["checked_in"], f"{guest_name} not checked in"
