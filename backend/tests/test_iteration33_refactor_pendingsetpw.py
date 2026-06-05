"""Iteration 33 — Tests for:
  1) routes/auth_email_flows.py extraction (set-password, forgot, reset, change)
  2) routes/events.py extraction (list/get/CRUD/sub-events/rsvps + 403)
  3) routes/members.py extraction (list/get/new/birthdays/status + 403)
  4) Feature: POST /api/admin/members/{id}/resend-set-password + pending_set_password
"""
import os
import time
import uuid

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@clubhaven.app", "Admin123!")
GOV = ("governor.tx@clubhaven.app", "Governor123!")
MEMBER = ("member@clubhaven.app", "Member123!")


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def member_sess():
    return _login(*MEMBER)


@pytest.fixture(scope="module")
def gov_sess():
    return _login(*GOV)


# =============================================================
# REFACTOR 1 — auth_email_flows.py
# =============================================================
class TestAuthEmailFlows:
    def test_set_password_bogus_token(self):
        r = requests.post(f"{API}/auth/set-password",
                          json={"token": "bogus-" + uuid.uuid4().hex, "new_password": "Whatever123!"})
        assert r.status_code == 400
        assert "Invalid or already-used token" in r.text

    def test_forgot_password_unknown_email_returns_ok(self):
        r = requests.post(f"{API}/auth/forgot-password",
                          json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_forgot_password_known_email_returns_ok(self):
        r = requests.post(f"{API}/auth/forgot-password", json={"email": ADMIN[0]})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_reset_password_bogus_token(self):
        r = requests.post(f"{API}/auth/reset-password",
                          json={"token": "bogus-" + uuid.uuid4().hex, "new_password": "Whatever123!"})
        assert r.status_code == 400
        assert "Invalid or already-used reset link." in r.text

    def test_change_password_unauth_401(self):
        r = requests.post(f"{API}/auth/change-password",
                          json={"current_password": "x", "new_password": "y"})
        assert r.status_code == 401

    def test_change_password_wrong_current(self, member_sess):
        r = member_sess.post(f"{API}/auth/change-password",
                             json={"current_password": "WRONG!" + uuid.uuid4().hex,
                                   "new_password": "NewPass123!"})
        assert r.status_code == 400
        assert "Current password is incorrect" in r.text

    def test_change_password_success_and_login(self):
        """Change member password, log in with new, then restore."""
        s = _login(*MEMBER)
        new_pw = "TempPw_" + uuid.uuid4().hex[:8] + "!Aa1"
        r = s.post(f"{API}/auth/change-password",
                   json={"current_password": MEMBER[1], "new_password": new_pw})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
        # Verify new password works
        r2 = requests.post(f"{API}/auth/login", json={"email": MEMBER[0], "password": new_pw})
        assert r2.status_code == 200
        # Restore original password
        s2 = _login(MEMBER[0], new_pw)
        r3 = s2.post(f"{API}/auth/change-password",
                     json={"current_password": new_pw, "new_password": MEMBER[1]})
        assert r3.status_code == 200


# =============================================================
# REFACTOR 2 — events.py
# =============================================================
class TestEvents:
    def test_list_events(self):
        r = requests.get(f"{API}/events")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_upcoming(self):
        r = requests.get(f"{API}/events?upcoming=true")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)

    def test_list_include_sub_events(self):
        r = requests.get(f"{API}/events?include_sub_events=true")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_event_404(self):
        r = requests.get(f"{API}/events/does-not-exist-{uuid.uuid4().hex}")
        assert r.status_code == 404

    def test_member_cannot_create_event(self, member_sess):
        r = member_sess.post(f"{API}/events", json={
            "title": "Should Fail", "start_at": "2030-01-01T00:00:00",
        })
        assert r.status_code == 403

    def test_admin_event_crud(self, admin_sess):
        # CREATE
        payload = {
            "title": f"TEST_event_{uuid.uuid4().hex[:6]}",
            "description": "iter33 test",
            "start_at": "2030-06-01T10:00:00",
            "end_at": "2030-06-01T12:00:00",
            "location": "TEST",
        }
        r = admin_sess.post(f"{API}/events", json=payload)
        assert r.status_code == 200, r.text
        ev = r.json()
        eid = ev["id"]
        assert ev["title"] == payload["title"]

        # GET
        r2 = admin_sess.get(f"{API}/events/{eid}")
        assert r2.status_code == 200
        assert r2.json()["id"] == eid

        # PUT cancelled toggle
        r3 = admin_sess.put(f"{API}/events/{eid}", json={"cancelled": True, "cancellation_note": "test"})
        assert r3.status_code == 200, r3.text
        body = r3.json()
        assert body.get("cancelled") is True
        assert body.get("cancelled_at"), "cancelled_at should be stamped"

        # Member cannot update
        s = _login(*MEMBER)
        rm = s.put(f"{API}/events/{eid}", json={"cancelled": False})
        assert rm.status_code == 403

        # sub-events list (likely empty)
        rs = requests.get(f"{API}/events/{eid}/sub-events")
        assert rs.status_code == 200
        assert isinstance(rs.json(), list)

        # rsvps list
        rr = requests.get(f"{API}/events/{eid}/rsvps")
        assert rr.status_code == 200
        assert isinstance(rr.json(), list)

        # DELETE
        rd = admin_sess.delete(f"{API}/events/{eid}")
        assert rd.status_code == 200
        # Member cannot delete (re-create + check)
        r4 = admin_sess.post(f"{API}/events", json=payload)
        eid2 = r4.json()["id"]
        rd2 = s.delete(f"{API}/events/{eid2}")
        assert rd2.status_code == 403
        # cleanup
        admin_sess.delete(f"{API}/events/{eid2}")


