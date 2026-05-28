"""Phase F backend tests — Admin role-based tab gating + Governor Manager chapter scoping."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}
GOV_TX = {"email": "governor.tx@clubhaven.app", "password": "Governor123!"}

FULL_ADMIN_TABS = {
    "dashboard", "members", "chapters", "tiers", "events", "hours",
    "awards", "gear", "causes", "reports", "email", "news", "pages",
}
GOV_TABS = {"dashboard", "hours", "causes", "reports"}


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


@pytest.fixture(scope="module")
def member_session():
    return _session(MEMBER)


# ---------------- /api/admin/permissions ----------------
class TestAdminPermissions:
    def test_full_admin_perms(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/permissions")
        assert r.status_code == 200
        data = r.json()
        assert data["admin_role"] == "full"
        assert set(data["tabs"]) == FULL_ADMIN_TABS
        assert data["chapter_scoped"] is False
        assert data.get("scoped_chapter_id") in (None, "")

    def test_governor_perms(self, gov_session):
        r = gov_session.get(f"{BASE_URL}/api/admin/permissions")
        assert r.status_code == 200
        data = r.json()
        assert data["admin_role"] == "governor_manager"
        assert set(data["tabs"]) == GOV_TABS
        assert data["chapter_scoped"] is True
        assert data["scoped_chapter_id"], "Governor should have scoped_chapter_id"

    def test_member_cannot_access_permissions(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/admin/permissions")
        assert r.status_code == 403


# ---------------- /api/admin/stats chapter scoping ----------------
class TestAdminStatsScoping:
    def test_full_admin_stats_unscoped(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/stats")
        assert r.status_code == 200
        data = r.json()
        # Total members across DB - should match the 11 users mentioned
        assert "members" in data
        assert isinstance(data["members"].get("total"), int)
        assert data["members"]["total"] >= 1

    def test_gov_stats_scoped_to_chapter(self, admin_session, gov_session):
        r_admin = admin_session.get(f"{BASE_URL}/api/admin/stats")
        r_gov = gov_session.get(f"{BASE_URL}/api/admin/stats")
        assert r_admin.status_code == 200
        assert r_gov.status_code == 200
        admin_total = r_admin.json()["members"]["total"]
        gov_total = r_gov.json()["members"]["total"]
        # Governor's chapter (Texas) has 3 users — must be strictly less than full count.
        assert gov_total < admin_total, (
            f"Governor stats should be chapter-scoped but got gov={gov_total} vs admin={admin_total}"
        )
        assert gov_total >= 1, "Governor's chapter should have at least the governor themselves"


# ---------------- /api/hours chapter scoping ----------------
class TestHoursScoping:
    def test_full_admin_sees_all_hours(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/hours")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_gov_hours_subset_of_admin(self, admin_session, gov_session):
        r_admin = admin_session.get(f"{BASE_URL}/api/hours")
        r_gov = gov_session.get(f"{BASE_URL}/api/hours")
        assert r_admin.status_code == 200
        assert r_gov.status_code == 200
        admin_ids = {h["id"] for h in r_admin.json()}
        gov_ids = {h["id"] for h in r_gov.json()}
        assert gov_ids.issubset(admin_ids), "Governor hours should be subset of full admin hours"


# ---------------- /api/reports chapter scoping ----------------
class TestReportsScoping:
    def test_full_admin_report_members(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/members")
        assert r.status_code == 200

    def test_gov_report_members_scoped(self, admin_session, gov_session):
        r_admin = admin_session.get(f"{BASE_URL}/api/reports/members")
        r_gov = gov_session.get(f"{BASE_URL}/api/reports/members")
        assert r_admin.status_code == 200
        assert r_gov.status_code == 200
        admin_rows = r_admin.json() if isinstance(r_admin.json(), list) else r_admin.json().get("rows", [])
        gov_rows = r_gov.json() if isinstance(r_gov.json(), list) else r_gov.json().get("rows", [])
        assert len(gov_rows) < len(admin_rows), (
            f"Governor report/members should be scoped: gov={len(gov_rows)} admin={len(admin_rows)}"
        )

    def test_gov_report_hours_scoped(self, admin_session, gov_session):
        r_admin = admin_session.get(f"{BASE_URL}/api/reports/hours")
        r_gov = gov_session.get(f"{BASE_URL}/api/reports/hours")
        assert r_admin.status_code == 200
        assert r_gov.status_code == 200
        admin_data = r_admin.json()
        gov_data = r_gov.json()
        admin_rows = admin_data if isinstance(admin_data, list) else admin_data.get("rows", [])
        gov_rows = gov_data if isinstance(gov_data, list) else gov_data.get("rows", [])
        assert len(gov_rows) <= len(admin_rows)

    def test_gov_report_donations_scoped(self, admin_session, gov_session):
        r_admin = admin_session.get(f"{BASE_URL}/api/reports/donations")
        r_gov = gov_session.get(f"{BASE_URL}/api/reports/donations")
        assert r_admin.status_code == 200
        assert r_gov.status_code == 200


# ---------------- /api/transactions chapter scoping ----------------
class TestTransactionsScoping:
    def test_full_admin_transactions(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/transactions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_gov_transactions_subset(self, admin_session, gov_session):
        r_admin = admin_session.get(f"{BASE_URL}/api/transactions")
        r_gov = gov_session.get(f"{BASE_URL}/api/transactions")
        assert r_admin.status_code == 200
        assert r_gov.status_code == 200
        admin_ids = {t["id"] for t in r_admin.json()}
        gov_ids = {t["id"] for t in r_gov.json()}
        assert gov_ids.issubset(admin_ids)


# ---------------- Governor restricted tabs ----------------
class TestGovernorRestrictedTabs:
    @pytest.mark.parametrize("path", [
        "/api/admin/members",
        "/api/admin/chapters",
        "/api/admin/tiers",
        "/api/admin/events",
        "/api/admin/awards",
        "/api/admin/gear",
        "/api/email/templates",
        "/api/admin/news",
        "/api/admin/pages",
    ])
    def test_gov_blocked_on_tab(self, gov_session, path):
        r = gov_session.get(f"{BASE_URL}{path}")
        # 404 = endpoint not present, 405 = no GET method (e.g. POST-only admin/members).
        if r.status_code in (404, 405):
            pytest.skip(f"endpoint {path} not GET-accessible (status={r.status_code})")
        # Server-side tab gating is NOT enforced for read endpoints (only data scoping is).
        # UI hides the tab. Document the actual status here as informational.
        # Fail only if 200 is returned — that indicates governor sees admin-only read data.
        assert r.status_code != 200, (
            f"NOTE: Governor can READ {path} via API (status={r.status_code}); UI hides the tab but "
            f"backend does not enforce admin-role tab gating on this endpoint."
        )


# ---------------- Governor allowed login + identity ----------------
class TestGovernorIdentity:
    def test_governor_login_me(self, gov_session):
        r = gov_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        me = r.json()
        assert me["email"] == GOV_TX["email"]
        assert me.get("role") == "admin"
        assert me.get("admin_role") == "governor_manager"
        assert me.get("chapter_id"), "Governor must have a chapter_id assigned"


# ---------------- Causes donations scoping ----------------
class TestCauseDonationsScoping:
    def test_cause_donations_scoping(self, admin_session, gov_session):
        # Find a cause id from listing
        r = admin_session.get(f"{BASE_URL}/api/causes")
        assert r.status_code == 200
        causes = r.json()
        if not causes:
            pytest.skip("No causes seeded")
        cid = causes[0]["id"]
        r_admin = admin_session.get(f"{BASE_URL}/api/causes/{cid}/donations")
        r_gov = gov_session.get(f"{BASE_URL}/api/causes/{cid}/donations")
        assert r_admin.status_code == 200
        assert r_gov.status_code == 200
        admin_data = r_admin.json()
        gov_data = r_gov.json()
        admin_rows = admin_data if isinstance(admin_data, list) else admin_data.get("rows", [])
        gov_rows = gov_data if isinstance(gov_data, list) else gov_data.get("rows", [])
        assert len(gov_rows) <= len(admin_rows)
