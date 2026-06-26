"""
Iteration 47: tests for the new member-facing email preferences:
  - GET  /api/me/email-preferences
  - PUT  /api/me/email-preferences  (per-category toggles + master kill switch + implicit re-subscribe)
  - resolve_segment per-category (email_prefs.blasts) filter on /api/email/blast
  - public_user() exposes email_opt_out + email_prefs
  - dues-reminder cron query construction (inspect via grep — not callable directly)
"""
import os
import re
import base64
import hashlib
import hmac
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/")

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}

# JWT_SECRET from /app/backend/.env (UNSUBSCRIBE_SECRET defaults to JWT_SECRET)
JWT_SECRET = "3c2e4d0174b499e2b5aacf364bac1d87f5541764c0f3d9d62ec8b4c05cd8a0b0"


def make_unsub_token(user_id: str, secret: str = JWT_SECRET) -> str:
    sig = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).digest()
    blob = user_id.encode() + b"." + base64.urlsafe_b64encode(sig)[:16]
    return base64.urlsafe_b64encode(blob).decode().rstrip("=")


def login_session(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return login_session(ADMIN)


@pytest.fixture(scope="module")
def member_session():
    return login_session(MEMBER)


@pytest.fixture(scope="module")
def member_user(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/members", timeout=20)
    assert r.status_code == 200, r.text
    payload = r.json()
    members = payload.get("items", payload) if isinstance(payload, dict) else payload
    for m in members:
        if m.get("email") == MEMBER["email"]:
            return m
    pytest.fail("member@clubhaven.app not found in /api/members")


def _reset_prefs(member_session):
    """Reset member back to a clean opted-in state."""
    member_session.put(
        f"{BASE_URL}/api/me/email-preferences",
        json={"blasts": True, "dues_reminders": True, "email_opt_out": False},
        timeout=20,
    )


@pytest.fixture(autouse=True)
def _cleanup(member_session):
    yield
    try:
        _reset_prefs(member_session)
    except Exception:
        pass


# ---------- GET /api/me/email-preferences ----------
class TestGetEmailPreferences:
    def test_unauth_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/me/email-preferences", timeout=20)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"

    def test_fresh_user_defaults_opted_in(self, member_session):
        _reset_prefs(member_session)
        r = member_session.get(f"{BASE_URL}/api/me/email-preferences", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email_opt_out"] is False
        assert data["email_prefs"]["blasts"] is True
        assert data["email_prefs"]["dues_reminders"] is True


# ---------- PUT /api/me/email-preferences ----------
class TestPutEmailPreferences:
    def test_unauth_returns_401(self):
        r = requests.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"blasts": False},
            timeout=20,
        )
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"

    def test_toggle_blasts_off_persists(self, member_session):
        _reset_prefs(member_session)
        r = member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"blasts": False},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["email_opt_out"] is False
        assert data["email_prefs"]["blasts"] is False
        assert data["email_prefs"]["dues_reminders"] is True

        # Verify persistence via subsequent GET
        g = member_session.get(f"{BASE_URL}/api/me/email-preferences", timeout=20).json()
        assert g["email_opt_out"] is False
        assert g["email_prefs"]["blasts"] is False
        assert g["email_prefs"]["dues_reminders"] is True

    def test_master_kill_switch_sets_opt_out(self, member_session):
        _reset_prefs(member_session)
        r = member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"email_opt_out": True},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email_opt_out"] is True

        g = member_session.get(f"{BASE_URL}/api/me/email-preferences", timeout=20).json()
        assert g["email_opt_out"] is True
        assert g.get("email_opt_out_at") is not None and len(g["email_opt_out_at"]) > 0

    def test_implicit_resubscribe_when_re_enabling_category(self, member_session):
        """If user is opted out (master kill on) and PUT comes in WITHOUT
        email_opt_out but with blasts=true OR dues_reminders=true, the backend
        must auto-clear email_opt_out."""
        # 1. Put user into opted-out state
        member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"email_opt_out": True},
            timeout=20,
        )
        g0 = member_session.get(f"{BASE_URL}/api/me/email-preferences", timeout=20).json()
        assert g0["email_opt_out"] is True

        # 2. Re-enable blasts (no explicit email_opt_out passed) → should auto-clear opt_out
        r = member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"blasts": True, "dues_reminders": True},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email_opt_out"] is False, "implicit re-subscribe failed: email_opt_out should auto-clear"
        assert data["email_prefs"]["blasts"] is True

        # 3. Re-fetch to confirm persistence
        g1 = member_session.get(f"{BASE_URL}/api/me/email-preferences", timeout=20).json()
        assert g1["email_opt_out"] is False

    def test_explicit_opt_out_overrides_implicit_resubscribe(self, member_session):
        """If email_opt_out is explicitly True in body, do NOT auto-clear."""
        _reset_prefs(member_session)
        r = member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"blasts": True, "dues_reminders": True, "email_opt_out": True},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["email_opt_out"] is True


