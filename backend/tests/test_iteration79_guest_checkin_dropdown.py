"""Iter79 — admin can pick a guest from the searchable dropdown when checking in.

The frontend now flattens every RSVP'd guest into a searchable list and submits
`POST /events/{id}/check-in` with `{guest_name, host_user_id, ticket_type}`.
This test exercises that backend contract end-to-end and confirms:

  1. A guest check-in with host_user_id links the check-in to the host member
     so reports group guests under their inviter.
  2. The duplicate-guest check-in guard still works when the same
     (host_user_id, guest_name) pair is submitted twice.
  3. A walk-in (no host_user_id) still works for the "manually type a guest"
     escape hatch.
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


def _iso_future(days=30, hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


@pytest.fixture
def event_with_rsvp(admin_s, member_s):
    """Create event, RSVP member + 2 guests via the admin-rsvp endpoint, yield
    the trio. Cleans up at the end."""
    # Event
    r = admin_s.post(f"{API}/events", json={
        "title": f"Iter79 Guest Check-in {uuid.uuid4().hex[:6]}",
        "description": "guest check-in dropdown test",
        "location": "DC",
        "start_at": _iso_future(40),
        "end_at": _iso_future(40, 3),
        "category": "general",
        "capacity": 50,
    }, timeout=15)
    assert r.status_code == 200, r.text
    ev = r.json()
    # Find member id
    members = admin_s.get(f"{API}/members", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    target = next((m for m in members if m.get("email") == MEMBER["email"]), None)
    assert target, "demo member not found"
    # Admin RSVPs member + 2 guests
    r = admin_s.post(f"{API}/events/{ev['id']}/admin-rsvp", json={
        "user_id": target["id"],
        "ticket_type": "general",
        "send_email": False,
        "guests": [
            {"name": "Alex Guest", "ticket_type": "guest"},
            {"name": "Pat Guest", "ticket_type": "guest"},
        ],
    }, timeout=20)
    assert r.status_code == 200, r.text
    yield ev, target
    admin_s.delete(f"{API}/events/{ev['id']}", timeout=10)


def test_guest_checkin_with_host_user_id_links_to_member(admin_s, event_with_rsvp):
    ev, host = event_with_rsvp
    # Check in the first guest with host linkage
    r = admin_s.post(f"{API}/events/{ev['id']}/check-in", json={
        "guest_name": "Alex Guest",
        "host_user_id": host["id"],
        "ticket_type": "guest",
    }, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_guest"] is True
    assert body["host_user_id"] == host["id"]
    assert body["user_name"] == "Alex Guest"

    # Also confirm the /check-in-roster surfaces the guest as checked_in
    roster = admin_s.get(f"{API}/events/{ev['id']}/check-in-roster", timeout=15).json()
    alex_row = next((row for row in roster if row.get("kind") == "guest" and row.get("name") == "Alex Guest"), None)
    assert alex_row, "Alex Guest missing from roster"
    assert alex_row["checked_in"] is True
    pat_row = next((row for row in roster if row.get("kind") == "guest" and row.get("name") == "Pat Guest"), None)
    assert pat_row and pat_row["checked_in"] is False, "Pat shouldn't be checked in yet"


def test_duplicate_guest_checkin_is_blocked(admin_s, event_with_rsvp):
    ev, host = event_with_rsvp
    payload = {"guest_name": "Alex Guest", "host_user_id": host["id"], "ticket_type": "guest"}
    r1 = admin_s.post(f"{API}/events/{ev['id']}/check-in", json=payload, timeout=15)
    assert r1.status_code == 200, r1.text
    r2 = admin_s.post(f"{API}/events/{ev['id']}/check-in", json=payload, timeout=15)
    assert r2.status_code == 400, r2.text
    assert "already" in r2.json().get("detail", "").lower()


def test_walk_in_guest_without_host_still_works(admin_s, event_with_rsvp):
    """The 'guest not listed — type manually' escape hatch."""
    ev, _ = event_with_rsvp
    r = admin_s.post(f"{API}/events/{ev['id']}/check-in", json={
        "guest_name": "Random Walkin",
        "ticket_type": "guest",
    }, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_guest"] is True
    assert body["host_user_id"] is None
    # Roster should include them as a walk-in row
    roster = admin_s.get(f"{API}/events/{ev['id']}/check-in-roster", timeout=15).json()
    walkin = next((row for row in roster if row.get("kind") == "walkin" and row.get("name") == "Random Walkin"), None)
    assert walkin, "Walk-in row missing from roster"
    assert walkin["checked_in"] is True
