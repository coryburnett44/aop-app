"""Iter80 — sub-events accept free / Zeffy-paid / external-link modes.

Verifies that POST /events with parent_event_id set + any of:
  - is_paid + payment_url + payment_amount  → Zeffy paid sub-event
  - external_url + external_button_label   → External-ticket sub-event
  - (neither)                                → Free RSVP sub-event

are persisted correctly and the RSVP/payment endpoints treat each mode the
right way:
  - Free sub-event → POST /rsvp succeeds
  - Zeffy paid sub-event → POST /rsvp returns 402; payment/confirm flow is the
    correct path
  - External sub-event → POST /rsvp still succeeds (external is a UI-only
    redirect; backend does not block).
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
def umbrella_with_modes(admin_s):
    """Create a parent and 3 sub-events (one per mode). Cleans up at end."""
    tag = f"iter80-{uuid.uuid4().hex[:6]}"
    r = admin_s.post(f"{API}/events", json={
        "title": f"PARENT {tag}",
        "description": "iter80 paid/external sub-event test",
        "location": "DC",
        "start_at": _iso_future(40),
        "end_at": _iso_future(40, 6),
        "category": "general",
        "capacity": 200,
    }, timeout=15)
    assert r.status_code == 200, r.text
    parent = r.json()
    children = []
    specs = [
        {"name": "free", "extras": {}},
        {"name": "zeffy", "extras": {"is_paid": True, "payment_url": "https://www.zeffy.com/en-US/ticketing/iter80-test", "payment_amount": 25.0}},
        {"name": "external", "extras": {"external_url": "https://www.eventbrite.com/iter80-test", "external_button_label": "Get tickets"}},
    ]
    for i, spec in enumerate(specs):
        payload = {
            "title": f"SUB-{spec['name']} {tag}",
            "description": f"iter80 {spec['name']} sub-event",
            "location": "DC",
            "start_at": _iso_future(40, i + 1),
            "end_at": _iso_future(40, i + 2),
            "category": "general",
            "capacity": 50,
            "parent_event_id": parent["id"],
            **spec["extras"],
        }
        rc = admin_s.post(f"{API}/events", json=payload, timeout=15)
        assert rc.status_code == 200, rc.text
        children.append((spec["name"], rc.json()))
    yield parent, children
    for _, c in children:
        admin_s.delete(f"{API}/events/{c['id']}", timeout=10)
    admin_s.delete(f"{API}/events/{parent['id']}", timeout=10)


def test_subevent_modes_persisted_correctly(admin_s, umbrella_with_modes):
    _, children = umbrella_with_modes
    by_mode = {name: ev for name, ev in children}
    assert by_mode["free"]["is_paid"] is False
    assert by_mode["free"]["external_url"] == ""
    assert by_mode["zeffy"]["is_paid"] is True
    assert by_mode["zeffy"]["payment_url"].startswith("https://www.zeffy.com")
    assert by_mode["zeffy"]["payment_amount"] == 25.0
    assert by_mode["external"]["external_url"].startswith("https://www.eventbrite.com")
    assert by_mode["external"]["external_button_label"] == "Get tickets"


def test_free_subevent_rsvp_succeeds(member_s, umbrella_with_modes):
    _, children = umbrella_with_modes
    by_mode = {name: ev for name, ev in children}
    free = by_mode["free"]
    r = member_s.post(f"{API}/events/{free['id']}/rsvp", json={}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("rsvped") is True
    # cleanup: cancel the rsvp
    member_s.post(f"{API}/events/{free['id']}/rsvp", json={}, timeout=15)


def test_paid_subevent_blocks_free_rsvp_and_routes_to_payment_confirm(member_s, umbrella_with_modes):
    _, children = umbrella_with_modes
    by_mode = {name: ev for name, ev in children}
    paid = by_mode["zeffy"]
    # Free RSVP → 402 with hint to use /payment/confirm
    r = member_s.post(f"{API}/events/{paid['id']}/rsvp", json={}, timeout=15)
    assert r.status_code == 402, r.text
    assert "payment" in r.json().get("detail", "").lower()


def test_external_subevent_does_not_block_rsvp_backend(member_s, umbrella_with_modes):
    """The external_url field is a UI hint — backend doesn't reject the RSVP.
    (Frontend renders a 'Get tickets' button and hides the RSVP CTA.)"""
    _, children = umbrella_with_modes
    by_mode = {name: ev for name, ev in children}
    ext = by_mode["external"]
    r = member_s.post(f"{API}/events/{ext['id']}/rsvp", json={}, timeout=15)
    # The backend does not have a guard for external_url, so this returns 200
    # (RSVP'd) — purely a UI-level behaviour. Document the current contract here
    # so it doesn't silently regress.
    assert r.status_code == 200, r.text
    # cleanup
    member_s.post(f"{API}/events/{ext['id']}/rsvp", json={}, timeout=15)
