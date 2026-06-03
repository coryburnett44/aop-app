"""Iteration 25 tests:
   - Auth route extraction (login/logout/me/refresh/register)
   - Zeffy receipt validation + confirm + admin approve
   - Smoke check unmoved endpoints
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


def _login(payload):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=payload, timeout=20)
    return s, r


# ------------- AUTH ----------------
class TestAuthLogin:
    def test_login_with_email_admin(self):
        s, r = _login(ADMIN)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("access_token", "refresh_token", "id", "email", "role"):
            assert k in d, f"missing {k}"
        assert d["email"] == ADMIN["email"]
        assert d["role"] == "admin"
        # cookies set
        assert "access_token" in s.cookies or "refresh_token" in s.cookies

    def test_login_with_email_member(self):
        _, r = _login(MEMBER)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "member"
        assert d["access_token"]

    def test_login_wrong_password(self):
        # unique identifier so we don't accidentally trip lockout for real users
        _, r = _login({"email": "admin@clubhaven.app", "password": "WRONG_PWD_!!"})
        assert r.status_code in (401, 429)
        if r.status_code == 401:
            assert "Invalid email/username" in r.json().get("detail", "")

    def test_login_with_username_case_insensitive(self):
        # First get admin's username (if any). The seed admin may not have username.
        # We'll attempt with the local part of the email lowercased as best-effort
        # and accept either success or 401 (depending on whether username field is set).
        s, r = _login(ADMIN)
        assert r.status_code == 200
        uname = r.json().get("username")
        if not uname:
            pytest.skip("admin user has no username set — skipping username login check")
        _, r2 = _login({"email": uname.upper(), "password": ADMIN["password"]})
        assert r2.status_code == 200, r2.text
        assert r2.json()["email"] == ADMIN["email"]


class TestAuthMeLogoutRefresh:
    def test_me_with_cookie(self):
        s, r = _login(ADMIN)
        assert r.status_code == 200
        m = s.get(f"{API}/auth/me", timeout=20)
        assert m.status_code == 200, m.text
        assert m.json()["email"] == ADMIN["email"]

    def test_me_without_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 401

    def test_logout_clears_cookies(self):
        s, r = _login(ADMIN)
        assert r.status_code == 200
        lo = s.post(f"{API}/auth/logout", timeout=20)
        assert lo.status_code == 200, lo.text
        assert lo.json() == {"ok": True}
        # After logout /me should 401 (cookies cleared on server response)
        me2 = requests.get(f"{API}/auth/me", timeout=20)
        assert me2.status_code == 401

    def test_logout_requires_auth(self):
        r = requests.post(f"{API}/auth/logout", timeout=20)
        assert r.status_code == 401

    def test_refresh_via_cookie(self):
        s, r = _login(ADMIN)
        assert r.status_code == 200
        rf = s.post(f"{API}/auth/refresh", timeout=20)
        assert rf.status_code == 200, rf.text
        d = rf.json()
        assert d.get("access_token") and d.get("refresh_token")

    def test_refresh_via_json_body(self):
        _, r = _login(ADMIN)
        token = r.json()["refresh_token"]
        rf = requests.post(f"{API}/auth/refresh", json={"refresh_token": token}, timeout=20)
        assert rf.status_code == 200, rf.text
        assert rf.json().get("access_token")

    def test_refresh_via_bearer(self):
        _, r = _login(ADMIN)
        token = r.json()["refresh_token"]
        rf = requests.post(f"{API}/auth/refresh",
                           headers={"Authorization": f"Bearer {token}"}, timeout=20)
        assert rf.status_code == 200, rf.text
        assert rf.json().get("access_token")

    def test_refresh_without_token(self):
        rf = requests.post(f"{API}/auth/refresh", timeout=20)
        assert rf.status_code == 401


class TestAuthRegister:
    def test_register_duplicate_email(self):
        r = requests.post(f"{API}/auth/register",
                          json={"email": ADMIN["email"], "password": "Whatever123!", "name": "Dup"},
                          timeout=20)
        assert r.status_code == 400

    def test_register_creates_user(self):
        uniq = f"test_iter25_{int(time.time())}@example.com"
        r = requests.post(f"{API}/auth/register",
                          json={"email": uniq, "password": "Pass123!", "name": "Iter25 Tester"},
                          timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("access_token", "refresh_token", "verify_link", "id", "email"):
            assert k in d, f"missing {k}"
        # cleanup — best effort: log in as admin and delete the user
        try:
            sa, _ = _login(ADMIN)
            sa.delete(f"{API}/members/{d['id']}", timeout=20)
        except Exception:
            pass


class TestBruteForceLockout:
    def test_5_fails_lock(self):
        # Use a deliberately-fresh identifier so we don't lock out real users.
        unique_email = f"nonexistent_iter25_{int(time.time())}@example.com"
        last = None
        for _ in range(5):
            _, last = _login({"email": unique_email, "password": "bad"})
            assert last.status_code in (401, 429)
        # 6th attempt should be 429
        _, r6 = _login({"email": unique_email, "password": "bad"})
        assert r6.status_code == 429, r6.text
        assert "Too many attempts" in r6.json().get("detail", "")
        # cleanup the attempt doc so a re-run starts clean — we just leave it; key uses ip+email
        # Real test users were not used so no impact.


# ---------- ZEFFY ----------
class TestZeffy:
    def setup_method(self):
        self.s_admin, ra = _login(ADMIN)
        assert ra.status_code == 200
        self.admin = ra.json()
        self.s_member, rm = _login(MEMBER)
        assert rm.status_code == 200
        self.member = rm.json()
        # ensure trust_zeffy starts false
        self.s_admin.put(f"{API}/members/{self.member['id']}", json={"trust_zeffy": False}, timeout=20)

    def test_zeffy_config(self):
        r = self.s_member.get(f"{API}/payments/zeffy/config", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["enabled"] is True
        assert d["currency"] == "USD"
        assert d["default_amount"] > 0
        assert d["url"].startswith("http")

    def test_validate_formats(self):
        cases = [
            ("RCT-0401-5406", True, "rct"),
            ("ZF-ABC123", True, "zf"),
            ("donor@example.com", True, "email"),
            ("ABC123DEF456", True, "alnum"),
            ("hello", False, None),
            ("fake receipt text", False, None),
        ]
        for val, valid, fmt in cases:
            r = self.s_member.get(f"{API}/payments/zeffy/validate", params={"value": val}, timeout=20)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["valid"] is valid, f"{val} -> {d}"
            assert d["format"] == fmt, f"{val} -> {d}"

    def test_will_auto_approve_flag(self):
        # untrusted member
        r = self.s_member.get(f"{API}/payments/zeffy/validate", params={"value": "RCT-0401-5406"}, timeout=20)
        assert r.json()["will_auto_approve"] is False
        # admin flips trust on
        u = self.s_admin.put(f"{API}/members/{self.member['id']}",
                             json={"trust_zeffy": True}, timeout=20)
        assert u.status_code == 200, u.text
        # member re-checks
        r2 = self.s_member.get(f"{API}/payments/zeffy/validate", params={"value": "RCT-0401-5406"}, timeout=20)
        assert r2.json()["will_auto_approve"] is True
        # turn off again
        self.s_admin.put(f"{API}/members/{self.member['id']}", json={"trust_zeffy": False}, timeout=20)

    def test_confirm_untrusted_creates_pending(self):
        r = self.s_member.post(f"{API}/payments/zeffy/confirm",
                               json={"confirmation": "RCT-0401-5406", "amount": 105.0}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending"
        assert d["auto_approved"] is False
        tx_id = d["transaction_id"]
        # Verify via member feed
        feed = self.s_member.get(f"{API}/me/transactions", timeout=20).json()
        match = [t for t in feed if t["id"] == tx_id]
        assert match, "tx not in member feed"
        assert match[0]["zeffy_receipt_format"] == "rct"
        assert match[0]["status"] == "pending"
        # Admin approves
        ap = self.s_admin.put(f"{API}/transactions/{tx_id}/approve-zeffy", timeout=20)
        assert ap.status_code == 200, ap.text
        # Re-approve idempotent
        ap2 = self.s_admin.put(f"{API}/transactions/{tx_id}/approve-zeffy", timeout=20)
        assert ap2.status_code == 200
        # cleanup
        self.s_admin.delete(f"{API}/transactions/{tx_id}", timeout=20)

    def test_confirm_trusted_auto_approves(self):
        # flip trust on
        u = self.s_admin.put(f"{API}/members/{self.member['id']}", json={"trust_zeffy": True}, timeout=20)
        assert u.status_code == 200
        # re-login to refresh user doc cache (token reads doc fresh each request anyway)
        s_m, rm = _login(MEMBER)
        r = s_m.post(f"{API}/payments/zeffy/confirm",
                     json={"confirmation": "RCT-1234-5678", "amount": 105.0}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "completed", d
        assert d["auto_approved"] is True
        tx_id = d["transaction_id"]
        # cleanup
        self.s_admin.delete(f"{API}/transactions/{tx_id}", timeout=20)
        self.s_admin.put(f"{API}/members/{self.member['id']}", json={"trust_zeffy": False}, timeout=20)

    def test_approve_zeffy_non_zeffy_400(self):
        # create a non-zeffy tx as admin
        r = self.s_admin.post(f"{API}/transactions",
                              json={"user_id": self.member["id"], "type": "fee",
                                    "amount": 10.0, "description": "TEST_iter25"}, timeout=20)
        assert r.status_code == 200, r.text
        tx_id = r.json()["id"]
        ap = self.s_admin.put(f"{API}/transactions/{tx_id}/approve-zeffy", timeout=20)
        assert ap.status_code == 400
        self.s_admin.delete(f"{API}/transactions/{tx_id}", timeout=20)

    def test_approve_zeffy_missing_404(self):
        ap = self.s_admin.put(f"{API}/transactions/missing-id-zzz/approve-zeffy", timeout=20)
        assert ap.status_code == 404

    def test_admin_list_surfaces_format(self):
        # Create a pending zeffy tx as member, list as admin, verify field
        r = self.s_member.post(f"{API}/payments/zeffy/confirm",
                               json={"confirmation": "ZF-ABC123XYZ", "amount": 105.0}, timeout=20)
        tx_id = r.json()["transaction_id"]
        lst = self.s_admin.get(f"{API}/transactions", timeout=20).json()
        match = [t for t in lst if t["id"] == tx_id]
        assert match, "admin list missing newly created tx"
        assert match[0]["zeffy_receipt_format"] == "zf"
        # cleanup
        self.s_admin.delete(f"{API}/transactions/{tx_id}", timeout=20)


# ---------- SMOKE: unmoved endpoints ----------
class TestUnmovedEndpoints:
    def setup_method(self):
        self.s, r = _login(ADMIN)
        assert r.status_code == 200

    def test_members(self):
        r = self.s.get(f"{API}/members", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_chapters(self):
        r = self.s.get(f"{API}/chapters", timeout=20)
        assert r.status_code == 200

    def test_tiers(self):
        r = self.s.get(f"{API}/tiers", timeout=20)
        assert r.status_code == 200

    def test_events(self):
        r = self.s.get(f"{API}/events", timeout=20)
        assert r.status_code == 200

    def test_forgot_password_endpoint_exists(self):
        # Should not 404 even with bogus payload — endpoint should be wired.
        r = requests.post(f"{API}/auth/forgot-password",
                          json={"email": "nobody-iter25@example.com"}, timeout=20)
        assert r.status_code in (200, 202, 400, 422)
