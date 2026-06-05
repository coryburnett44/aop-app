"""
Iteration 37 — Tests for:
  (A) routes/reports.py extraction (admin /reports/* endpoints + personnel-brief + PDF)
  (B) /me/personnel-brief and /me/personnel-brief/pdf still work via the shim
  (C) /api/awards now returns granted_count + granted_distinct_count
  (D) Recent grants carry ordinal + award_count
  (E) Permission gating (member -> 403 on /reports/*; admin -> 200)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


# ----- fixtures -----
def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=10)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def member():
    return _login(MEMBER)


@pytest.fixture(scope="module")
def member_user(member):
    r = member.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json()


# ===== A. /reports/* endpoints (refactored) =====
class TestReportsRefactor:
    def test_reports_members(self, admin):
        r = admin.get(f"{API}/reports/members", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            row = data[0]
            for f in ("id", "name", "events_attended_count", "events_attended", "guests_registered_count", "guests_registered"):
                assert f in row, f"missing field {f} in /reports/members row"

    def test_reports_members_chapter_filter(self, admin):
        # chapter filter should not error even when chapter has 0 members
        r = admin.get(f"{API}/reports/members", params={"chapter_id": "__nonexistent__"}, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_reports_rsvps(self, admin):
        r = admin.get(f"{API}/reports/rsvps", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            for f in ("rsvp_id", "event_id", "user_id", "guests", "guest_count"):
                assert f in row

    def test_reports_hours(self, admin):
        r = admin.get(f"{API}/reports/hours", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_reports_hours_status_filter(self, admin):
        r = admin.get(f"{API}/reports/hours", params={"status_filter": "approved"}, timeout=20)
        assert r.status_code == 200
        rows = r.json()
        for h in rows:
            assert h.get("status") == "approved"

    @pytest.mark.parametrize("group_by", ["member", "chapter", "overall", "month", "quarter", "year"])
    def test_reports_hours_summary_group_by(self, admin, group_by):
        r = admin.get(f"{API}/reports/hours/summary", params={"group_by": group_by}, timeout=20)
        assert r.status_code == 200, f"group_by={group_by} -> {r.status_code} {r.text[:200]}"
        data = r.json()
        # Shape
        assert "totals" in data and "rows" in data and "period" in data and "group_by" in data
        assert data["group_by"] == group_by
        assert isinstance(data["rows"], list)
        totals = data["totals"]
        for f in ("approved_hours", "pending_hours", "rejected_hours", "approved_count"):
            assert f in totals
        # Per-group row shape check
        if data["rows"]:
            row = data["rows"][0]
            if group_by == "member":
                assert "user_id" in row and "hours" in row
            elif group_by == "chapter":
                assert "chapter_id" in row and "hours" in row and "member_count" in row
            elif group_by == "overall":
                assert "label" in row and "hours" in row
            else:
                assert "period_key" in row and "period_label" in row

    def test_reports_donations(self, admin):
        r = admin.get(f"{API}/reports/donations", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_personnel_brief_admin(self, admin, member_user):
        r = admin.get(f"{API}/reports/personnel-brief/{member_user['id']}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # Regression: required shape preserved
        for f in (
            "member", "chapter", "tier",
            "awards", "awards_grouped", "awards_count", "awards_distinct_count",
            "hours", "approved_hours", "pending_hours",
            "events", "events_count",
            "checkins", "rsvps", "transactions", "total_paid", "generated_at",
        ):
            assert f in d, f"missing personnel-brief field: {f}"
        assert isinstance(d["awards_grouped"], list)
        assert d["awards_distinct_count"] <= d["awards_count"]

    def test_personnel_brief_pdf_admin(self, admin, member_user):
        r = admin.get(f"{API}/reports/personnel-brief/{member_user['id']}/pdf", timeout=30)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content.startswith(b"%PDF"), "Not a PDF (no %PDF magic)"
        assert len(r.content) > 2000, f"PDF too small: {len(r.content)} bytes"

    def test_personnel_brief_pdf_not_found(self, admin):
        r = admin.get(f"{API}/reports/personnel-brief/__bogus__/pdf", timeout=10)
        assert r.status_code == 404


# ===== B. /me/personnel-brief* shim (still in server.py) =====
class TestMeBriefShim:
    def test_me_personnel_brief(self, member):
        r = member.get(f"{API}/me/personnel-brief", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for f in ("member", "awards_grouped", "awards_distinct_count", "hours"):
            assert f in d

    def test_me_personnel_brief_pdf(self, member):
        r = member.get(f"{API}/me/personnel-brief/pdf", timeout=30)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content.startswith(b"%PDF")
        assert len(r.content) > 2000

    def test_me_brief_matches_admin_brief(self, admin, member, member_user):
        a = admin.get(f"{API}/reports/personnel-brief/{member_user['id']}", timeout=20).json()
        m = member.get(f"{API}/me/personnel-brief", timeout=20).json()
        # Same member content (counts must match — the shim delegates to the same fn)
        assert a["awards_count"] == m["awards_count"]
        assert a["awards_distinct_count"] == m["awards_distinct_count"]
        assert a["member"]["id"] == m["member"]["id"]


# ===== C. /api/awards multi-grant fields =====
class TestAwardsGrantedCounts:
    def test_awards_list_has_both_counts(self, admin):
        r = admin.get(f"{API}/awards", timeout=10)
        assert r.status_code == 200
        awards = r.json()
        assert isinstance(awards, list) and len(awards) > 0
        for a in awards:
            assert "granted_count" in a, "missing granted_count"
            assert "granted_distinct_count" in a, "missing granted_distinct_count"
            assert isinstance(a["granted_count"], int)
            assert isinstance(a["granted_distinct_count"], int)
            assert a["granted_distinct_count"] <= a["granted_count"]

    def test_life_membership_ribbon_multi_grant(self, admin):
        """From iter36 context: Riley Chen has 3 grants of 'Life Membership Ribbon' (distinct=1, total=3)."""
        r = admin.get(f"{API}/awards", timeout=10)
        assert r.status_code == 200
        for a in r.json():
            if a.get("name") == "Life Membership Ribbon":
                assert a["granted_count"] >= a["granted_distinct_count"]
                # If total > distinct, ordinal pills should appear on recent recipients (FE)
                return
        pytest.skip("Life Membership Ribbon award not present in this env")


# ===== D. Recent grants carry ordinal + award_count =====
class TestRecentGrantsOrdinal:
    def test_grants_per_member_carry_ordinal_and_award_count(self, admin, member_user):
        """The Awards public page aggregates /members/{id}/awards across members
        and renders ordinal pills when award_count > 1. So /members/{id}/awards
        must carry both `ordinal` and `award_count`."""
        r = admin.get(f"{API}/members/{member_user['id']}/awards", timeout=10)
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
        rows = r.json()
        assert isinstance(rows, list)
        if not rows:
            pytest.skip("Member has no award grants")
        for row in rows:
            assert "ordinal" in row, f"missing ordinal on grant {row.get('id')}"
            assert "award_count" in row, f"missing award_count on grant {row.get('id')}"
        # Verify at least one multi-grant award has ordinal > 1 + award_count > 1
        multi = [r for r in rows if (r.get("award_count") or 0) > 1]
        if multi:
            assert any(g.get("ordinal") and g["ordinal"] > 1 for g in multi), \
                "expected at least one grant with ordinal>1 for multi-grant awards"


# ===== E. Permission gating =====
class TestReportsPermissions:
    @pytest.mark.parametrize("path", [
        "/reports/members",
        "/reports/rsvps",
        "/reports/hours",
        "/reports/hours/summary",
        "/reports/donations",
    ])
    def test_member_blocked_on_reports_endpoints(self, member, path):
        r = member.get(f"{API}{path}", timeout=10)
        assert r.status_code == 403, f"{path} should 403 for member (got {r.status_code})"

    def test_member_blocked_on_personnel_brief_admin_endpoint(self, member, member_user):
        r = member.get(f"{API}/reports/personnel-brief/{member_user['id']}", timeout=10)
        assert r.status_code == 403

    def test_member_blocked_on_personnel_brief_pdf_admin_endpoint(self, member, member_user):
        r = member.get(f"{API}/reports/personnel-brief/{member_user['id']}/pdf", timeout=10)
        assert r.status_code == 403

    def test_unauth_blocked(self):
        r = requests.get(f"{API}/reports/members", timeout=10)
        assert r.status_code in (401, 403)
