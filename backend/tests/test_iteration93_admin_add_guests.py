"""Iteration 93 — Admin adds guests to an existing member's RSVP.

Verifies POST /api/events/{event_id}/rsvps/{user_id}/guests:
  - 403 for non-admin callers
  - 404 when the member hasn't RSVP'd yet
  - 400 on empty guest list
  - 200 happy path with per-guest ticket_id + admin attribution
  - Guest with `email` gets `email_sent_at` stamped after the email path
    runs (we don't actually send mail in tests — Resend is stubbed off via
    RESEND_API_KEY=""; we just confirm the structural response).
"""
import os
import uuid

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@clubhaven.app", "Admin123!")


@pytest.fixture(scope="module")
def member_token():
    return _login("member@clubhaven.app", "Member123!")


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pick_event(token: str) -> dict:
    """Pick any free, future, non-cancelled, non-closed, non-umbrella event."""
    r = requests.get(f"{BASE}/events", headers=_h(token))
    r.raise_for_status()
    for e in r.json():
        if (
            not e.get("is_paid")
            and not e.get("cancelled")
            and not e.get("rsvps_closed")
            and not e.get("has_children")
        ):
            return e
    pytest.skip("No suitable test event available")


def test_admin_add_guests_happy_path(admin_token, member_token):
    event = _pick_event(admin_token)
    # Make sure the member has an RSVP (idempotent — delete + re-create).
    member_me = requests.get(f"{BASE}/auth/me", headers=_h(member_token)).json()
    member_id = member_me["id"]
    # Delete any pre-existing RSVP (idempotent admin path).
    requests.delete(f"{BASE}/events/{event['id']}/rsvps/{member_id}", headers=_h(admin_token))
    rsvp = requests.post(f"{BASE}/events/{event['id']}/rsvp", headers=_h(member_token), json={})
    assert rsvp.status_code == 200, rsvp.text

    # Admin adds 2 guests, one with email, one without.
    payload = {
        "guests": [
            {"name": "Alice Tester", "email": "alice@example.com", "ticket_type": "general"},
            {"name": "Bob Tester", "ticket_type": "vip"},
        ],
        "send_email": False,  # avoid touching Resend in tests
    }
    r = requests.post(
        f"{BASE}/events/{event['id']}/rsvps/{member_id}/guests",
        headers=_h(admin_token),
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert len(body["added"]) == 2
    assert all("ticket_id" in g and len(g["ticket_id"]) >= 16 for g in body["added"])
    assert body["total_guests"] >= 2
    # Cleanup.
    requests.delete(f"{BASE}/events/{event['id']}/rsvps/{member_id}", headers=_h(admin_token))


def test_admin_add_guests_no_rsvp_yet(admin_token):
    event = _pick_event(admin_token)
    fake_user_id = str(uuid.uuid4())
    r = requests.post(
        f"{BASE}/events/{event['id']}/rsvps/{fake_user_id}/guests",
        headers=_h(admin_token),
        json={"guests": [{"name": "Ghost"}]},
    )
    assert r.status_code == 404
    assert "has not RSVP" in r.json()["detail"]


def test_admin_add_guests_rejects_non_admin(member_token):
    event = _pick_event(member_token)
    member_me = requests.get(f"{BASE}/auth/me", headers=_h(member_token)).json()
    r = requests.post(
        f"{BASE}/events/{event['id']}/rsvps/{member_me['id']}/guests",
        headers=_h(member_token),
        json={"guests": [{"name": "Sneaky"}]},
    )
    assert r.status_code == 403


def test_admin_add_guests_empty_payload_rejected(admin_token, member_token):
    event = _pick_event(admin_token)
    member_me = requests.get(f"{BASE}/auth/me", headers=_h(member_token)).json()
    # Ensure member has an RSVP first so we trigger the empty-guest path
    # rather than the "no RSVP yet" path.
    requests.delete(f"{BASE}/events/{event['id']}/rsvps/{member_me['id']}", headers=_h(admin_token))
    rsvp_ok = requests.post(f"{BASE}/events/{event['id']}/rsvp", headers=_h(member_token), json={})
    assert rsvp_ok.status_code == 200
    try:
        r = requests.post(
            f"{BASE}/events/{event['id']}/rsvps/{member_me['id']}/guests",
            headers=_h(admin_token),
            json={"guests": []},
        )
        assert r.status_code == 400
        assert "at least one guest" in r.json()["detail"].lower()
    finally:
        requests.delete(f"{BASE}/events/{event['id']}/rsvps/{member_me['id']}", headers=_h(admin_token))


def test_admin_add_guests_persists_email_and_admin_attribution(admin_token, member_token):
    """Verify the guest's email field is stored alongside admin attribution
    (who added it + timestamp) so the audit trail is preserved."""
    event = _pick_event(admin_token)
    member_me = requests.get(f"{BASE}/auth/me", headers=_h(member_token)).json()
    requests.delete(f"{BASE}/events/{event['id']}/rsvps/{member_me['id']}", headers=_h(admin_token))
    requests.post(f"{BASE}/events/{event['id']}/rsvp", headers=_h(member_token), json={})
    try:
        r = requests.post(
            f"{BASE}/events/{event['id']}/rsvps/{member_me['id']}/guests",
            headers=_h(admin_token),
            json={
                "guests": [{"name": "Carol Tester", "email": "carol@example.com"}],
                "send_email": False,
            },
        )
        assert r.status_code == 200, r.text
        # Fetch the RSVP list and find Carol.
        rsvps = requests.get(f"{BASE}/events/{event['id']}/rsvps", headers=_h(admin_token)).json()
        my_row = next((row for row in rsvps if row["user_id"] == member_me["id"]), None)
        assert my_row is not None
        carol = next((g for g in (my_row.get("guests") or []) if g.get("name") == "Carol Tester"), None)
        assert carol is not None
        assert carol.get("email") == "carol@example.com"
        assert carol.get("added_by_admin"), "admin attribution should be stamped"
        assert carol.get("ticket_id"), "ticket_id should be assigned"
    finally:
        requests.delete(f"{BASE}/events/{event['id']}/rsvps/{member_me['id']}", headers=_h(admin_token))
