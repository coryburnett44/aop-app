"""Iter74 — admin un-RSVP + admin remove-guest endpoints.

Endpoints under test:
  DELETE /api/events/{event_id}/rsvps/{user_id}
  DELETE /api/events/{event_id}/rsvps/{user_id}/guests/{ticket_id}
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
EVENT_ID = "3a9ee2e9-7852-4586-9b3f-a94b3da8af84"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "maya.patel@clubhaven.app", "password": "Demo123!"}


# ---------- session helpers ----------
def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def member_session():
    # Maya is currently inactive in the seed state — use Jordan for self-RSVP regression.
    return _login({"email": "jordan.reed@clubhaven.app", "password": "Demo123!"})


@pytest.fixture(scope="module")
def maya_user_id(admin_session):
    r = admin_session.get(f"{API}/members", timeout=15)
    assert r.status_code == 200, r.text
    members = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    m = next((x for x in members if x.get("email") == MEMBER["email"]), None)
    assert m, f"could not find maya in admin members listing"
    return m["id"]


def _event_counters(session):
    r = session.get(f"{API}/events/{EVENT_ID}", timeout=15)
    assert r.status_code == 200, r.text
    e = r.json()
    return int(e.get("rsvp_count") or 0), int(e.get("guest_count") or 0)


def _cleanup_maya_rsvp(admin_session, maya_id):
    """Best-effort idempotent un-RSVP so tests start clean."""
    admin_session.delete(f"{API}/events/{EVENT_ID}/rsvps/{maya_id}", timeout=15)


# ---------- pre-flight ----------
def test_event_exists(admin_session):
    r = admin_session.get(f"{API}/events/{EVENT_ID}", timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("id") == EVENT_ID


# ---------- AuthZ ----------
def test_un_rsvp_requires_admin(member_session, maya_user_id):
    r = member_session.delete(f"{API}/events/{EVENT_ID}/rsvps/{maya_user_id}", timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code} {r.text}"


def test_remove_guest_requires_admin(member_session, maya_user_id):
    r = member_session.delete(
        f"{API}/events/{EVENT_ID}/rsvps/{maya_user_id}/guests/fake-tid", timeout=15
    )
    assert r.status_code in (401, 403)


# ---------- Idempotency: un-RSVP no-op ----------
def test_un_rsvp_idempotent_when_no_rsvp(admin_session, maya_user_id):
    _cleanup_maya_rsvp(admin_session, maya_user_id)
    r = admin_session.delete(f"{API}/events/{EVENT_ID}/rsvps/{maya_user_id}", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data == {"ok": True, "was_present": False, "guests_removed": 0} or (
        data.get("ok") is True and data.get("was_present") is False and data.get("guests_removed") == 0
    )


# ---------- 404 paths ----------
def test_remove_guest_no_rsvp_returns_404(admin_session, maya_user_id):
    _cleanup_maya_rsvp(admin_session, maya_user_id)
    r = admin_session.delete(
        f"{API}/events/{EVENT_ID}/rsvps/{maya_user_id}/guests/some-ticket-id", timeout=15
    )
    assert r.status_code == 404, r.text
    assert "No RSVP" in r.json().get("detail", "")


# ---------- Full counters integrity flow ----------
def test_counter_integrity_full_flow(admin_session, maya_user_id):
    _cleanup_maya_rsvp(admin_session, maya_user_id)
    base_r, base_g = _event_counters(admin_session)

    # admin RSVP with 2 guests
    r = admin_session.post(
        f"{API}/events/{EVENT_ID}/admin-rsvp",
        json={
            "user_id": maya_user_id,
            "ticket_type": "general",
            "guests": [
                {"name": "TEST_Guest_A", "ticket_type": "general"},
                {"name": "TEST_Guest_B", "ticket_type": "general"},
            ],
            "send_email": False,
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    after_create_r, after_create_g = _event_counters(admin_session)
    assert after_create_r == base_r + 1, f"rsvp_count {after_create_r} != {base_r}+1"
    assert after_create_g == base_g + 2, f"guest_count {after_create_g} != {base_g}+2"

    # fetch RSVP to grab ticket_ids
    rsvps = admin_session.get(f"{API}/events/{EVENT_ID}/rsvps", timeout=15).json()
    maya_row = next((row for row in rsvps if row.get("user_id") == maya_user_id), None)
    assert maya_row, "maya RSVP not visible in /rsvps list"
    assert len(maya_row.get("guests", [])) == 2
    guest_a = next(g for g in maya_row["guests"] if g["name"] == "TEST_Guest_A")
    bogus_ticket = "00000000-0000-0000-0000-000000000000"

    # bogus ticket id => 404
    bad = admin_session.delete(
        f"{API}/events/{EVENT_ID}/rsvps/{maya_user_id}/guests/{bogus_ticket}", timeout=15
    )
    assert bad.status_code == 404, bad.text
    assert "Guest not found" in bad.json().get("detail", "")

    # remove guest A
    rg = admin_session.delete(
        f"{API}/events/{EVENT_ID}/rsvps/{maya_user_id}/guests/{guest_a['ticket_id']}", timeout=15
    )
    assert rg.status_code == 200, rg.text
    body = rg.json()
    assert body["ok"] is True
    assert body["removed_guest"]["ticket_id"] == guest_a["ticket_id"]
    assert body["removed_guest"]["name"] == "TEST_Guest_A"
    assert body["remaining_guests"] == 1

    after_g_r, after_g_g = _event_counters(admin_session)
    assert after_g_r == base_r + 1
    assert after_g_g == base_g + 1, f"after guest removal guest_count {after_g_g} != {base_g}+1"

    # full un-RSVP
    ur = admin_session.delete(f"{API}/events/{EVENT_ID}/rsvps/{maya_user_id}", timeout=15)
    assert ur.status_code == 200, ur.text
    body = ur.json()
    assert body["ok"] is True
    assert body["was_present"] is True
    assert body["guests_removed"] == 1
    assert "checkins_removed" in body

    final_r, final_g = _event_counters(admin_session)
    assert final_r == base_r, f"final rsvp_count {final_r} != baseline {base_r}"
    assert final_g == base_g, f"final guest_count {final_g} != baseline {base_g}"


# ---------- Regression: member self-RSVP still works ----------
def test_member_self_rsvp_still_works(member_session, admin_session, maya_user_id):
    _cleanup_maya_rsvp(admin_session, maya_user_id)
    base_r, base_g = _event_counters(admin_session)
    # toggle on (no guests for simplicity)
    r = member_session.post(f"{API}/events/{EVENT_ID}/rsvp", json={"ticket_type": "general", "guests": []}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json().get("rsvped") is True
    # toggle off via same endpoint
    r2 = member_session.post(f"{API}/events/{EVENT_ID}/rsvp", json={"ticket_type": "general", "guests": []}, timeout=20)
    assert r2.status_code == 200
    assert r2.json().get("rsvped") is False
    final_r, final_g = _event_counters(admin_session)
    assert final_r == base_r
    assert final_g == base_g


# ---------- Final cleanup ----------
def test_cleanup_maya_state(admin_session, maya_user_id):
    _cleanup_maya_rsvp(admin_session, maya_user_id)
