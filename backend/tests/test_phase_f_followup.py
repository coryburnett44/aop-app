"""Phase F follow-up — server-side admin sub-role tab gating (defense-in-depth).

Validates require_admin_tab / admin_tab_dep across every endpoint listed in the
review request. Governor Manager (allowed tabs: dashboard/hours/causes/reports)
must get 403 on every restricted-tab endpoint, while full admin still gets 2xx.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
GOV_TX = {"email": "governor.tx@clubhaven.app", "password": "Governor123!"}


def _session(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _session(ADMIN)


@pytest.fixture(scope="module")
def gov_session():
    return _session(GOV_TX)


# ---------------- Restricted GET endpoints (Governor must get 403) ----------------
# Tabs in this list are NOT in Governor's allowlist {dashboard, hours, causes, reports}
GOV_FORBIDDEN_GETS = [
    "/api/email/templates",        # email tab
    "/api/email/blasts",           # email tab
    "/api/email/signatures",       # email tab
]


@pytest.mark.parametrize("path", GOV_FORBIDDEN_GETS)
def test_gov_forbidden_get_returns_403(gov_session, path):
    r = gov_session.get(f"{BASE_URL}{path}")
    assert r.status_code == 403, (
        f"Governor should get 403 on {path}, got {r.status_code}: {r.text[:200]}"
    )


@pytest.mark.parametrize("path", GOV_FORBIDDEN_GETS)
def test_admin_allowed_get_returns_200(admin_session, path):
    r = admin_session.get(f"{BASE_URL}{path}")
    assert r.status_code == 200, (
        f"Full admin should get 200 on {path}, got {r.status_code}: {r.text[:200]}"
    )


# ---------------- Restricted POST/PUT/DELETE endpoints (Governor must get 403, NOT 401/422) ----------------
# We send minimal/empty bodies — gating runs BEFORE pydantic validation in FastAPI,
# so a 403 confirms the dep blocks even malformed requests for governor.
RESTRICTED_WRITES = [
    # method, path, json
    ("POST",   "/api/email/blast",        {"subject": "x", "html": "<p>x</p>", "filter": {}}),
    ("POST",   "/api/email/preview",      {"subject": "x", "html": "<p>x</p>", "filter": {}}),
    ("POST",   "/api/news",               {"title": "x", "body": "x"}),
    ("PUT",    "/api/news/nonexistent",   {"title": "x"}),
    ("DELETE", "/api/news/nonexistent",   None),
    ("POST",   "/api/pages",              {"slug": "x", "title": "x", "body": "x"}),
    ("PUT",    "/api/pages/nonexistent",  {"title": "x"}),
    ("DELETE", "/api/pages/nonexistent",  None),
    ("POST",   "/api/chapters",           {"name": "x", "state": "TX"}),
    ("PUT",    "/api/chapters/nonexistent", {"name": "x"}),
    ("DELETE", "/api/chapters/nonexistent", None),
    ("POST",   "/api/tiers",              {"name": "x", "min_hours": 0}),
    ("PUT",    "/api/tiers/nonexistent",  {"name": "x"}),
    ("DELETE", "/api/tiers/nonexistent",  None),
    ("POST",   "/api/events",             {"title": "x", "starts_at": "2030-01-01T00:00:00Z"}),
    ("PUT",    "/api/events/nonexistent", {"title": "x"}),
    ("DELETE", "/api/events/nonexistent", None),
    ("POST",   "/api/awards",             {"name": "x"}),
    ("PUT",    "/api/awards/nonexistent", {"name": "x"}),
    ("DELETE", "/api/awards/nonexistent", None),
    ("POST",   "/api/awards/nonexistent/grant", {"user_id": "u"}),
    ("DELETE", "/api/awards/grants/nonexistent", None),
    ("POST",   "/api/admin/members",      {"email": "x@x.com", "name": "x"}),
    # NOTE: server routes are /api/members/{id}* (managed by admin_tab_dep("members"))
    ("PUT",    "/api/members/nonexistent", {"name": "x"}),
    ("DELETE", "/api/members/nonexistent", None),
    ("PUT",    "/api/members/nonexistent/role",    {"role": "member"}),
    ("PUT",    "/api/members/nonexistent/chapter", {"chapter_id": "x"}),
    ("PUT",    "/api/members/nonexistent/tier",    {"tier_id": "x"}),
    ("PUT",    "/api/members/nonexistent/status",  {"status": "active"}),
    ("POST",   "/api/gear",               {"name": "x", "price": 0}),
    ("PUT",    "/api/gear/nonexistent",   {"name": "x"}),
    ("DELETE", "/api/gear/nonexistent",   None),
    # POST check-in is singular /check-in (kept; list/delete are /check-ins)
    ("POST",   "/api/events/nonexistent/check-in", {"user_id": "x"}),
    ("GET",    "/api/events/nonexistent/check-ins", None),
    ("DELETE", "/api/events/nonexistent/check-ins/nonexistent", None),
    # Image upload — multipart, but gating runs first so 403 expected without file
    ("POST",   "/api/email/upload-image", None),
]


@pytest.mark.parametrize("method,path,body", RESTRICTED_WRITES,
                         ids=[f"{m} {p}" for m, p, _ in RESTRICTED_WRITES])
def test_gov_forbidden_writes_return_403(gov_session, method, path, body):
    url = f"{BASE_URL}{path}"
    if method == "POST":
        r = gov_session.post(url, json=body) if body is not None else gov_session.post(url)
    elif method == "PUT":
        r = gov_session.put(url, json=body) if body is not None else gov_session.put(url)
    elif method == "DELETE":
        r = gov_session.delete(url)
    else:  # GET
        r = gov_session.get(url)
    assert r.status_code == 403, (
        f"Governor should be 403 on {method} {path}, got {r.status_code}: {r.text[:200]}"
    )


# ---------------- Governor IS allowed on their 4 tabs ----------------
class TestGovernorAllowedEndpoints:
    def test_gov_admin_stats(self, gov_session):
        r = gov_session.get(f"{BASE_URL}/api/admin/stats")
        assert r.status_code == 200

    def test_gov_hours_list(self, gov_session):
        r = gov_session.get(f"{BASE_URL}/api/hours")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_gov_hours_review_allowed(self, gov_session):
        # Hours tab is allowed for governor; gating must NOT 403.
        # Non-existent id is fine — expect 404 (not 403).
        r = gov_session.put(
            f"{BASE_URL}/api/hours/nonexistent/review",
            json={"status": "approved"},
        )
        assert r.status_code != 403, f"Governor must not be 403 on hours/review, got {r.status_code}"
        assert r.status_code in (200, 400, 404, 422), (
            f"Expected 200/400/404/422 on hours/review, got {r.status_code}: {r.text[:200]}"
        )

    def test_gov_causes_write_allowed(self, gov_session):
        # Causes tab is in governor's allowlist. Create then delete.
        r = gov_session.post(
            f"{BASE_URL}/api/causes",
            json={"title": "TEST_gov_cause", "description": "phase F follow-up"},
        )
        assert r.status_code != 403, f"Governor must not be 403 on POST /api/causes, got {r.status_code}: {r.text[:200]}"
        if r.status_code in (200, 201):
            cid = r.json().get("id")
            if cid:
                upd = gov_session.put(
                    f"{BASE_URL}/api/causes/{cid}",
                    json={"title": "TEST_gov_cause_upd"},
                )
                assert upd.status_code != 403
                d = gov_session.delete(f"{BASE_URL}/api/causes/{cid}")
                assert d.status_code != 403

    def test_gov_reports_members(self, gov_session):
        r = gov_session.get(f"{BASE_URL}/api/reports/members")
        assert r.status_code == 200

    def test_gov_reports_hours(self, gov_session):
        r = gov_session.get(f"{BASE_URL}/api/reports/hours")
        assert r.status_code == 200

    def test_gov_reports_donations(self, gov_session):
        r = gov_session.get(f"{BASE_URL}/api/reports/donations")
        assert r.status_code == 200

    def test_gov_personnel_brief(self, admin_session, gov_session):
        # Find a user in governor's chapter via /api/admin/permissions + reports/members
        rm = gov_session.get(f"{BASE_URL}/api/reports/members")
        assert rm.status_code == 200
        rows = rm.json() if isinstance(rm.json(), list) else rm.json().get("rows", [])
        if not rows:
            pytest.skip("No members in governor's chapter to look up brief for")
        uid = rows[0].get("id") or rows[0].get("user_id")
        if not uid:
            pytest.skip("Member row missing id field")
        r = gov_session.get(f"{BASE_URL}/api/reports/personnel-brief/{uid}")
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"

    def test_gov_cause_donations(self, admin_session, gov_session):
        rc = admin_session.get(f"{BASE_URL}/api/causes")
        if rc.status_code != 200 or not rc.json():
            pytest.skip("No causes seeded")
        cid = rc.json()[0]["id"]
        r = gov_session.get(f"{BASE_URL}/api/causes/{cid}/donations")
        assert r.status_code == 200


# ---------------- Full admin still works (no regression) ----------------
class TestFullAdminNoRegression:
    def test_admin_login_me(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json().get("email") == ADMIN["email"]

    def test_admin_permissions_full(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/permissions")
        assert r.status_code == 200
        assert r.json()["admin_role"] == "full"

    @pytest.mark.parametrize("path", [
        "/api/email/templates",
        "/api/email/blasts",
        "/api/email/signatures",
        "/api/admin/stats",
        "/api/hours",
        "/api/reports/members",
        "/api/reports/hours",
        "/api/reports/donations",
    ])
    def test_admin_gets_200(self, admin_session, path):
        r = admin_session.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"admin should get 200 on {path}, got {r.status_code}"

    def test_admin_create_news_then_delete(self, admin_session):
        # Smoke test: confirm restricted write tabs still work for full admin
        r = admin_session.post(
            f"{BASE_URL}/api/news",
            json={"title": "TEST_phaseF_news", "body": "ok"},
        )
        assert r.status_code in (200, 201), f"admin POST /api/news got {r.status_code}: {r.text[:200]}"
        nid = r.json().get("id")
        if nid:
            d = admin_session.delete(f"{BASE_URL}/api/news/{nid}")
            assert d.status_code in (200, 204)


# ---------------- Auth regression ----------------
class TestAuthRegression:
    def test_login_admin(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
        assert r.status_code == 200

    def test_login_gov(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=GOV_TX)
        assert r.status_code == 200

    def test_me_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code in (401, 403)