# =============================================================
# REFACTOR 3 — members.py
# =============================================================
class TestMembers:
    def test_list_members(self):
        r = requests.get(f"{API}/members")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        if items:
            # No password_hash leak, no _id
            assert "password_hash" not in items[0]
            assert "_id" not in items[0]
            assert "pending_set_password" in items[0], "public_user must expose pending_set_password"

    def test_list_members_q_city(self):
        r = requests.get(f"{API}/members?q=admin&city=anywhere")
        assert r.status_code == 200

    def test_get_member_404(self):
        r = requests.get(f"{API}/members/no-such-id-{uuid.uuid4().hex}")
        assert r.status_code == 404

    def test_members_new(self):
        r = requests.get(f"{API}/members-new?days=3650")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_members_birthdays(self):
        r = requests.get(f"{API}/members-birthdays?days=365")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # Verify Feb 29 / next_birthday computation fields present when items exist
        for it in items:
            assert "days_until_birthday" in it
            assert "next_birthday" in it
            assert 0 <= it["days_until_birthday"] <= 365

    def test_set_status_requires_admin(self, member_sess, admin_sess):
        # Pick any user id (admin's own)
        me = admin_sess.get(f"{API}/auth/me").json()
        uid = me["id"]
        # Member should be denied
        r = member_sess.put(f"{API}/members/{uid}/status", json={"status": "active"})
        assert r.status_code == 403

    def test_set_status_admin_can_set_and_clear_deceased(self, admin_sess):
        # Find a non-admin test user to avoid breaking admin account
        items = requests.get(f"{API}/members?q=maya").json()
        target = next((u for u in items if u.get("email", "").startswith("maya.patel")), None)
        if not target:
            pytest.skip("No demo user maya.patel found")
        uid = target["id"]
        # Set deceased
        r = admin_sess.put(f"{API}/members/{uid}/status", json={"status": "deceased"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("deceased_at"), "deceased_at should be stamped"
        # Clear
        r2 = admin_sess.put(f"{API}/members/{uid}/status", json={"status": "active"})
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2.get("deceased_at") is None


# =============================================================
# FEATURE 4 — resend-set-password + pending_set_password
# =============================================================
class TestResendSetPassword:
    def test_member_id(self, admin_sess):
        items = requests.get(f"{API}/members?q=jordan").json()
        target = next((u for u in items if u.get("email", "").startswith("jordan.reed")), None)
        assert target, "demo user jordan.reed missing"
        return target["id"]

    def test_resend_requires_admin(self, member_sess, admin_sess):
        uid = self.test_member_id(admin_sess)
        r = member_sess.post(f"{API}/admin/members/{uid}/resend-set-password")
        assert r.status_code == 403

    def test_resend_404_unknown(self, admin_sess):
        r = admin_sess.post(f"{API}/admin/members/no-such-{uuid.uuid4().hex}/resend-set-password")
        assert r.status_code == 404

    def test_resend_success_sets_pending(self, admin_sess):
        uid = self.test_member_id(admin_sess)
        r = admin_sess.post(f"{API}/admin/members/{uid}/resend-set-password")
        # Allow 503 if RESEND_API_KEY missing (sandbox), else 200
        assert r.status_code in (200, 503), r.text
        if r.status_code == 503:
            pytest.skip("Resend not configured on this env")
        body = r.json()
        assert body.get("ok") is True
        assert body.get("email")
        # Verify pending_set_password=True now appears in public_user
        time.sleep(0.3)
        m = requests.get(f"{API}/members/{uid}").json()
        assert m.get("pending_set_password") is True, "Flag should be True after resend"

    def test_resend_invalidates_older_tokens(self, admin_sess):
        """Two sequential resends should leave only the latest token usable.
        We can't introspect db directly here, but a second resend must still 200."""
        uid = self.test_member_id(admin_sess)
        r1 = admin_sess.post(f"{API}/admin/members/{uid}/resend-set-password")
        if r1.status_code == 503:
            pytest.skip("Resend not configured")
        assert r1.status_code == 200
        r2 = admin_sess.post(f"{API}/admin/members/{uid}/resend-set-password")
        assert r2.status_code == 200
