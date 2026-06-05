"""
Iteration 32 backend tests:
  - BUG 1: /api/auth/set-password endpoint with bogus token (negative path only — we
    can't easily mint a real token without poking the DB).
  - BUG 2: Login lockout no longer blocks correct credentials.
  - FEATURE 3: GET /api/admin/permissions returns all_tabs / role_default_tabs /
    has_custom_tabs. Full admin can PUT /api/members/{id} with allowed_tabs to grant
    custom tab access; non-full admins get 403. Empty allowed_tabs clears the override.
    Override drives admin_tab_dep gating (governor_manager + members tab -> can hit
    /api/admin/applications).
  - REGRESSION: Sub-role defaults still return has_custom_tabs=false.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PW = "Admin123!"
GOV_EMAIL = "governor.tx@clubhaven.app"
GOV_PW = "Governor123!"


def _login(s: requests.Session, email: str, pw: str) -> requests.Response:
    return s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = _login(s, ADMIN_EMAIL, ADMIN_PW)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text[:200]}")
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def gov_user_id(admin_session):
    """Resolve the governor.tx user id via admin members list."""
    r = admin_session.get(f"{API}/members?q=governor", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    if items is None:
        items = data
    print(f"DEBUG members lookup got {len(items)} items: {[u.get('email') for u in items]}")
    for u in items:
        if u.get("email") == GOV_EMAIL:
            return u["id"]
    pytest.skip(f"governor.tx user not found in {len(items)} members: {[u.get('email') for u in items][:5]}")


# -------- BUG 1: set-password endpoint --------
class TestSetPasswordEndpoint:
    def test_set_password_with_bogus_token_returns_4xx(self):
        r = requests.post(
            f"{API}/auth/set-password",
            json={"token": "definitely-not-a-real-token", "password": "NewPass123!"},
            timeout=20,
        )
        # Backend should reject — accept 400/401/404/422.
        assert r.status_code in (400, 401, 404, 422), f"unexpected status {r.status_code}: {r.text[:300]}"


# -------- BUG 2: Login lockout --------
class TestLoginLockoutAllowsCorrectPassword:
    """5 wrong attempts -> 6th wrong returns 429. CORRECT password should still
    succeed (200). After success, counter resets — subsequent wrong attempts go
    back to 401, not 429."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        # Make identifier unique per test run by routing through a fresh session +
        # the same IP. Backend keys by IP+email, so we use the real admin email
        # but only run this once per iteration. The post-success reset clears
        # the counter at the end.
        yield
        # Final cleanup — a single successful login resets the counter.
        s = requests.Session()
        _login(s, ADMIN_EMAIL, ADMIN_PW)

    def test_lockout_then_correct_password_succeeds(self):
        s = requests.Session()
        # 5 wrong attempts — all 401
        for i in range(5):
            r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": f"wrong-{i}"}, timeout=20)
            assert r.status_code == 401, f"attempt {i + 1} -> {r.status_code} {r.text[:120]}"

        # 6th wrong attempt should trip the soft lock (429)
        r6 = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "still-wrong"}, timeout=20)
        assert r6.status_code == 429, f"6th wrong -> {r6.status_code} {r6.text[:200]}"
        assert "15 minutes" in r6.text or "Too many" in r6.text

        # CORRECT password must STILL succeed even though we're locked
        r_ok = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=20)
        assert r_ok.status_code == 200, f"correct pw should bypass lock, got {r_ok.status_code} {r_ok.text[:200]}"
        assert "access_token" in r_ok.json()

        # Counter reset — a fresh wrong attempt should return 401 (not 429).
        r_after = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-again"}, timeout=20)
        assert r_after.status_code == 401, f"counter should be reset after success, got {r_after.status_code}"