# ---------- public_user() exposes new fields ----------
class TestPublicUserShape:
    def test_auth_me_includes_email_prefs(self, member_session):
        _reset_prefs(member_session)
        r = member_session.get(f"{BASE_URL}/api/auth/me", timeout=20)
        assert r.status_code == 200, r.text
        u = r.json()
        # public_user() shape
        assert "email_opt_out" in u, "auth/me missing email_opt_out"
        assert "email_prefs" in u, "auth/me missing email_prefs"
        assert "blasts" in u["email_prefs"]
        assert "dues_reminders" in u["email_prefs"]
        assert u["email_opt_out"] is False
        assert u["email_prefs"]["blasts"] is True
        assert u["email_prefs"]["dues_reminders"] is True


# ---------- resolve_segment per-category filter ----------
class TestResolveSegmentCategoryFilter:
    def test_blast_filtered_when_master_kill_on(self, admin_session, member_session, member_user):
        """Master kill switch should exclude the member from blast resolution."""
        uid = member_user["id"]
        # opt out via master kill (PUT — uses cookie-auth as member)
        member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"email_opt_out": True},
            timeout=20,
        )
        payload = {
            "subject": "TEST_iter47 segment probe (master kill)",
            "body_html": "<p>TEST_iter47</p>",
            "segment": "custom",
            "custom_user_ids": [uid],
            "test_only": False,
        }
        br = admin_session.post(f"{BASE_URL}/api/email/blast", json=payload, timeout=60)
        assert br.status_code == 400, f"expected 400 (filtered out by master kill), got {br.status_code}: {br.text}"
        assert "no recipients" in br.text.lower()

        # Re-subscribe via PUT
        member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"blasts": True, "dues_reminders": True, "email_opt_out": False},
            timeout=20,
        )

    def test_blast_filtered_when_blasts_category_off(self, admin_session, member_session, member_user):
        """Per-category filter: email_prefs.blasts=false (without master kill)
        should still exclude the member from blast resolution."""
        uid = member_user["id"]
        # Ensure opted-in master, but blasts category OFF
        member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"blasts": False, "dues_reminders": True, "email_opt_out": False},
            timeout=20,
        )
        # Confirm state
        g = member_session.get(f"{BASE_URL}/api/me/email-preferences", timeout=20).json()
        assert g["email_opt_out"] is False
        assert g["email_prefs"]["blasts"] is False

        payload = {
            "subject": "TEST_iter47 segment probe (category off)",
            "body_html": "<p>TEST_iter47</p>",
            "segment": "custom",
            "custom_user_ids": [uid],
            "test_only": False,
        }
        br = admin_session.post(f"{BASE_URL}/api/email/blast", json=payload, timeout=60)
        assert br.status_code == 400, f"expected 400 (per-category filter), got {br.status_code}: {br.text}"
        assert "no recipients" in br.text.lower()

        # Restore: turn blasts back on, verify preview now resolves
        member_session.put(
            f"{BASE_URL}/api/me/email-preferences",
            json={"blasts": True, "dues_reminders": True, "email_opt_out": False},
            timeout=20,
        )
        preview = admin_session.post(f"{BASE_URL}/api/email/preview", json=payload, timeout=20)
        assert preview.status_code == 200, preview.text
        assert preview.json()["recipient_count"] == 1


# ---------- Dues-reminder cron query construction (static inspection) ----------
class TestDuesReminderCronQueryStatic:
    def test_dues_cron_query_uses_email_prefs_filter(self):
        """We can't trigger the dues-reminder cron directly without scheduler
        plumbing — so verify the mongo query includes the new
        `email_prefs.dues_reminders: {$ne: False}` clause AND the existing
        `email_opt_out: {$ne: True}` clause. The query lives in
        routes/automated_emails.py since the dues cadence was modularised."""
        with open("/app/backend/routes/automated_emails.py", "r") as f:
            src = f.read()
        # Strip whitespace for robustness
        compact = re.sub(r"\s+", "", src)
        assert '"email_opt_out":{"$ne":True}' in compact, (
            "dues cron query missing email_opt_out filter"
        )
        assert '"email_prefs.dues_reminders":{"$ne":False}' in compact, (
            "dues cron query missing email_prefs.dues_reminders filter"
        )

    def test_resolve_segment_query_uses_email_prefs_blasts(self):
        """Verify resolve_segment filters out members where
        email_prefs.blasts is False. The segment helper lives in
        routes/email.py since the email-blast extraction."""
        with open("/app/backend/routes/email.py", "r") as f:
            src = f.read()
        compact = re.sub(r"\s+", "", src)
        assert '"email_prefs.blasts"={"$ne":False}' in compact or \
               '"email_prefs.blasts":{"$ne":False}' in compact or \
               'q["email_prefs.blasts"]={"$ne":False}' in compact, (
            "resolve_segment missing email_prefs.blasts filter"
        )
