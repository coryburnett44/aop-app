"""Iter76 — admin can delete default photo albums + per-guest ticket type on admin-RSVP.

Tests:
  A. DELETE /api/photos/albums/{id} on a default album:
     - 403 for non-admin
     - 200 for admin, tombstone created, list no longer returns it.
  B. POST /api/events/{id}/admin-rsvp with mixed-ticket-type guests:
     - guest ticket_types persist on the resulting rsvp row.
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


@pytest.fixture(scope="module")
def member_s():
    return _login(MEMBER)


# ============================================================
# A. Admin delete default album
# ============================================================

def test_admin_can_delete_default_album_and_member_cannot(admin_s, member_s):
    # Find a default album
    albums = admin_s.get(f"{API}/photos/albums", timeout=15).json()
    default = next((a for a in albums if a.get("is_default")), None)
    assert default, "no default album found in seed"
    aid = default["id"]
    aname = default["name"]

    # Member cannot delete a default album
    r_member = member_s.delete(f"{API}/photos/albums/{aid}", timeout=15)
    assert r_member.status_code == 403, r_member.text

    # Admin can delete it
    r_admin = admin_s.delete(f"{API}/photos/albums/{aid}", timeout=15)
    assert r_admin.status_code == 200, r_admin.text
    assert r_admin.json().get("ok") is True

    # Verify it's gone from the listing
    fresh = admin_s.get(f"{API}/photos/albums", timeout=15).json()
    assert not any(a["id"] == aid for a in fresh), "deleted default album still in listing"

    # Restore for idempotency: re-create with same name as a custom album so the
    # next test run still sees it. (We can't easily reinsert as is_default=true
    # without bypassing the API; the tombstone will block the seeder from
    # restoring it on next boot — that's the intended behaviour.)
    rebuild = admin_s.post(f"{API}/photos/albums", json={"name": aname, "category": "other"}, timeout=15)
    # Either created or already exists — both fine.
    assert rebuild.status_code in (200, 400), rebuild.text


# ============================================================
# B. Per-guest ticket type on admin RSVP
# ============================================================

def _iso_future(days=30, hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


@pytest.fixture
def ticketed_event(admin_s):
    """Create an event that allows ticket types so VIP/all_access are accepted."""
    payload = {
        "title": f"Iter76 Ticketed {uuid.uuid4().hex[:6]}",
        "description": "ticket-type guest test",
        "location": "DC",
        "start_at": _iso_future(40),
        "end_at": _iso_future(40, 3),
        "category": "general",
        "capacity": 50,
        "allows_ticket_types": True,
        "enabled_ticket_types": ["vip", "all_access", "general", "guest"],
    }
    r = admin_s.post(f"{API}/events", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    ev = r.json()
    yield ev
    admin_s.delete(f"{API}/events/{ev['id']}", timeout=10)


def test_admin_rsvp_per_guest_ticket_type_persists(admin_s, ticketed_event):
    # Pick a member to RSVP on behalf of
    members = admin_s.get(f"{API}/members", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    target = next((m for m in members if m.get("email") == MEMBER["email"]), None)
    assert target, "demo member not found"

    body = {
        "user_id": target["id"],
        "ticket_type": "vip",
        "send_email": False,
        "guests": [
            {"name": "Plus One Alpha", "ticket_type": "vip"},
            {"name": "Plus One Bravo", "ticket_type": "all_access"},
            {"name": "Plus One Charlie", "ticket_type": "general"},
        ],
    }
    r = admin_s.post(f"{API}/events/{ticketed_event['id']}/admin-rsvp", json=body, timeout=20)
    assert r.status_code == 200, r.text

    # Confirm guest ticket types persisted on the rsvp row
    rsvps = admin_s.get(f"{API}/events/{ticketed_event['id']}/rsvps", timeout=15).json()
    me = next((x for x in rsvps if x.get("user_id") == target["id"]), None)
    assert me, "rsvp row missing"
    guest_types = {g["name"]: g.get("ticket_type") for g in me.get("guests", [])}
    assert guest_types.get("Plus One Alpha") == "vip"
    assert guest_types.get("Plus One Bravo") == "all_access"
    assert guest_types.get("Plus One Charlie") == "general"
