"""Iteration 48 — tests for:
1. /api/admin/dashboard members.by_tier returns only real tier names from db.tiers
2. /api/reports/award-grants admin endpoint (enriched + year/user filters)
3. /api/reports/of-the-year admin endpoint (enriched + category_label + year filter)
4. authz: non-admin gets 401/403 on the two new endpoints
"""
import os
import pytest
import requests

def _load_backend_url():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if not val:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except FileNotFoundError:
            pass
    if not val:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return val.rstrip("/")


BASE_URL = _load_backend_url()
ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin_client():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def member_client():
    return _login(MEMBER)


# ---------- by_tier ----------
class TestByTier:
    def test_by_tier_returns_only_real_tier_names(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/stats", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "members" in data
        by_tier = data["members"]["by_tier"]
        assert isinstance(by_tier, list)

        # fetch real tiers
        t = admin_client.get(f"{BASE_URL}/api/tiers", timeout=15)
        assert t.status_code == 200
        real_names = {x["name"] for x in t.json()}
        assert real_names, "no tiers in DB - cannot validate by_tier filter"

        # every entry's tier must be a real tier name
        for entry in by_tier:
            assert "tier" in entry and "count" in entry
            assert entry["count"] > 0, f"non-positive count: {entry}"
            assert entry["tier"] in real_names, (
                f"by_tier returned non-tier label '{entry['tier']}' - "
                f"expected one of real tier names {real_names}"
            )
            # confirm 'standard' / 'lifetime' status strings are not surfaced
            assert entry["tier"].lower() not in ("standard", "lifetime")

    def test_by_tier_sorted_desc_by_count(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/stats", timeout=20)
        assert r.status_code == 200
        by_tier = r.json()["members"]["by_tier"]
        counts = [e["count"] for e in by_tier]
        assert counts == sorted(counts, reverse=True), "by_tier not sorted desc by count"


# ---------- /reports/award-grants ----------
class TestAwardGrants:
    def test_list_enriched(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/reports/award-grants", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        if not rows:
            pytest.skip("no award grants in seed DB to assert enrichment on")
        # sorted granted_at desc
        gs = [r_.get("granted_at", "") for r_ in rows]
        assert gs == sorted(gs, reverse=True), "award-grants not sorted granted_at DESC"
        # enriched fields present
        sample = rows[0]
        for k in ("current_user_name", "user_email", "user_avatar_url", "chapter_name"):
            assert k in sample, f"missing enriched field {k} in award-grant row: {sample.keys()}"

    def test_filter_by_year_2026(self, admin_client):
        r = admin_client.get(
            f"{BASE_URL}/api/reports/award-grants", params={"year": 2026}, timeout=20
        )
        assert r.status_code == 200
        rows = r.json()
        for row in rows:
            ga = row.get("granted_at", "")
            assert ga.startswith("2026"), f"year=2026 filter leaked non-2026 row: {ga}"

    def test_filter_by_user_id(self, admin_client):
        # get any grant then re-filter by its user_id
        r = admin_client.get(f"{BASE_URL}/api/reports/award-grants", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        if not rows:
            pytest.skip("no grants to test user_id filter")
        uid = rows[0]["user_id"]
        r2 = admin_client.get(
            f"{BASE_URL}/api/reports/award-grants",
            params={"user_id": uid},
            timeout=20,
        )
        assert r2.status_code == 200
        filtered = r2.json()
        assert filtered, "user_id filter returned empty"
        for row in filtered:
            assert row["user_id"] == uid

    def test_authz_member_forbidden(self, member_client):
        r = member_client.get(f"{BASE_URL}/api/reports/award-grants", timeout=20)
        assert r.status_code in (401, 403), (
            f"member should be denied, got {r.status_code} {r.text[:200]}"
        )

    def test_authz_anon_forbidden(self):
        r = requests.get(f"{BASE_URL}/api/reports/award-grants", timeout=20)
        assert r.status_code in (401, 403)


# ---------- /reports/of-the-year ----------
class TestOfTheYear:
    def test_list_enriched(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/reports/of-the-year", timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        if not rows:
            pytest.skip("no OTY rows in seed DB")
        # sorted year DESC, category ASC within year
        for i in range(1, len(rows)):
            a, b = rows[i - 1], rows[i]
            if a["year"] == b["year"]:
                assert a["category"] <= b["category"], (
                    f"category not ascending within year {a['year']}: {a['category']} then {b['category']}"
                )
            else:
                assert a["year"] > b["year"], f"year not descending: {a['year']} then {b['year']}"
        # category_label present and human-readable
        sample_categories_expected = {
            "member_of_year": "Member of the Year",
            "chapter_of_year": "Chapter of the Year",
            "top_cs_member": "Top Community Service Member",
            "top_cs_chapter": "Top Community Service Chapter",
            "top_fundraising_member": "Top Fundraising Member",
            "top_fundraising_chapter": "Top Fundraising Chapter",
            "top_recruiter": "Top Member Recruiter",
        }
        for row in rows:
            assert "category_label" in row
            cat = row.get("category", "")
            if cat in sample_categories_expected:
                assert row["category_label"] == sample_categories_expected[cat]

    def test_filter_by_year(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/reports/of-the-year", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        if not rows:
            pytest.skip("no OTY rows")
        year = rows[0]["year"]
        r2 = admin_client.get(
            f"{BASE_URL}/api/reports/of-the-year", params={"year": year}, timeout=20
        )
        assert r2.status_code == 200
        for row in r2.json():
            assert row["year"] == year

    def test_authz_member_forbidden(self, member_client):
        r = member_client.get(f"{BASE_URL}/api/reports/of-the-year", timeout=20)
        assert r.status_code in (401, 403)

    def test_authz_anon_forbidden(self):
        r = requests.get(f"{BASE_URL}/api/reports/of-the-year", timeout=20)
        assert r.status_code in (401, 403)
