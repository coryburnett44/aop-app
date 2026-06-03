"""
Phase O — Tests for:
  1. password_reset_tokens MongoDB TTL index
  2. JWT token_version invalidation (access + refresh)
  3. Automated emails CRUD/preview/run-now/permissions
"""
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import jwt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"

# Local mongo for direct DB inspection
mc = MongoClient("mongodb://localhost:27017")
db = mc["clubhaven_db"]


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.cookies.get("access_token") or r.json().get("access_token")
    # also return session for cookie-based access
    return s, token, r.json()


# ---------------------- PASSWORD RESET TTL ----------------------

class TestPasswordResetTTL:
    def test_ttl_index_exists(self):
        idx = list(db.password_reset_tokens.list_indexes())
        ttl_idx = [i for i in idx if i.get("expireAfterSeconds") is not None]
        assert ttl_idx, f"No TTL index on password_reset_tokens. Indexes: {idx}"
        # should be on expires_at_dt with expireAfterSeconds=60
        found = False
        for i in ttl_idx:
            keys = list(i.get("key", {}).keys())
            if "expires_at_dt" in keys and i.get("expireAfterSeconds") == 60:
                found = True
                break
        assert found, f"TTL index not on expires_at_dt w/ 60s. Found: {ttl_idx}"

    def test_insert_expired_token_persists_in_collection(self):
        """Insert an already-expired doc. We won't wait for sweep (~60s) since the
        TTL monitor runs every 60s in MongoDB. Just verify insert + format is right."""
        tok = f"TEST_expired_{uuid.uuid4().hex[:8]}"
        db.password_reset_tokens.insert_one({
            "token": tok,
            "user_id": "TEST_ttl_user",
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
            "expires_at_dt": datetime.now(timezone.utc) - timedelta(minutes=2),
            "used": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        doc = db.password_reset_tokens.find_one({"token": tok})
        assert doc is not None
        assert isinstance(doc["expires_at_dt"], datetime)
        # cleanup ourselves so we don't depend on sweep
        db.password_reset_tokens.delete_one({"token": tok})


# ---------------------- TOKEN VERSION INVALIDATION ----------------------

@pytest.fixture(scope="class")
def test_user():
    """Create a fresh user so we can mutate token_version safely without
    breaking other shared accounts."""
    email = f"test_tv_{uuid.uuid4().hex[:8]}@test.com"
    pw = "OrigPass123!"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": pw, "name": "TV Test User",
    }, timeout=20)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    yield {"email": email, "password": pw, "data": r.json()}
    # cleanup
    db.users.delete_many({"email": email})
    db.password_reset_tokens.delete_many({"user_id": r.json().get("user", {}).get("id")})


class TestTokenVersion:
    def test_register_jwt_has_tv_zero(self, test_user):
        # login again to get token explicitly
        s, token, body = _login(test_user["email"], test_user["password"])
        assert token, "no access_token"
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload.get("tv") == 0, f"expected tv=0, got {payload.get('tv')}. payload={payload}"
        # verify db says token_version=0 too
        u = db.users.find_one({"email": test_user["email"]})
        assert int(u.get("token_version", 0)) == 0

    def test_old_token_rejected_after_password_reset(self, test_user):
        # Login first → get old access token
        s_old, old_token, _ = _login(test_user["email"], test_user["password"])
        old_refresh = s_old.cookies.get("refresh_token")

        # Verify /auth/me works with old token
        r = requests.get(f"{API}/auth/me", cookies={"access_token": old_token}, timeout=10)
        assert r.status_code == 200

        # Forgot password
        r = requests.post(f"{API}/auth/forgot-password", json={"email": test_user["email"]}, timeout=10)
        assert r.status_code == 200

        # Fetch reset token directly from DB
        u = db.users.find_one({"email": test_user["email"]})
        tdoc = db.password_reset_tokens.find_one({"user_id": u["id"], "used": False}, sort=[("created_at", -1)])
        assert tdoc, "no reset token created"

        new_password = "NewPass456!"
        r = requests.post(f"{API}/auth/reset-password", json={
            "token": tdoc["token"], "new_password": new_password,
        }, timeout=10)
        assert r.status_code == 200, f"reset failed: {r.status_code} {r.text}"
        test_user["password"] = new_password

        # DB token_version should now be 1
        u2 = db.users.find_one({"email": test_user["email"]})
        assert int(u2.get("token_version", 0)) == 1, f"expected tv=1, got {u2.get('token_version')}"

        # OLD access token must now return 401
        r = requests.get(f"{API}/auth/me", cookies={"access_token": old_token}, timeout=10)
        assert r.status_code == 401, f"expected 401 for stale token, got {r.status_code} {r.text}"
        assert "session expired" in (r.json().get("detail") or "").lower() or "expired" in (r.json().get("detail") or "").lower()

        # Save refresh token for next test
        test_user["_old_refresh"] = old_refresh

    def test_old_refresh_token_rejected(self, test_user):
        old_refresh = test_user.get("_old_refresh")
        if not old_refresh:
            pytest.skip("no old refresh token captured")
        r = requests.post(f"{API}/auth/refresh", cookies={"refresh_token": old_refresh}, timeout=10)
        assert r.status_code == 401, f"old refresh should be rejected, got {r.status_code} {r.text}"

    def test_fresh_login_issues_token_tv_one(self, test_user):
        s, token, _ = _login(test_user["email"], test_user["password"])
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload.get("tv") == 1, f"expected tv=1 after reset, got {payload.get('tv')}"
        # works on /auth/me
        r = requests.get(f"{API}/auth/me", cookies={"access_token": token}, timeout=10)
        assert r.status_code == 200


