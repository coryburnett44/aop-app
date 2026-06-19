"""Iteration 50 — admin-rsvp + combined member RSVP+guests flow.

Tests:
- POST /api/events/{id}/admin-rsvp happy paths (send_email True/False)
- 409/400/404/403 error paths
- Capacity enforcement (no-email path)
- Member-side POST /api/events/{id}/rsvp with guests included in single call
"""
import os
import uuid
import pytest
import requests


def _load_backend_url():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if not val:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not val:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return val.rstrip("/")


BASE_URL = _load_backend_url()
ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}
DEMO_MEMBERS = [
    {"email": "maya.patel@clubhaven.app", "password": "Demo123!"},
    {"email": "jordan.reed@clubhaven.app", "password": "Demo123!"},
    {"email": "sam.okafor@clubhaven.app", "password": "Demo123!"},
    {"email": "harper.liu@clubhaven.app", "password": "Demo123!"},
]


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin_client():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def member_client():
    return _login(MEMBER)


@pytest.fixture(scope="session")
def admin_user(admin_client):
    return admin_client.get(f"{BASE_URL}/api/auth/me", timeout=15).json()


@pytest.fixture(scope="session")
def member_user(member_client):
    return member_client.get(f"{BASE_URL}/api/auth/me", timeout=15).json()


@pytest.fixture(scope="session")
def umbrella_event(admin_client):
    """The 10-Year Anniversary event is a parent with sub-events in seed."""
    events = admin_client.get(f"{BASE_URL}/api/events", timeout=15).json()
    for e in events:
        if "10-Year" in (e.get("title") or ""):
            # confirm it has sub-events
            subs = admin_client.get(f"{BASE_URL}/api/events/{e['id']}/sub-events", timeout=15).json()
            if isinstance(subs, list) and len(subs) > 0:
                return e
    pytest.skip("No umbrella event with sub-events found in seed")


