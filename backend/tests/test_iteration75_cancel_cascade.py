"""Iter75 — cascade cancellation from parent event to sub-events.

Behaviour under test:
  - When an admin sets `cancelled=true` on a parent event via
    PUT /api/events/{id}, every sub-event (parent_event_id == id) is also
    marked cancelled and tagged with `cancelled_via_parent=true`.
  - Members get a 400 when they try to RSVP/edit-guests on those sub-events
    (defense-in-depth: the rsvps router also rejects when the parent is
    cancelled even if the cascade didn't reach this row).
  - When the admin un-cancels the parent, only sub-events tagged
    `cancelled_via_parent=true` are reverted — sub-events the admin had
    cancelled independently stay cancelled.

Endpoints exercised:
  PUT  /api/events/{id}        (cancel + uncancel)
  POST /api/events             (create the parent + 2 children inline)
  POST /api/events/{id}/rsvp   (member self-RSVP — expect 400 when blocked)
  DELETE /api/events/{id}      (cleanup)
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
def umbrella(admin_s):
    """Create a parent event + 2 sub-events. Cleans up at the end."""
    tag = f"iter75-{uuid.uuid4().hex[:8]}"
    parent_payload = {
        "title": f"PARENT {tag}",
        "description": "iter75 cascade-cancellation test umbrella",
        "location": "DC",
        "start_at": _iso_future(30),
        "end_at": _iso_future(30, 4),
        "category": "general",
        "capacity": 100,
    }
    r = admin_s.post(f"{API}/events", json=parent_payload, timeout=15)
    assert r.status_code == 200, r.text
    parent = r.json()
    children = []
    for i, hour_offset in enumerate([1, 2]):
        child_payload = {
            "title": f"SUB-{i} {tag}",
            "description": f"iter75 cascade-cancellation child {i}",
            "location": "DC",
            "start_at": _iso_future(30, hour_offset),
            "end_at": _iso_future(30, hour_offset + 1),
            "category": "general",
            "capacity": 50,
            "parent_event_id": parent["id"],
        }
        rc = admin_s.post(f"{API}/events", json=child_payload, timeout=15)
        assert rc.status_code == 200, rc.text
        children.append(rc.json())
    yield parent, children
    # cleanup
    for c in children:
        admin_s.delete(f"{API}/events/{c['id']}", timeout=10)
    admin_s.delete(f"{API}/events/{parent['id']}", timeout=10)


def _get(admin_s, eid):
    r = admin_s.get(f"{API}/events/{eid}", timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


# ============================================================
# Tests
# ============================================================

def test_cascade_cancels_all_subevents(admin_s, umbrella):
    parent, children = umbrella
    # Sanity: all currently uncancelled
    for c in children:
        assert _get(admin_s, c["id"])["cancelled"] is False

    r = admin_s.put(
        f"{API}/events/{parent['id']}",
        json={"cancelled": True, "cancellation_note": "Hurricane warning"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["cancelled"] is True

    # All children must now be cancelled and tagged via cascade
    for c in children:
        fresh = _get(admin_s, c["id"])
        assert fresh["cancelled"] is True, f"child {c['id']} not cascade-cancelled"
        assert fresh.get("cancelled_via_parent") is True
        # The cancellation note should have propagated
        assert fresh.get("cancellation_note") == "Hurricane warning"


def test_cascade_uncancel_only_touches_inherited(admin_s, umbrella):
    parent, children = umbrella
    # Cancel parent → cascades to both
    admin_s.put(f"{API}/events/{parent['id']}", json={"cancelled": True, "cancellation_note": "test"}, timeout=15)
    # Independently mark child[1] so it loses the cascade flag (simulate admin
    # editing the child after cascade — we want it to STAY cancelled on revert).
    admin_s.put(
        f"{API}/events/{children[1]['id']}",
        json={"cancelled": True, "cancellation_note": "kept independently"},
        timeout=15,
    )
    # Directly clear cancelled_via_parent on child[1] to simulate the admin
    # turning it into an "independent" cancellation. Easiest way via API: PUT
    # is the only path, and our update_event preserves whatever fields it
    # already has. We can simulate by un-cancelling then re-cancelling child[1]:
    admin_s.put(f"{API}/events/{children[1]['id']}", json={"cancelled": False}, timeout=15)
    admin_s.put(
        f"{API}/events/{children[1]['id']}",
        json={"cancelled": True, "cancellation_note": "kept independently"},
        timeout=15,
    )
    # Now child[1] is cancelled but cancelled_via_parent should be False
    fresh1 = _get(admin_s, children[1]["id"])
    assert fresh1["cancelled"] is True
    assert fresh1.get("cancelled_via_parent") is False

    # Un-cancel the parent
    r = admin_s.put(f"{API}/events/{parent['id']}", json={"cancelled": False}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["cancelled"] is False

    # child[0] was cancelled by cascade → reverted
    assert _get(admin_s, children[0]["id"])["cancelled"] is False
    # child[1] was independently cancelled → still cancelled
    assert _get(admin_s, children[1]["id"])["cancelled"] is True


def test_member_rsvp_blocked_on_cascaded_subevent(admin_s, member_s, umbrella):
    parent, children = umbrella
    # Cancel parent — cascade should hit children
    admin_s.put(f"{API}/events/{parent['id']}", json={"cancelled": True, "cancellation_note": "snow"}, timeout=15)

    # Member tries to RSVP to a sub-event → 400
    r = member_s.post(f"{API}/events/{children[0]['id']}/rsvp", json={}, timeout=15)
    assert r.status_code == 400, r.text
    assert "cancel" in r.json().get("detail", "").lower()


def test_member_rsvp_blocked_when_only_parent_is_cancelled(admin_s, member_s, umbrella):
    """Defense-in-depth: if a sub-event somehow has cancelled=False but its
    parent is cancelled, the RSVP must still be blocked. We simulate this by
    cancelling the parent (cascade), then manually un-cancelling the child via
    the API while the parent stays cancelled."""
    parent, children = umbrella
    admin_s.put(f"{API}/events/{parent['id']}", json={"cancelled": True}, timeout=15)
    # Force child back to uncancelled (admin override)
    admin_s.put(f"{API}/events/{children[0]['id']}", json={"cancelled": False}, timeout=15)

    fresh = _get(admin_s, children[0]["id"])
    assert fresh["cancelled"] is False  # child is locally uncancelled
    # …but the parent is still cancelled, so RSVP must still 400
    r = member_s.post(f"{API}/events/{children[0]['id']}/rsvp", json={}, timeout=15)
    assert r.status_code == 400, r.text
    assert "parent" in r.json().get("detail", "").lower()