# ---------------------- AUTOMATED EMAILS ----------------------

@pytest.fixture(scope="class")
def admin_session():
    s, token, _ = _login(ADMIN_EMAIL, ADMIN_PASS)
    return s


@pytest.fixture(scope="class")
def member_session():
    s, token, _ = _login(MEMBER_EMAIL, MEMBER_PASS)
    return s


class TestAutomatedEmails:
    custom_id = None

    def test_list_has_builtin(self, admin_session):
        r = admin_session.get(f"{API}/automated-emails", timeout=10)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        builtin = [x for x in items if x.get("id") == "builtin_weekly_digest"]
        assert builtin, f"builtin_weekly_digest missing. ids={[x.get('id') for x in items]}"
        b = builtin[0]
        assert b["is_builtin"] is True
        # cron may have been altered by prior runs; just sanity-check it's 5 parts
        assert len(b["cron_expression"].split()) == 5, f"bad cron: {b['cron_expression']}"
        assert b.get("next_run_at"), "next_run_at empty"

    def test_member_forbidden(self, member_session):
        r = member_session.get(f"{API}/automated-emails", timeout=10)
        assert r.status_code == 403

    def test_create_invalid_cron(self, admin_session):
        r = admin_session.post(f"{API}/automated-emails", json={
            "name": "TEST_bad_cron", "subject": "x", "body_html": "<p>x</p>",
            "cron_expression": "NOT A CRON",
            "is_active": True, "audience": {"type": "all", "ids": []}, "sections": {},
        }, timeout=10)
        assert r.status_code == 400, r.text

    def test_create_valid(self, admin_session):
        payload = {
            "name": "TEST_phase_o_campaign",
            "subject": "Hi {{member_name}}",
            "body_html": "<p>Hello {{member_name}}</p>{{upcoming_events}}",
            "cron_expression": "0 10 * * 1,3,5",  # mon, wed, fri
            "is_active": True,
            "audience": {"type": "all", "ids": []},
            "sections": {"events": True, "photos": False},
        }
        r = admin_session.post(f"{API}/automated-emails", json=payload, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == payload["name"]
        assert d["cron_expression"] == payload["cron_expression"]
        assert d.get("next_run_at"), "next_run_at not computed"
        assert d.get("is_builtin") is False
        TestAutomatedEmails.custom_id = d["id"]

    def test_update_builtin(self, admin_session):
        new_subject = "Updated digest subject"
        body = {
            "name": "Weekly Digest",
            "subject": new_subject,
            "body_html": "<p>Hi {{member_name}}</p>",
            "cron_expression": "0 8 * * 1",  # changed hour
            "is_active": True,
            "audience": {"type": "all", "ids": []},
            "sections": {"events": True, "photos": True, "documents": False},
        }
        r = admin_session.put(f"{API}/automated-emails/builtin_weekly_digest", json=body, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["subject"] == new_subject
        assert d["cron_expression"] == "0 8 * * 1"
        assert d["sections"]["documents"] is False
        # Verify persistence via GET list
        r2 = admin_session.get(f"{API}/automated-emails", timeout=10)
        b = [x for x in r2.json() if x["id"] == "builtin_weekly_digest"][0]
        assert b["subject"] == new_subject
        assert b["sections"]["documents"] is False

    def test_delete_builtin_forbidden(self, admin_session):
        r = admin_session.delete(f"{API}/automated-emails/builtin_weekly_digest", timeout=10)
        assert r.status_code == 400
        assert "deleted" in r.text.lower() and "built-in" in r.text.lower()

    def test_preview_substitutes_merge_tags(self, admin_session):
        # Set subject containing a merge tag to test subject substitution per spec
        body = {
            "name": "Weekly Digest",
            "subject": "Hi {{member_name}}, here's your digest",
            "body_html": "<p>Hi {{member_name}}</p>{{upcoming_events}}{{new_photos}}{{new_documents}}{{new_members}}{{my_rsvps}}{{pending_hours}}{{birthday_greeting}}",
            "cron_expression": "0 9 * * 1",
            "is_active": True,
            "audience": {"type": "all", "ids": []},
            "sections": {"events": True, "photos": True, "documents": True, "new_members": True, "my_rsvps": True, "pending_hours": True, "birthday_greeting": True},
        }
        ur = admin_session.put(f"{API}/automated-emails/builtin_weekly_digest", json=body, timeout=10)
        assert ur.status_code == 200, ur.text

        r = admin_session.post(f"{API}/automated-emails/builtin_weekly_digest/preview", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "subject" in d and "body_html" in d
        # raw merge tags should no longer appear in body_html
        for tag in ["{{member_name}}", "{{upcoming_events}}", "{{new_photos}}", "{{new_documents}}",
                    "{{new_members}}", "{{my_rsvps}}", "{{pending_hours}}", "{{birthday_greeting}}"]:
            assert tag not in d["body_html"], f"unresolved merge tag {tag} in body_html"
        # subject merge tag substitution — per spec the {{member_name}} should be replaced
        u = db.users.find_one({"email": ADMIN_EMAIL})
        first = (u.get("name") or "Member").split(" ")[0] if u else "Member"
        assert "{{member_name}}" not in d["subject"], (
            f"Spec: preview should substitute {{member_name}} in subject too. Got subject='{d['subject']}'"
        )
        assert first in d["subject"], f"admin first name '{first}' not in subject '{d['subject']}'"

    def test_run_now_returns_count(self, admin_session):
        r = admin_session.post(f"{API}/automated-emails/builtin_weekly_digest/run-now", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sent" in d
        assert isinstance(d["sent"], int)

    def test_delete_custom_campaign(self, admin_session):
        cid = TestAutomatedEmails.custom_id
        if not cid:
            pytest.skip("no custom campaign created")

        r = admin_session.delete(f"{API}/automated-emails/{cid}", timeout=10)
        assert r.status_code == 200, r.text
        # verify gone
        r2 = admin_session.get(f"{API}/automated-emails", timeout=10)
        ids = [x["id"] for x in r2.json()]
        assert cid not in ids


    def test_zz_restore_builtin_defaults(self, admin_session):
        """Restore the built-in Weekly Digest to factory defaults for next iteration."""
        default_body = """<div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#f7f5f0">
  <h1 style="color:#0A2463;margin:0 0 4px;font-size:28px">Good morning, {{member_name}}</h1>
  <p style="color:#666;font-size:14px">Here's what's happening this week in Alpha Omega Phi.</p>
  {{birthday_greeting}}
  {{my_rsvps}}
  {{upcoming_events}}
  {{new_photos}}
  {{new_documents}}
  {{new_members}}
  {{pending_hours}}
  <p style="font-size:12px;color:#888;margin-top:24px">You're receiving this because you're a member of Alpha Omega Phi. Replies go to info@aop-app.org.</p>
</div>"""
        body = {
            "name": "Weekly Digest",
            "subject": "Your AOP weekly digest — {{member_name}}",
            "body_html": default_body,
            "cron_expression": "0 9 * * 1",
            "is_active": True,
            "audience": {"type": "all", "ids": []},
            "sections": {"events": True, "photos": True, "documents": True, "new_members": True, "my_rsvps": True, "pending_hours": True, "birthday_greeting": True},
        }
        r = admin_session.put(f"{API}/automated-emails/builtin_weekly_digest", json=body, timeout=10)
        assert r.status_code == 200, r.text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