# -------- FEATURE 3 & REGRESSION: /admin/permissions shape + custom tabs --------
class TestAdminPermissions:
    def test_full_admin_permissions_shape(self, admin_session):
        r = admin_session.get(f"{API}/admin/permissions", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("admin_role", "tabs", "all_tabs", "role_default_tabs", "has_custom_tabs"):
            assert k in data, f"missing key {k} in {data.keys()}"
        # all_tabs should be the canonical 14
        assert len(data["all_tabs"]) == 14, f"expected 14 admin tabs, got {data['all_tabs']}"
        assert "dashboard" in data["all_tabs"]
        # role_default_tabs map present for all 4 admin sub-roles
        for role in ("full", "membership_manager", "operations_manager", "governor_manager"):
            assert role in data["role_default_tabs"]
        # Full admin: every tab, no custom override.
        assert data["admin_role"] == "full"
        assert set(data["tabs"]) == set(data["all_tabs"])
        assert data["has_custom_tabs"] is False

    def test_governor_manager_default_tabs_no_custom(self):
        s = requests.Session()
        r = _login(s, GOV_EMAIL, GOV_PW)
        if r.status_code != 200:
            pytest.skip(f"governor login failed: {r.status_code} {r.text[:120]}")
        s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        rp = s.get(f"{API}/admin/permissions", timeout=20)
        assert rp.status_code == 200, rp.text
        data = rp.json()
        assert data["admin_role"] == "governor_manager"
        assert set(data["tabs"]) == {"dashboard", "hours", "causes", "reports"}, data["tabs"]
        assert data["has_custom_tabs"] is False
        assert data["chapter_scoped"] is True


class TestCustomTabPermissions:
    """Full admin grants/revokes custom tabs for governor.tx and verifies
    admin_tab_dep gating updates accordingly."""

    def test_grant_revoke_and_gating(self, admin_session, gov_user_id):
        # 1. Baseline: governor cannot hit /api/admin/applications (requires 'members' tab).
        gs = requests.Session()
        rl = _login(gs, GOV_EMAIL, GOV_PW)
        assert rl.status_code == 200, rl.text
        gs.headers["Authorization"] = f"Bearer {rl.json()['access_token']}"

        r_pre = gs.get(f"{API}/admin/applications", timeout=20)
        assert r_pre.status_code == 403, f"governor should be 403 on /admin/applications by default, got {r_pre.status_code}"

        # 2. Full admin grants 'members' (+ defaults) to governor.tx
        new_tabs = ["dashboard", "hours", "causes", "reports", "members"]
        r_put = admin_session.put(
            f"{API}/members/{gov_user_id}",
            json={"allowed_tabs": new_tabs},
            timeout=20,
        )
        assert r_put.status_code == 200, f"PUT failed: {r_put.status_code} {r_put.text[:300]}"

        # 3. Governor re-logs in and now sees has_custom_tabs=true + the granted tab.
        gs2 = requests.Session()
        rl2 = _login(gs2, GOV_EMAIL, GOV_PW)
        gs2.headers["Authorization"] = f"Bearer {rl2.json()['access_token']}"
        rp2 = gs2.get(f"{API}/admin/permissions", timeout=20)
        assert rp2.status_code == 200, rp2.text
        d2 = rp2.json()
        assert d2["has_custom_tabs"] is True, d2
        assert "members" in d2["tabs"], d2["tabs"]

        # 4. Now governor CAN hit /admin/applications.
        r_post = gs2.get(f"{API}/admin/applications", timeout=20)
        assert r_post.status_code == 200, f"after grant governor should be 200, got {r_post.status_code} {r_post.text[:200]}"

        # 5. Non-full admin cannot set allowed_tabs (403). Governor tries to edit themselves.
        r_forbid = gs2.put(
            f"{API}/members/{gov_user_id}",
            json={"allowed_tabs": ["dashboard", "members", "chapters"]},
            timeout=20,
        )
        assert r_forbid.status_code == 403, f"non-full admin should not set allowed_tabs, got {r_forbid.status_code} {r_forbid.text[:200]}"

        # 6. Revoke — full admin sends allowed_tabs=[] which clears the override.
        r_clear = admin_session.put(
            f"{API}/members/{gov_user_id}",
            json={"allowed_tabs": []},
            timeout=20,
        )
        assert r_clear.status_code == 200, r_clear.text

        # 7. After clearing, governor's permissions revert to defaults (no members).
        gs3 = requests.Session()
        rl3 = _login(gs3, GOV_EMAIL, GOV_PW)
        gs3.headers["Authorization"] = f"Bearer {rl3.json()['access_token']}"
        rp3 = gs3.get(f"{API}/admin/permissions", timeout=20)
        assert rp3.status_code == 200, rp3.text
        d3 = rp3.json()
        assert d3["has_custom_tabs"] is False, d3
        assert set(d3["tabs"]) == {"dashboard", "hours", "causes", "reports"}, d3["tabs"]

        # 8. And the /admin/applications gate is closed again.
        r_after = gs3.get(f"{API}/admin/applications", timeout=20)
        assert r_after.status_code == 403, f"after revoke should be 403, got {r_after.status_code}"

    def test_allowed_tabs_sanitized_against_all_tabs(self, admin_session, gov_user_id):
        """Sending a junk tab key should be filtered out (not persisted)."""
        r = admin_session.put(
            f"{API}/members/{gov_user_id}",
            json={"allowed_tabs": ["dashboard", "members", "totally-fake-tab", "another-junk"]},
            timeout=20,
        )
        assert r.status_code == 200, r.text

        gs = requests.Session()
        rl = _login(gs, GOV_EMAIL, GOV_PW)
        gs.headers["Authorization"] = f"Bearer {rl.json()['access_token']}"
        rp = gs.get(f"{API}/admin/permissions", timeout=20)
        data = rp.json()
        assert "totally-fake-tab" not in data["tabs"], data["tabs"]
        assert "another-junk" not in data["tabs"], data["tabs"]
        # Real ones should still be present
        assert "dashboard" in data["tabs"]
        assert "members" in data["tabs"]

        # cleanup — revert
        admin_session.put(f"{API}/members/{gov_user_id}", json={"allowed_tabs": []}, timeout=20)
