"""
Iteration 49: Tests for GET /api/awards/{award_id}/grants

Validates: list endpoint returns enriched recipient rows with name fallback,
year, ordinal; auth required; non-existent IDs return empty list (no 404).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SAMPLE_AWARD_ID = "4f1a923c-6be8-47f3-baed-dbb7cb804e48"  # Life Membership Ribbon, 5 grants


# ---- fixtures ----
@pytest.fixture(scope="module")
def member_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={
        "email": "member@clubhaven.app",
        "password": "Member123!",
    })
    assert r.status_code == 200, f"member login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@clubhaven.app",
        "password": "Admin123!",
    })
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


# ---- tests ----
class TestAwardGrantsList:
    def test_anonymous_request_returns_401(self):
        # No cookies/auth — endpoint must reject.
        r = requests.get(f"{BASE_URL}/api/awards/{SAMPLE_AWARD_ID}/grants")
        assert r.status_code == 401, f"expected 401 anon, got {r.status_code}"

    def test_seeded_award_returns_enriched_rows(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/awards/{SAMPLE_AWARD_ID}/grants")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) == 5, f"expected 5 grants per seed, got {len(rows)}: {rows}"
        for row in rows:
            assert set(["user_id", "member_name", "avatar_url", "granted_at", "year", "ordinal", "reason"]).issubset(row.keys()), row
            assert row["member_name"], f"empty member_name in row: {row}"
            assert isinstance(row["ordinal"], int)
            if row["granted_at"]:
                assert row["year"] == row["granted_at"][:4]
                assert len(row["year"]) == 4

    def test_rows_sorted_granted_at_desc(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/awards/{SAMPLE_AWARD_ID}/grants")
        rows = r.json()
        dates = [row.get("granted_at") or "" for row in rows]
        assert dates == sorted(dates, reverse=True), f"not desc sorted: {dates}"

    def test_riley_chen_has_three_grants_with_ordinals(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/awards/{SAMPLE_AWARD_ID}/grants")
        rows = r.json()
        riley_rows = [x for x in rows if "Riley Chen" in (x.get("member_name") or "")]
        assert len(riley_rows) == 3, f"expected 3 Riley grants, got {len(riley_rows)}"
        ordinals = sorted([x["ordinal"] for x in riley_rows])
        assert ordinals == [1, 2, 3], f"ordinals {ordinals}"

    def test_nonexistent_award_returns_empty_list_not_404(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/awards/does-not-exist-xyz/grants")
        assert r.status_code == 200, f"expected 200, got {r.status_code} {r.text}"
        assert r.json() == []

    def test_award_with_zero_grants_returns_empty(self, admin_session):
        # Create a fresh award (no grants) and verify it returns [].
        create = admin_session.post(f"{BASE_URL}/api/awards", json={
            "name": "TEST_iter49_empty_award",
            "description": "test",
            "icon": "trophy",
            "color": "#000000",
        })
        assert create.status_code == 200, create.text
        aid = create.json()["id"]
        try:
            r = admin_session.get(f"{BASE_URL}/api/awards/{aid}/grants")
            assert r.status_code == 200
            assert r.json() == []
        finally:
            admin_session.delete(f"{BASE_URL}/api/awards/{aid}")

    def test_departed_member_uses_user_name_fallback(self, admin_session):
        """Create award + user, grant it, delete the user, then verify the grants
        response still surfaces a member_name via the stored user_name fallback."""
        # Create disposable user (will be deleted) via the admin endpoint.
        ts = "iter49departing"
        user_payload = {
            "name": "TEST Departed Member",
            "email": f"TEST_departing_{ts}@example.com",
            "role": "member",
        }
        # Try admin/users create then fall back to /api/users
        cu = admin_session.post(f"{BASE_URL}/api/admin/users", json=user_payload)
        if cu.status_code not in (200, 201):
            cu = admin_session.post(f"{BASE_URL}/api/users", json=user_payload)
        if cu.status_code not in (200, 201):
            pytest.skip(f"Cannot create disposable user via admin API (got {cu.status_code}); fallback path tested via code review only")
        uid = (cu.json() or {}).get("id")
        assert uid

        # Create an award
        ca = admin_session.post(f"{BASE_URL}/api/awards", json={
            "name": "TEST_iter49_departed",
            "description": "test",
            "icon": "trophy",
            "color": "#123456",
        })
        assert ca.status_code == 200, ca.text
        aid = ca.json()["id"]

        try:
            # Grant the award
            grant = admin_session.post(f"{BASE_URL}/api/awards/{aid}/grant", json={
                "user_id": uid,
                "reason": "test fallback",
                "granted_at": "2025-06-01T00:00:00Z",
            })
            assert grant.status_code == 200, grant.text

            # Delete the user (try a few endpoints — implementation-dependent)
            d = admin_session.delete(f"{BASE_URL}/api/admin/users/{uid}")
            if d.status_code not in (200, 204):
                d = admin_session.delete(f"{BASE_URL}/api/users/{uid}")
            if d.status_code not in (200, 204):
                pytest.skip(f"Cannot delete user via admin API (got {d.status_code}); fallback path covered by code-review only")

            # Now query grants — the row should still appear with member_name set.
            g = admin_session.get(f"{BASE_URL}/api/awards/{aid}/grants")
            assert g.status_code == 200
            rows = g.json()
            assert len(rows) == 1, rows
            row = rows[0]
            assert row["user_id"] == uid
            # Either the stored user_name ("TEST Departed Member") or 'Former member' if blank
            assert row["member_name"], f"expected non-empty fallback name, got: {row}"
            assert row["member_name"] in ("TEST Departed Member", "Former member")
        finally:
            admin_session.delete(f"{BASE_URL}/api/awards/{aid}")