def _create_event(admin_client, capacity=0, cancelled=False, paid=False):
    payload = {
        "title": f"TEST_AdminRsvp {uuid.uuid4().hex[:8]}",
        "description": "iter50 test event",
        "location": "Test Hall",
        "start_at": "2027-01-01T18:00:00+00:00",
        "end_at": "2027-01-01T20:00:00+00:00",
        "capacity": capacity,
        "category": "social",
        "is_paid": paid,
    }
    r = admin_client.post(f"{BASE_URL}/api/events", json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    ev = r.json()
    if cancelled:
        cr = admin_client.put(f"{BASE_URL}/api/events/{ev['id']}", json={"cancelled": True}, timeout=15)
        assert cr.status_code == 200, cr.text
        ev = cr.json()
    return ev


@pytest.fixture
def fresh_event(admin_client):
    ev = _create_event(admin_client)
    yield ev
    try:
        admin_client.delete(f"{BASE_URL}/api/rsvps/event/{ev['id']}", timeout=10)
    except Exception:
        pass
    admin_client.delete(f"{BASE_URL}/api/events/{ev['id']}", timeout=10)


@pytest.fixture
def cancelled_event(admin_client):
    ev = _create_event(admin_client, cancelled=True)
    yield ev
    admin_client.delete(f"{BASE_URL}/api/events/{ev['id']}", timeout=10)


def _clear_rsvp(admin_client, event_id, user_id):
    """Best-effort: have the user remove their RSVP by toggling."""
    pass


# =========================================================
# AUTHZ
# =========================================================
class TestAuthz:
    def test_non_admin_member_gets_403(self, member_client, fresh_event, member_user):
        r = member_client.post(
            f"{BASE_URL}/api/events/{fresh_event['id']}/admin-rsvp",
            json={"user_id": member_user["id"], "send_email": False},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_anon_gets_401(self, fresh_event, member_user):
        r = requests.post(
            f"{BASE_URL}/api/events/{fresh_event['id']}/admin-rsvp",
            json={"user_id": member_user["id"]},
            timeout=15,
        )
        assert r.status_code in (401, 403), r.text


# =========================================================
# VALIDATION / ERROR PATHS
# =========================================================
class TestValidation:
    def test_missing_user_id_returns_400(self, admin_client, fresh_event):
        r = admin_client.post(
            f"{BASE_URL}/api/events/{fresh_event['id']}/admin-rsvp",
            json={"send_email": False},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "user_id" in r.text.lower()

    def test_nonexistent_user_id_returns_404(self, admin_client, fresh_event):
        r = admin_client.post(
            f"{BASE_URL}/api/events/{fresh_event['id']}/admin-rsvp",
            json={"user_id": "does-not-exist-" + uuid.uuid4().hex, "send_email": False},
            timeout=15,
        )
        assert r.status_code == 404, r.text
        assert "member" in r.text.lower() or "not found" in r.text.lower()

    def test_nonexistent_event_returns_404(self, admin_client, member_user):
        r = admin_client.post(
            f"{BASE_URL}/api/events/does-not-exist-{uuid.uuid4().hex}/admin-rsvp",
            json={"user_id": member_user["id"], "send_email": False},
            timeout=15,
        )
        assert r.status_code == 404, r.text

    def test_cancelled_event_returns_400(self, admin_client, cancelled_event, member_user):
        r = admin_client.post(
            f"{BASE_URL}/api/events/{cancelled_event['id']}/admin-rsvp",
            json={"user_id": member_user["id"], "send_email": False},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "cancel" in r.text.lower()

    def test_umbrella_parent_event_returns_400(self, admin_client, umbrella_event, member_user):
        r = admin_client.post(
            f"{BASE_URL}/api/events/{umbrella_event['id']}/admin-rsvp",
            json={"user_id": member_user["id"], "send_email": False},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "umbrella" in r.text.lower() or "sub-event" in r.text.lower()


# =========================================================
# HAPPY PATHS — admin-rsvp
# =========================================================
class TestAdminRsvpNoEmail:
    def test_create_no_email_with_2_guests(self, admin_client, fresh_event, admin_user, member_user):
        body = {
            "user_id": member_user["id"],
            "ticket_type": "general",
            "guests": [{"name": "Alex"}, {"name": "Pat"}],
            "send_email": False,
        }
        r = admin_client.post(
            f"{BASE_URL}/api/events/{fresh_event['id']}/admin-rsvp",
            json=body, timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["rsvped"] is True
        assert data["user_id"] == member_user["id"]
        assert data["user_name"] == member_user.get("name", "")
        assert data["guests"] == 2
        assert data["email_sent"] is False
        assert isinstance(data.get("ticket_id"), str) and len(data["ticket_id"]) > 0

        # Verify RSVP row persisted via admin attendees endpoint
        att = admin_client.get(f"{BASE_URL}/api/events/{fresh_event['id']}/rsvps", timeout=15)
        if att.status_code != 200:
            att = admin_client.get(f"{BASE_URL}/api/events/{fresh_event['id']}/attendees", timeout=15)
        assert att.status_code == 200, att.text
        rows = att.json()
        # find our row
        match = [r for r in rows if (r.get("user_id") == member_user["id"])]
        assert len(match) >= 1, f"RSVP row not found: {rows}"
        row = match[0]
        # Validate doc shape — created_by_admin and email_suppressed should be present
        assert row.get("created_by_admin") == admin_user["id"], f"created_by_admin missing: {row}"
        assert row.get("created_by_admin_name") == admin_user.get("name", "Admin")
        assert row.get("email_suppressed") is True, f"email_suppressed not set: {row}"
        assert len(row.get("guests") or []) == 2
        guest_names = sorted(g.get("name") for g in row["guests"])
        assert guest_names == ["Alex", "Pat"]
        # Each guest sub-doc should have ticket_id
        for g in row["guests"]:
            assert g.get("ticket_id"), g
            assert g.get("ticket_type") == "general"


class TestAdminRsvpWithEmail:
    def test_create_with_email_stamps_attribution(self, admin_client, fresh_event, admin_user):
        # Use a demo member to avoid conflict with member@clubhaven.app
        # Login as a demo member to discover their user_id, then logout — we
        # only need the id for the admin-rsvp call.
        demo = _login(DEMO_MEMBERS[0])
        target = demo.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
        assert target.get("id"), "could not resolve demo member id"

        r = admin_client.post(
            f"{BASE_URL}/api/events/{fresh_event['id']}/admin-rsvp",
            json={"user_id": target["id"], "ticket_type": "general", "send_email": True},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["rsvped"] is True
        assert data["email_sent"] is True
        assert data["guests"] == 0

        # Verify attribution stamped via shared helper path
        att = admin_client.get(f"{BASE_URL}/api/events/{fresh_event['id']}/rsvps", timeout=15)
        if att.status_code != 200:
            att = admin_client.get(f"{BASE_URL}/api/events/{fresh_event['id']}/attendees", timeout=15)
        rows = att.json()
        row = next((r for r in rows if r.get("user_id") == target["id"]), None)
        assert row, f"target RSVP not found"
        assert row.get("created_by_admin") == admin_user["id"]
        assert row.get("created_by_admin_name") == admin_user.get("name", "Admin")
        # email_suppressed should NOT be set (or be falsy) on the email path
        assert not row.get("email_suppressed"), f"email_suppressed should not be true on send_email path: {row}"


class TestAdminRsvpDuplicate:
    def test_duplicate_returns_409(self, admin_client, fresh_event, member_user):
        body = {"user_id": member_user["id"], "send_email": False}
        r1 = admin_client.post(
            f"{BASE_URL}/api/events/{fresh_event['id']}/admin-rsvp",
            json=body, timeout=15,
        )
        assert r1.status_code == 200, r1.text
        r2 = admin_client.post(
            f"{BASE_URL}/api/events/{fresh_event['id']}/admin-rsvp",
            json=body, timeout=15,
        )
        assert r2.status_code == 409, r2.text
        assert "already" in r2.text.lower()


class TestAdminRsvpCapacity:
    def test_over_capacity_no_email_returns_400(self, admin_client, member_user):
        ev = _create_event(admin_client, capacity=2)
        try:
            # capacity 2 → me + 2 guests = 3 seats > 2 -> should 400
            r = admin_client.post(
                f"{BASE_URL}/api/events/{ev['id']}/admin-rsvp",
                json={
                    "user_id": member_user["id"],
                    "guests": [{"name": "G1"}, {"name": "G2"}],
                    "send_email": False,
                },
                timeout=15,
            )
            assert r.status_code == 400, r.text
            assert "seat" in r.text.lower() or "capac" in r.text.lower()
        finally:
            admin_client.delete(f"{BASE_URL}/api/events/{ev['id']}", timeout=10)


# =========================================================
# MEMBER-SIDE combined RSVP+guests in one call
# =========================================================
class TestMemberCombinedRsvp:
    def test_member_rsvp_with_guests_in_single_call(self, admin_client, member_client, member_user):
        ev = _create_event(admin_client)
        try:
            r = member_client.post(
                f"{BASE_URL}/api/events/{ev['id']}/rsvp",
                json={"ticket_type": "general", "guests": [{"name": "Alex"}]},
                timeout=20,
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["rsvped"] is True
            assert data["guests"] == 1
            assert data.get("ticket_id")

            # Verify exactly ONE RSVP doc with 1 guest persisted
            att = admin_client.get(f"{BASE_URL}/api/events/{ev['id']}/rsvps", timeout=15)
            if att.status_code != 200:
                att = admin_client.get(f"{BASE_URL}/api/events/{ev['id']}/attendees", timeout=15)
            rows = att.json()
            mine = [r for r in rows if r.get("user_id") == member_user["id"]]
            assert len(mine) == 1, f"expected exactly one RSVP doc, got {len(mine)}: {mine}"
            assert len(mine[0].get("guests") or []) == 1
            assert (mine[0]["guests"][0].get("name")) == "Alex"
            # No admin attribution on self-service path
            assert not mine[0].get("created_by_admin")
        finally:
            # cleanup: member toggles off
            try:
                member_client.post(f"{BASE_URL}/api/events/{ev['id']}/rsvp", timeout=10)
            except Exception:
                pass
            admin_client.delete(f"{BASE_URL}/api/events/{ev['id']}", timeout=10)
