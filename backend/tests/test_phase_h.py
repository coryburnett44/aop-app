"""Phase H — Public application flow, reports enrichment, anniversary 2027 dates,
self-check-in, role-change gating, welcome email, intake fields, RSVPs report."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}
MM = {"email": "mm.tx@clubhaven.app", "password": "MemMgr123!"}
GOV = {"email": "governor.tx@clubhaven.app", "password": "Governor123!"}


def login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_s():
    return login(ADMIN)


@pytest.fixture(scope="module")
def member_s():
    return login(MEMBER)


@pytest.fixture(scope="module")
def mm_s():
    return login(MM)


@pytest.fixture(scope="module")
def member_id(member_s):
    return member_s.get(f"{API}/auth/me", timeout=10).json()["id"]


def _unique_email():
    return f"TEST_app_{uuid.uuid4().hex[:10]}@example.com"


# ---------- Public application flow ----------
class TestPublicApplicationFlow:
    def test_submit_returns_application_id(self):
        body = {
            "first_name": "TESTApp",
            "last_name": "Candidate",
            "email": _unique_email(),
            "line_name": "Phantom",
            "intake_line": "Spring 2024",
            "intake_completed_at": "2024-05",
            "address": "100 Test St",
            "city": "Austin",
            "state": "TX",
            "zip_code": "78701",
            "country": "USA",
        }
        r = requests.post(f"{API}/auth/apply", json=body, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert "application_id" in data and len(data["application_id"]) > 0

    def test_duplicate_pending_rejected_400(self):
        email = _unique_email()
        body = {
            "first_name": "Dup",
            "last_name": "Pend",
            "email": email,
        }
        r1 = requests.post(f"{API}/auth/apply", json=body, timeout=10)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/auth/apply", json=body, timeout=10)
        assert r2.status_code == 400
        assert "pending" in r2.text.lower()

    def test_existing_email_rejected_400(self):
        body = {
            "first_name": "Already",
            "last_name": "Member",
            "email": "member@clubhaven.app",
        }
        r = requests.post(f"{API}/auth/apply", json=body, timeout=10)
        assert r.status_code == 400


class TestApplicationsListing:
    def test_admin_can_list_pending(self, admin_s):
        r = admin_s.get(f"{API}/admin/applications?status_filter=pending", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_membership_manager_can_list(self, mm_s):
        r = mm_s.get(f"{API}/admin/applications?status_filter=pending", timeout=10)
        assert r.status_code == 200, r.text

    def test_member_cannot_list_applications(self, member_s):
        r = member_s.get(f"{API}/admin/applications?status_filter=pending", timeout=10)
        assert r.status_code in (401, 403)


class TestApproveCreatesUserAndToken:
    @pytest.fixture(scope="class")
    def approved(self, admin_s):
        # Submit a fresh application
        email = _unique_email()
        body = {"first_name": "Approve", "last_name": "Me", "email": email,
                "intake_line": "Phase H Line", "intake_completed_at": "2023-08",
                "address": "1 A", "city": "Austin", "state": "TX",
                "zip_code": "78704", "country": "USA", "line_name": "Maverick"}
        r = requests.post(f"{API}/auth/apply", json=body, timeout=10)
        assert r.status_code == 200
        app_id = r.json()["application_id"]
        # Approve
        r2 = admin_s.post(
            f"{API}/admin/applications/{app_id}/review",
            json={"action": "approve"}, timeout=20,
        )
        assert r2.status_code == 200, r2.text
        # Backend doesn't expose token directly via API — pull via authenticated admin Mongo proxy? No.
        # We retrieve token via list (status=approved) — but token is in password_set_tokens collection.
        # Workaround: trigger a NEW application then approve, and grab token via a dev path?
        # The server has no token-exposing endpoint. We'll directly hit Mongo via the backend container.
        # Since tests run from outside, instead read application doc and look for "token" — not exposed.
        # Solution: use admin debug — list approved applications then derive user via /api/members?
        # We'll rely on the server having a direct token retrieval method via Mongo CLI on container.
        return {"app_id": app_id, "email": email, "user_id": r2.json().get("user_id")}

    def test_approved_creates_user_record(self, admin_s, approved):
        # Fetch member by id
        uid = approved["user_id"]
        assert uid, "user_id missing in approve response"
        r = admin_s.get(f"{API}/members/{uid}", timeout=10)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["email"] == approved["email"].lower()
        assert u.get("intake_line") == "Phase H Line"
        assert u.get("intake_completed_at") == "2023-08"
        assert u.get("line_name") == "Maverick"

    def test_set_password_then_login_then_replay_blocked(self, admin_s, approved):
        # Pull the issued token directly from Mongo (running inside backend container)
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        # Load backend env
        env = {}
        with open("/app/backend/.env") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")

        async def _get_token():
            c = AsyncIOMotorClient(env["MONGO_URL"])
            db = c[env["DB_NAME"]]
            t = await db.password_set_tokens.find_one({"user_id": approved["user_id"], "used": False})
            return (t or {}).get("token")

        token = asyncio.get_event_loop().run_until_complete(_get_token()) if False else asyncio.run(_get_token())
        assert token, "Token row not found in password_set_tokens"

        # Set password
        new_pw = "NewTestPass123!"
        r = requests.post(
            f"{API}/auth/set-password",
            json={"token": token, "new_password": new_pw},
            timeout=10,
        )
        assert r.status_code == 200, r.text

        # Login works
        r2 = requests.post(
            f"{API}/auth/login",
            json={"email": approved["email"], "password": new_pw},
            timeout=10,
        )
        assert r2.status_code == 200, r2.text

        # Replay: second set-password with same token → 400
        r3 = requests.post(
            f"{API}/auth/set-password",
            json={"token": token, "new_password": "AnotherPass1!"},
            timeout=10,
        )
        assert r3.status_code == 400


class TestRejectApplication:
    def test_reject_application(self, admin_s):
        email = _unique_email()
        r = requests.post(
            f"{API}/auth/apply",
            json={"first_name": "Rej", "last_name": "Ect", "email": email},
            timeout=10,
        )
        app_id = r.json()["application_id"]
        r2 = admin_s.post(
            f"{API}/admin/applications/{app_id}/review",
            json={"action": "reject", "note": "TEST reject reason"},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        # Verify status='rejected' in listing
        r3 = admin_s.get(f"{API}/admin/applications?status_filter=rejected", timeout=10)
        assert r3.status_code == 200
        ids = [a["id"] for a in r3.json()]
        assert app_id in ids
        # And no user with that email
        r4 = admin_s.get(f"{API}/members?q={email}", timeout=10)
        if r4.status_code == 200:
            users = r4.json()
            assert not any(u.get("email") == email for u in (users if isinstance(users, list) else []))


# ---------- Welcome email best-effort (admin create member) ----------
class TestAdminCreateMemberWelcomeEmail:
    def test_admin_create_member_succeeds(self, admin_s):
        email = f"TEST_welcome_{uuid.uuid4().hex[:8]}@example.com"
        body = {
            "email": email,
            "password": "TempPass123!",
            "name": "TEST Welcome",
            "first_name": "TEST",
            "last_name": "Welcome",
        }
        start = time.time()
        r = admin_s.post(f"{API}/admin/members", json=body, timeout=20)
        elapsed = time.time() - start
        assert r.status_code in (200, 201), r.text
        # Confirm endpoint returns reasonably quickly (welcome email is best-effort, must not block)
        assert elapsed < 15, f"endpoint too slow ({elapsed:.1f}s) — welcome email may be blocking"


# ---------- Member Card returns required fields ----------
class TestMemberCardFields:
    def test_get_member_includes_card_fields(self, admin_s, member_id):
        r = admin_s.get(f"{API}/members/{member_id}", timeout=10)
        assert r.status_code == 200
        u = r.json()
        for field in ("avatar_url", "state", "country", "intake_line",
                      "intake_completed_at", "join_date", "line_name",
                      "email", "phone", "address", "city", "bio"):
            assert field in u, f"missing field: {field}"


# ---------- Reports — Members enriched ----------
class TestMembersReportEnriched:
    def test_report_includes_events_and_guests(self, admin_s):
        r = admin_s.get(f"{API}/reports/members", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        row = rows[0]
        for field in ("events_attended_count", "events_attended",
                      "guests_registered_count", "guests_registered"):
            assert field in row, f"missing field: {field} in row: {row}"
        assert isinstance(row["events_attended"], list)
        assert isinstance(row["guests_registered"], list)


# ---------- Reports — RSVPs ----------
class TestRsvpsReport:
    def test_rsvps_no_filter(self, admin_s):
        r = admin_s.get(f"{API}/reports/rsvps", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            for field in ("user_id", "event_id", "rsvped_at"):
                assert field in row, f"missing {field} in {row}"

    def test_rsvps_with_event_filter(self, admin_s, member_s):
        # Find anniversary parent / sub-event id
        evs = member_s.get(f"{API}/events", timeout=10).json()
        parent = next((e for e in evs if e.get("title") == "Alpha Omega Phi 10-Year Anniversary"), None)
        if not parent:
            pytest.skip("Anniversary parent not seeded")
        subs = member_s.get(f"{API}/events/{parent['id']}/sub-events", timeout=10).json()
        sip = next((s for s in subs if s["title"] == "Sip and Paint"), None)
        if not sip:
            pytest.skip("Sip and Paint sub-event missing")
        r = admin_s.get(f"{API}/reports/rsvps?event_id={sip['id']}", timeout=20)
        assert r.status_code == 200, r.text
        for row in r.json():
            assert row["event_id"] == sip["id"]

    def test_rsvps_with_parent_event_filter(self, admin_s, member_s):
        evs = member_s.get(f"{API}/events", timeout=10).json()
        parent = next((e for e in evs if e.get("title") == "Alpha Omega Phi 10-Year Anniversary"), None)
        if not parent:
            pytest.skip("Anniversary parent not seeded")
        r = admin_s.get(f"{API}/reports/rsvps?parent_event_id={parent['id']}", timeout=20)
        assert r.status_code == 200, r.text


# ---------- Self-check-in ----------
class TestSelfCheckIn:
    @pytest.fixture(scope="class")
    def past_event_id(self, admin_s):
        """Create a past event (start_at in the past) owned by admin for self-check-in."""
        from datetime import datetime, timezone, timedelta
        start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        body = {
            "title": f"TEST_SelfCheckIn_{uuid.uuid4().hex[:6]}",
            "description": "test",
            "start_at": start,
            "end_at": end,
            "location": "Online",
            "category": "social",
        }
        r = admin_s.post(f"{API}/events", json=body, timeout=10)
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def test_self_check_in_creates_row(self, member_s, past_event_id):
        r = member_s.post(f"{API}/events/{past_event_id}/self-check-in", timeout=10)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data.get("self_reported") is True or data.get("note") == "self-check-in"

    def test_self_check_in_idempotent(self, member_s, past_event_id):
        r1 = member_s.post(f"{API}/events/{past_event_id}/self-check-in", timeout=10)
        r2 = member_s.post(f"{API}/events/{past_event_id}/self-check-in", timeout=10)
        assert r1.status_code in (200, 201)
        assert r2.status_code in (200, 201), r2.text
        # second call shouldn't crash — id should match (idempotent)
        if "id" in r1.json() and "id" in r2.json():
            assert r1.json()["id"] == r2.json()["id"]


# ---------- Anniversary 2027 reconciliation ----------
class TestAnniversary2027Dates:
    @pytest.fixture(scope="class")
    def anniv(self, member_s):
        evs = member_s.get(f"{API}/events", timeout=10).json()
        parent = next((e for e in evs if e.get("title") == "Alpha Omega Phi 10-Year Anniversary"), None)
        assert parent, "Anniversary parent not seeded"
        subs = member_s.get(f"{API}/events/{parent['id']}/sub-events", timeout=10).json()
        return {"parent": parent, "subs": subs}

    def test_parent_start_end_dates(self, anniv):
        parent = anniv["parent"]
        assert parent.get("start_at", "").startswith("2027-07-29"), parent.get("start_at")
        assert parent.get("end_at", "").startswith("2027-07-31"), parent.get("end_at")

    def test_sub_event_dates(self, anniv):
        by_title = {s["title"]: s for s in anniv["subs"]}
        # Sip&Paint + Transportation→Sip on 2027-07-29
        assert by_title["Sip and Paint"]["start_at"].startswith("2027-07-29")
        assert by_title["Transportation Buses to Sip and Paint"]["start_at"].startswith("2027-07-29")
        # Banquet on 2027-07-30
        assert by_title["Banquet"]["start_at"].startswith("2027-07-30")
        # Top Golf + Transportation→Top Golf on 2027-07-31
        assert by_title["Top Golf"]["start_at"].startswith("2027-07-31")
        assert by_title["Transportation Buses to Top Golf"]["start_at"].startswith("2027-07-31")

    def test_ticket_type_flags(self, anniv):
        by_title = {s["title"]: s for s in anniv["subs"]}
        assert by_title["Sip and Paint"]["allows_ticket_types"] is True
        assert by_title["Top Golf"]["allows_ticket_types"] is True
        assert by_title["Banquet"]["allows_ticket_types"] is True
        assert by_title["Transportation Buses to Sip and Paint"]["allows_ticket_types"] is False
        assert by_title["Transportation Buses to Top Golf"]["allows_ticket_types"] is False


# ---------- Role-change gating ----------
class TestRoleChangeGating:
    def test_membership_manager_cannot_change_role_dedicated(self, mm_s, member_id):
        r = mm_s.put(f"{API}/members/{member_id}/role", json={"role": "admin"}, timeout=10)
        assert r.status_code == 403, r.text
        assert "full admin" in r.text.lower() or "only" in r.text.lower()

    def test_membership_manager_cannot_change_role_via_full_put(self, mm_s, member_id):
        r = mm_s.put(f"{API}/members/{member_id}", json={"role": "admin"}, timeout=10)
        assert r.status_code == 403, r.text

    def test_full_admin_can_change_role(self, admin_s, member_id):
        # Set to member (idempotent)
        r = admin_s.put(f"{API}/members/{member_id}/role", json={"role": "member"}, timeout=10)
        assert r.status_code == 200, r.text


# ---------- Profile intake fields ----------
class TestProfileIntakeFields:
    def test_put_me_persists_intake_line_and_completed_at(self, member_s):
        body = {"intake_line": "TEST_IntakeLine_42", "intake_completed_at": "2022-09"}
        r = member_s.put(f"{API}/members/me", json=body, timeout=10)
        assert r.status_code == 200, r.text
        me = member_s.get(f"{API}/auth/me", timeout=10).json()
        assert me.get("intake_line") == "TEST_IntakeLine_42"
        assert me.get("intake_completed_at") == "2022-09"
