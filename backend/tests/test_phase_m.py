"""Phase M backend tests — QR ticketed RSVP, admin notification email, check-in flow."""
import os
import time
import uuid
import jwt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASSWORD = "Member123!"

JWT_SECRET = "3c2e4d0174b499e2b5aacf364bac1d87f5541764c0f3d9d62ec8b4c05cd8a0b0"
JWT_ALG = "HS256"

SIP_AND_PAINT_ID = "da96f140-3e0e-4daf-974e-5a27220b7cb9"
ANNIVERSARY_PARENT_ID = "444769bf-5a23-4ed8-973c-ad0e6e187cda"


# ---------- Session fixtures ----------
def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_sess() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def member_sess() -> requests.Session:
    return _login(MEMBER_EMAIL, MEMBER_PASSWORD)


@pytest.fixture(scope="module")
def public_sess() -> requests.Session:
    return requests.Session()


# ============================================================
# 1. Public application — admin notification fires (best-effort)
# ============================================================
class TestApplyAdminNotification:
    def test_apply_returns_200_and_persists(self, public_sess):
        unique = uuid.uuid4().hex[:8]
        payload = {
            "first_name": "TESTM",
            "last_name": f"Applicant{unique}",
            "email": f"apply-test-{unique}@example.com",
            "password": "TestPass123!",
            "line_name": f"TEST Line {unique}",
            "intake_line": "Spring 2026 TEST",
            "intake_completed_at": "2026-01-15",
            "address": "123 Test St",
            "city": "Houston",
            "state": "TX",
            "zip_code": "77001",
            "country": "USA",
        }
        r = public_sess.post(f"{API}/auth/apply", json=payload, timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert "application_id" in data
        # Backend logs (best-effort visible in supervisor) should contain
        # "Admin application notification sent" — we verify via successful 200
        # since email sending is async fire-and-forget.


# ============================================================
# 2. RSVP w/ ticket_type — member ticket_id + guest ticket_ids
# ============================================================
class TestRsvpTickets:
    def _ensure_no_rsvp(self, sess, event_id):
        # Toggle off if already RSVPed
        r = sess.get(f"{API}/me/events", timeout=10)
        if r.status_code == 200 and any(e["id"] == event_id for e in r.json()):
            sess.post(f"{API}/events/{event_id}/rsvp", json={"guests": []}, timeout=10)

    def test_rsvp_creates_ticket_ids_for_member_and_guests(self, member_sess):
        self._ensure_no_rsvp(member_sess, SIP_AND_PAINT_ID)
        payload = {
            "ticket_type": "vip",
            "guests": [
                {"name": "TESTM Guest Alpha", "email": "alpha@example.com", "ticket_type": "general"},
                {"name": "TESTM Guest Bravo", "email": "bravo@example.com", "ticket_type": "vip"},
            ],
        }
        r = member_sess.post(f"{API}/events/{SIP_AND_PAINT_ID}/rsvp", json=payload, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body["rsvped"] is True
        assert body["guests"] == 2
        assert "ticket_id" in body
        member_ticket_id = body["ticket_id"]
        assert isinstance(member_ticket_id, str) and len(member_ticket_id) > 0

        # Verify persistence via /events/{id}/rsvps (admin-only? actually public per server.py)
        r2 = member_sess.get(f"{API}/events/{SIP_AND_PAINT_ID}/rsvps", timeout=10)
        assert r2.status_code == 200
        my_rsvp = next((x for x in r2.json() if x.get("user_name") == "Member User" or x.get("ticket_id") == member_ticket_id), None)
        assert my_rsvp is not None, "RSVP not found"
        assert my_rsvp["ticket_id"] == member_ticket_id
        assert my_rsvp["ticket_type"] == "vip"
        guests = my_rsvp["guests"]
        assert len(guests) == 2
        for g in guests:
            assert "ticket_id" in g and len(g["ticket_id"]) > 0
            assert g["ticket_type"] in ("general", "vip")
        # store for next tests
        pytest._m_member_ticket_id = member_ticket_id
        pytest._m_guest_ticket_ids = [g["ticket_id"] for g in guests]
        pytest._m_guest_names = [g["name"] for g in guests]

    def test_update_rsvp_guests_preserves_ticket_ids(self, member_sess):
        # Send the same two guests + one new — old ticket_ids preserved, new one assigned
        prior_ids = pytest._m_guest_ticket_ids
        payload = {
            "ticket_type": "vip",
            "guests": [
                {"name": "TESTM Guest Alpha", "email": "alpha@example.com", "ticket_type": "general"},
                {"name": "TESTM Guest Bravo", "email": "bravo@example.com", "ticket_type": "vip"},
                {"name": "TESTM Guest Charlie", "email": "charlie@example.com", "ticket_type": "speaker"},
            ],
        }
        r = member_sess.put(f"{API}/events/{SIP_AND_PAINT_ID}/rsvp/guests", json=payload, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body["ok"] is True
        assert body["guests"] == 3

        # Fetch RSVPs and validate ticket_id preservation
        r2 = member_sess.get(f"{API}/events/{SIP_AND_PAINT_ID}/rsvps", timeout=10)
        my_rsvp = next((x for x in r2.json() if x.get("ticket_id") == pytest._m_member_ticket_id), None)
        assert my_rsvp is not None
        new_guests = my_rsvp["guests"]
        new_by_name = {g["name"].strip().lower(): g for g in new_guests}
        # Alpha & Bravo IDs preserved
        assert new_by_name["testm guest alpha"]["ticket_id"] == prior_ids[0]
        assert new_by_name["testm guest bravo"]["ticket_id"] == prior_ids[1]
        # Charlie got a new ticket_id
        charlie = new_by_name["testm guest charlie"]
        assert charlie["ticket_id"] not in prior_ids
        assert charlie["ticket_type"] == "speaker"


# ============================================================
# 3. /checkin/lookup — no-auth decode endpoint
# ============================================================
class TestCheckinLookup:
    def test_garbage_token_returns_400(self, public_sess):
        r = public_sess.get(f"{API}/checkin/lookup/not-a-real-token", timeout=10)
        assert r.status_code == 400

    def test_valid_token_decodes(self, public_sess):
        # Build a JWT identical to make_ticket_token
        token = jwt.encode(
            {
                "event_id": SIP_AND_PAINT_ID,
                "ticket_id": pytest._m_member_ticket_id,
                "kind": "member",
                "ticket_type": "vip",
                "name": "Member User",
                "iat": int(time.time()),
            },
            JWT_SECRET,
            algorithm=JWT_ALG,
        )
        r = public_sess.get(f"{API}/checkin/lookup/{token}", timeout=10)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body["ticket_id"] == pytest._m_member_ticket_id
        assert body["kind"] == "member"
        assert body["ticket_type"] == "vip"
        assert body["event"]["id"] == SIP_AND_PAINT_ID
        pytest._m_member_token = token


# ============================================================
# 4. /checkin/scan — admin auth required + idempotent
# ============================================================
class TestCheckinScan:
    def test_member_role_blocked_with_403(self, member_sess):
        token = pytest._m_member_token
        r = member_sess.post(f"{API}/checkin/scan/{token}", timeout=10)
        assert r.status_code == 403

    def test_admin_scan_member_ticket_creates_checkin(self, admin_sess):
        token = pytest._m_member_token
        r = admin_sess.post(f"{API}/checkin/scan/{token}", timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body["already_checked_in"] is False
        ci = body["checkin"]
        assert ci["ticket_id"] == pytest._m_member_ticket_id
        assert ci["ticket_type"] == "vip"
        assert ci["event_id"] == SIP_AND_PAINT_ID
        assert ci.get("user_id")  # member check-in has user_id
        assert "checked_in_at" in ci
        assert ci["checked_in_by_name"]
        pytest._m_checkin_id = ci["id"]

    def test_admin_scan_idempotent(self, admin_sess):
        token = pytest._m_member_token
        r = admin_sess.post(f"{API}/checkin/scan/{token}", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["already_checked_in"] is True
        assert body["checkin"]["ticket_id"] == pytest._m_member_ticket_id
        assert body["checkin"]["id"] == pytest._m_checkin_id  # SAME row, not duplicated

    def test_admin_scan_guest_ticket(self, admin_sess):
        guest_ticket_id = pytest._m_guest_ticket_ids[0]
        token = jwt.encode(
            {
                "event_id": SIP_AND_PAINT_ID,
                "ticket_id": guest_ticket_id,
                "kind": "guest",
                "ticket_type": "general",
                "name": "TESTM Guest Alpha",
                "iat": int(time.time()),
            },
            JWT_SECRET,
            algorithm=JWT_ALG,
        )
        r = admin_sess.post(f"{API}/checkin/scan/{token}", timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body["already_checked_in"] is False
        ci = body["checkin"]
        assert ci["ticket_id"] == guest_ticket_id
        assert ci["ticket_type"] == "general"
        assert ci["guest_name"] == "TESTM Guest Alpha"
        assert ci.get("host_user_id")
        pytest._m_guest_checkin_id = ci["id"]

    def test_admin_scan_garbage_token_400(self, admin_sess):
        r = admin_sess.post(f"{API}/checkin/scan/garbage.token.xyz", timeout=10)
        assert r.status_code == 400


# ============================================================
# 5. Chapter logo URL surfaced on /chapters
# ============================================================
class TestChapterLogo:
    def test_chapters_endpoint_returns_logo_url_field(self, public_sess):
        r = public_sess.get(f"{API}/chapters", timeout=10)
        assert r.status_code == 200
        chapters = r.json()
        assert len(chapters) > 0
        # logo_url field must be present (even if empty string) on every chapter
        for c in chapters:
            assert "logo_url" in c, f"chapter {c.get('id')} missing logo_url"


# ============================================================
# 6. Cleanup — delete checkins + toggle RSVP off
# ============================================================
@pytest.fixture(scope="module", autouse=True)
def _cleanup(request, admin_sess, member_sess):
    yield
    # Toggle RSVP off
    try:
        member_sess.post(f"{API}/events/{SIP_AND_PAINT_ID}/rsvp", json={"guests": []}, timeout=10)
    except Exception:
        pass
    # No public endpoint to delete checkins; leave the test rows (admin can clean later).
    # They are tagged TESTM in user_name/guest_name.
