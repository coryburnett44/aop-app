"""
Iteration 46: tests for the new email-deliverability / unsubscribe stack:
  - GET /api/email/deliverability (admin-only diag)
  - GET/POST /api/email/unsubscribe?token=...
  - GET /api/email/unsubscribe-status?token=...
  - POST /api/email/resubscribe?token=...
  - resolve_segment filter on /api/email/blast
"""
import os
import re
import base64
import hashlib
import hmac
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")

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
    """Use the admin members list to grab the test 'member@clubhaven.app' record (id + email)."""
    r = admin_session.get(f"{BASE_URL}/api/members", timeout=20)
    assert r.status_code == 200, r.text
    payload = r.json()
    members = payload.get("items", payload) if isinstance(payload, dict) else payload
    for m in members:
        if m.get("email") == MEMBER["email"]:
            return m
    pytest.fail("member@clubhaven.app not found in /api/members")


# ---------- Deliverability diag ----------
class TestDeliverability:
    def test_admin_can_read(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/email/deliverability", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["resend_configured"] is True
        assert d["from"] == "Alpha Omega Phi <info@aop-app.org>"
        assert d["reply_to"] == "info@aop-app.org"
        assert d["sending_domain"] == "aop-app.org"
        assert d["is_resend_sandbox"] is False
        assert isinstance(d["opt_out_count"], int)
        assert isinstance(d["total_with_email"], int)
        assert isinstance(d["dns_checklist"], list)
        assert len(d["dns_checklist"]) == 4
        # DMARC entry should interpolate the real domain
        dmarc = [row for row in d["dns_checklist"] if "DMARC" in row.get("record", "")]
        assert dmarc, "no DMARC row found"
        assert "aop-app.org" in dmarc[0]["value"]

    def test_non_admin_forbidden(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/email/deliverability", timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


# ---------- Unsubscribe redirect ----------
class TestUnsubscribeRedirect:
    def test_get_with_valid_token_redirects_and_writes_db(self, admin_session, member_user):
        uid = member_user["id"]
        token = make_unsub_token(uid)
        r = requests.get(
            f"{BASE_URL}/api/email/unsubscribe?token={token}",
            allow_redirects=False,
            timeout=20,
        )
        assert r.status_code == 302, f"expected 302, got {r.status_code}"
        loc = r.headers.get("location", "")
        assert "/unsubscribed?status=ok" in loc
        assert f"token={token}" in loc

        # Verify DB flip via the status endpoint
        rs = requests.get(f"{BASE_URL}/api/email/unsubscribe-status?token={token}", timeout=20)
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["email"] == MEMBER["email"]
        assert body["opted_out"] is True
        assert body["opted_out_at"]

        # Cleanup — resubscribe so other tests aren't affected
        rr = requests.post(f"{BASE_URL}/api/email/resubscribe?token={token}", timeout=20)
        assert rr.status_code == 200

    def test_post_one_click_path(self, member_user):
        uid = member_user["id"]
        token = make_unsub_token(uid)
        r = requests.post(
            f"{BASE_URL}/api/email/unsubscribe?token={token}",
            allow_redirects=False,
            timeout=20,
        )
        assert r.status_code == 302
        assert "/unsubscribed?status=ok" in r.headers.get("location", "")
        # cleanup
        requests.post(f"{BASE_URL}/api/email/resubscribe?token={token}", timeout=20)

    def test_garbage_token_redirects_invalid(self):
        r = requests.get(
            f"{BASE_URL}/api/email/unsubscribe?token=this-is-garbage-not-a-real-token",
            allow_redirects=False,
            timeout=20,
        )
        assert r.status_code == 302
        assert "/unsubscribed?status=invalid" in r.headers.get("location", "")

    def test_empty_token_redirects_invalid(self):
        r = requests.get(
            f"{BASE_URL}/api/email/unsubscribe?token=",
            allow_redirects=False,
            timeout=20,
        )
        assert r.status_code == 302
        assert "/unsubscribed?status=invalid" in r.headers.get("location", "")


# ---------- Status + Resubscribe ----------
class TestStatusAndResubscribe:
    def test_status_reflects_state(self, member_user):
        uid = member_user["id"]
        token = make_unsub_token(uid)

        # Before opt-out
        before = requests.get(f"{BASE_URL}/api/email/unsubscribe-status?token={token}", timeout=20).json()
        assert before["email"] == MEMBER["email"]
        assert before["opted_out"] is False

        # Opt out
        requests.get(f"{BASE_URL}/api/email/unsubscribe?token={token}", allow_redirects=False, timeout=20)
        mid = requests.get(f"{BASE_URL}/api/email/unsubscribe-status?token={token}", timeout=20).json()
        assert mid["opted_out"] is True

        # Resubscribe via POST
        rr = requests.post(f"{BASE_URL}/api/email/resubscribe?token={token}", timeout=20)
        assert rr.status_code == 200
        assert rr.json() == {"ok": True, "subscribed": True}

        after = requests.get(f"{BASE_URL}/api/email/unsubscribe-status?token={token}", timeout=20).json()
        assert after["opted_out"] is False

    def test_resubscribe_garbage_token_400(self):
        r = requests.post(f"{BASE_URL}/api/email/resubscribe?token=notarealtoken", timeout=20)
        assert r.status_code == 400
        assert "invalid" in r.json().get("detail", "").lower()


# ---------- resolve_segment opt-out filter ----------
class TestBlastSegmentFilter:
    def test_blast_skips_opted_out_member(self, admin_session, member_user):
        """Use segment='custom' targeting only the test member.
        When opted out the filter strips them — resolve_segment becomes empty,
        producing a 400 'no recipients'. That proves the filter without
        having to broadcast to the whole active segment (which 502s)."""
        uid = member_user["id"]
        token = make_unsub_token(uid)
        # opt out
        r = requests.get(f"{BASE_URL}/api/email/unsubscribe?token={token}", allow_redirects=False, timeout=20)
        assert r.status_code == 302

        try:
            payload = {
                "subject": "TEST_iter46 segment filter probe",
                "body_html": "<p>TEST_iter46 filter probe</p>",
                "segment": "custom",
                "custom_user_ids": [uid],
                "test_only": False,
            }
            br = admin_session.post(f"{BASE_URL}/api/email/blast", json=payload, timeout=60)
            # Because the only candidate was filtered out, segment is empty -> 400
            assert br.status_code == 400, f"expected 400 (no recipients after opt-out filter), got {br.status_code}: {br.text}"
            assert "no recipients" in br.text.lower()

            # Now resubscribe and confirm the same blast call would resolve recipients
            requests.post(f"{BASE_URL}/api/email/resubscribe?token={token}", timeout=20)
            preview = admin_session.post(f"{BASE_URL}/api/email/preview", json=payload, timeout=20)
            assert preview.status_code == 200, preview.text
            assert preview.json()["recipient_count"] == 1
        finally:
            # Always re-subscribe in cleanup
            requests.post(f"{BASE_URL}/api/email/resubscribe?token={token}", timeout=20)

    def test_blast_test_only_returns_ok(self, admin_session):
        payload = {
            "subject": "TEST_iter46 test_only probe",
            "body_html": "<p>TEST_iter46 admin-only probe</p>",
            "segment": "active",
            "test_only": True,
        }
        br = admin_session.post(f"{BASE_URL}/api/email/blast", json=payload, timeout=60)
        assert br.status_code == 200, br.text
        data = br.json()
        assert data["sent"] >= 1
        assert data["failed"] == 0

        # Verify the log entry has sent_count==1, failed_count==0
        bl = admin_session.get(f"{BASE_URL}/api/email/blasts", timeout=20).json()
        this = next((b for b in bl if b.get("id") == data["blast_id"]), None)
        assert this
        assert this["sent_count"] == 1
        assert this["failed_count"] == 0
