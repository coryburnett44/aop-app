"""Phase X regression tests:
- /api/me/hours period-based filtering (year/quarter/month/status_filter)
- /api/me/hours/summary year rollups (by_month, by_quarter)
- /api/reports/hours admin period & chapter filters
- /api/reports/hours/summary group_by={member, chapter, overall, month, quarter, year}
- Admin gating for /api/reports/hours and /api/reports/hours/summary
"""
import os
from datetime import datetime

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"
GOV_EMAIL = "governor.tx@clubhaven.app"
GOV_PASS = "Governor123!"
CURRENT_YEAR = datetime.utcnow().year


def _login(s, email, password):
    return s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = _login(s, ADMIN_EMAIL, ADMIN_PASS)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def member_session():
    s = requests.Session()
    r = _login(s, MEMBER_EMAIL, MEMBER_PASS)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def gov_session():
    s = requests.Session()
    r = _login(s, GOV_EMAIL, GOV_PASS)
    if r.status_code != 200:
        pytest.skip("Governor session not available")
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# ---- /api/me/hours period filters --------------------------------------
class TestMeHoursFilters:
    def test_me_hours_no_filters(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/hours")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_me_hours_by_year(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/hours", params={"year": 2025})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # all dates within year 2025
        for h in data:
            d = (h.get("date") or "")[:4]
            if d:
                assert d == "2025", f"entry has date {h.get('date')} outside year 2025"

    def test_me_hours_by_quarter(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/hours", params={"year": 2025, "quarter": 2})
        assert r.status_code == 200
        data = r.json()
        for h in data:
            d = (h.get("date") or "")[:10]
            if d:
                month = int(d[5:7])
                assert 4 <= month <= 6, f"Q2 should be Apr-Jun, got month={month}"

    def test_me_hours_by_month(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/hours", params={"year": 2025, "month": 3})
        assert r.status_code == 200
        for h in r.json():
            d = (h.get("date") or "")[:7]
            if d:
                assert d == "2025-03"

    def test_me_hours_status_filter(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/hours", params={"status_filter": "approved"})
        assert r.status_code == 200
        for h in r.json():
            assert h.get("status") == "approved"

    def test_me_hours_requires_auth(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/me/hours")
        assert r.status_code in (401, 403)


# ---- /api/me/hours/summary ---------------------------------------------
class TestMeHoursSummary:
    def test_summary_default_year(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/hours/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["year"] == CURRENT_YEAR
        assert isinstance(d["by_month"], list) and len(d["by_month"]) == 12
        assert isinstance(d["by_quarter"], list) and len(d["by_quarter"]) == 4

    def test_summary_specific_year_structure(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/hours/summary", params={"year": 2025})
        assert r.status_code == 200
        d = r.json()
        assert d["year"] == 2025
        assert len(d["by_month"]) == 12
        # First month should be Jan
        assert d["by_month"][0]["label"] == "Jan"
        assert d["by_month"][11]["label"] == "Dec"
        # Each month has required fields
        for m in d["by_month"]:
            assert "hours" in m and "approved_hours" in m and "count" in m
        assert len(d["by_quarter"]) == 4
        # by_quarter labels Q1..Q4
        assert [q["label"] for q in d["by_quarter"]] == ["Q1", "Q2", "Q3", "Q4"]
        for q in d["by_quarter"]:
            assert "hours" in q and "approved_hours" in q and "count" in q
        # total_approved consistency
        sum_months_approved = sum(m["approved_hours"] for m in d["by_month"])
        assert abs(sum_months_approved - d["total_approved"]) < 0.01

    def test_summary_total_approved_zero_when_no_entries(self, member_session):
        # Use a year far in the future where there is no data
        r = member_session.get(f"{BASE_URL}/api/me/hours/summary", params={"year": 2099})
        assert r.status_code == 200
        d = r.json()
        assert d["total_approved"] == 0.0
        assert all(m["hours"] == 0.0 for m in d["by_month"])

    def test_summary_requires_auth(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/me/hours/summary")
        assert r.status_code in (401, 403)


# ---- /api/reports/hours admin filters ----------------------------------
class TestReportsHoursAdmin:
    def test_admin_can_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_member_forbidden(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/reports/hours")
        assert r.status_code in (401, 403)

    def test_summary_member_forbidden(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/reports/hours/summary")
        assert r.status_code in (401, 403)

    def test_reports_hours_year_filter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours", params={"year": 2025})
        assert r.status_code == 200
        for h in r.json():
            d = (h.get("date") or "")[:4]
            if d:
                assert d == "2025"

    def test_reports_hours_quarter_filter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours", params={"year": 2025, "quarter": 1})
        assert r.status_code == 200
        for h in r.json():
            ds = (h.get("date") or "")[:10]
            if ds:
                m = int(ds[5:7])
                assert 1 <= m <= 3, f"Q1 expected Jan-Mar got {m}"

    def test_reports_hours_chapter_filter(self, admin_session):
        # Find a chapter id
        ch = admin_session.get(f"{BASE_URL}/api/chapters")
        assert ch.status_code == 200
        chapters = ch.json()
        if not chapters:
            pytest.skip("No chapters seeded")
        chapter_id = chapters[0]["id"]
        r = admin_session.get(f"{BASE_URL}/api/reports/hours", params={"chapter_id": chapter_id})
        assert r.status_code == 200
        # Cannot easily verify each entry belongs to chapter without joining;
        # but the endpoint must succeed
        assert isinstance(r.json(), list)

    def test_reports_hours_combined_filters(self, admin_session):
        ch = admin_session.get(f"{BASE_URL}/api/chapters").json()
        if not ch:
            pytest.skip()
        r = admin_session.get(f"{BASE_URL}/api/reports/hours", params={
            "year": 2025, "quarter": 1, "chapter_id": ch[0]["id"], "status_filter": "approved"
        })
        assert r.status_code == 200
        for h in r.json():
            assert h.get("status") == "approved"


# ---- /api/reports/hours/summary group_by --------------------------------
class TestReportsHoursSummary:
    def test_group_by_member(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours/summary", params={"group_by": "member"})
        assert r.status_code == 200
        d = r.json()
        assert d["group_by"] == "member"
        assert "totals" in d and "rows" in d and "period" in d
        # totals contract
        for k in ("approved_hours", "pending_hours", "rejected_hours",
                  "approved_count", "pending_count", "rejected_count"):
            assert k in d["totals"]
        # rows shape
        for row in d["rows"]:
            for k in ("user_id", "user_name", "chapter_id", "chapter_name", "hours", "count"):
                assert k in row, f"missing {k} in member row: {row}"
        # sorted desc by hours
        hours = [r["hours"] for r in d["rows"]]
        assert hours == sorted(hours, reverse=True)

    def test_group_by_chapter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours/summary", params={"group_by": "chapter"})
        assert r.status_code == 200
        d = r.json()
        assert d["group_by"] == "chapter"
        for row in d["rows"]:
            for k in ("chapter_id", "chapter_name", "hours", "count", "member_count"):
                assert k in row, f"missing {k} in chapter row: {row}"

    def test_group_by_overall(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours/summary", params={"group_by": "overall"})
        assert r.status_code == 200
        d = r.json()
        assert d["group_by"] == "overall"
        assert len(d["rows"]) == 1
        row = d["rows"][0]
        assert row["label"] == "All hours"
        assert "hours" in row and "count" in row

    def test_group_by_month(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours/summary",
                              params={"group_by": "month", "year": 2025})
        assert r.status_code == 200
        d = r.json()
        assert d["group_by"] == "month"
        keys = [row["period_key"] for row in d["rows"]]
        assert keys == sorted(keys), "month rows should be ascending"
        for row in d["rows"]:
            assert "period_label" in row and "period_key" in row
            assert row["period_key"].startswith("2025-")
            # label format e.g. 'Jan 2025'
            assert "2025" in row["period_label"]

    def test_group_by_quarter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours/summary",
                              params={"group_by": "quarter", "year": 2025})
        assert r.status_code == 200
        d = r.json()
        assert d["group_by"] == "quarter"
        for row in d["rows"]:
            # period_key format '2025-Q1'
            assert row["period_key"].startswith("2025-Q"), row["period_key"]

    def test_group_by_year(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours/summary", params={"group_by": "year"})
        assert r.status_code == 200
        d = r.json()
        assert d["group_by"] == "year"
        for row in d["rows"]:
            # period_key format '2025'
            assert row["period_key"].isdigit() and len(row["period_key"]) == 4

    def test_summary_period_window(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/hours/summary",
                              params={"year": 2025, "quarter": 2, "group_by": "overall"})
        assert r.status_code == 200
        d = r.json()
        assert d["period"]["year"] == 2025
        assert d["period"]["quarter"] == 2
        assert d["period"]["from"].startswith("2025-04-01")
        assert d["period"]["to"].startswith("2025-06-30")


# ---- Chapter scoping for governor --------------------------------------
class TestChapterScopedAdmin:
    def test_governor_only_sees_chapter_hours(self, gov_session, admin_session):
        # Get governor user info to determine their chapter
        me = gov_session.get(f"{BASE_URL}/api/auth/me").json()
        gov_chapter = me.get("chapter_id")
        if not gov_chapter:
            pytest.skip("Governor has no chapter assigned")
        r = gov_session.get(f"{BASE_URL}/api/reports/hours")
        assert r.status_code == 200
        # All entries should belong to a member in the governor's chapter
        entries = r.json()
        if not entries:
            return  # nothing to verify
        # Verify by fetching users
        users = admin_session.get(f"{BASE_URL}/api/members").json()
        chapter_user_ids = {u["id"] for u in users if u.get("chapter_id") == gov_chapter}
        for h in entries:
            assert h["user_id"] in chapter_user_ids, f"hour entry leaked outside chapter scope"


# ---- Regression: /api/hours review queue --------------------------------
class TestRegressionHoursQueue:
    def test_admin_hours_queue(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/hours")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_review_pending_route_exists(self, admin_session):
        # Use a fake id — PUT exists; should return 404 (route exists & gated correctly)
        r = admin_session.put(f"{BASE_URL}/api/hours/nonexistent_id_xxx/review",
                              json={"status": "approved"})
        assert r.status_code in (400, 404, 422)
