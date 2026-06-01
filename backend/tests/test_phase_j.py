"""Phase J — Founder tier, social URLs on profile, intake-approval workflow,
renew-disabled (410), free-form chapter creation. All tests against the
deployed preview URL."""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


# ---------- Fixtures ----------
def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_client():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def member_client():
    return _login(MEMBER)


# ---------- Tiers ----------
class TestTiers:
    def test_tiers_includes_founder(self, admin_client):
        r = admin_client.get(f"{BASE}/api/tiers", timeout=20)
        assert r.status_code == 200
        tiers = r.json()
        names = [t["name"] for t in tiers]
        # Expected 7 canonical tiers
        for expected in [
            "Regular Member", "Associate Member", "Honorary Member",
            "Life Member Candidate", "Silver Life Member", "Gold Life Member",
            "Founder",
        ]:
            assert expected in names, f"missing tier {expected}; got {names}"
        founder = next(t for t in tiers if t["name"] == "Founder")
        assert founder["order"] == 7
        assert founder["is_lifetime"] is True
        assert float(founder["annual_dues"]) == 0.0


# ---------- Self-renew disabled ----------
class TestRenewDisabled:
    def test_member_renew_returns_410(self, member_client):
        r = member_client.post(f"{BASE}/api/members/me/renew", timeout=20)
        assert r.status_code == 410, f"expected 410, got {r.status_code} {r.text}"
        body = r.json()
        msg = (body.get("detail") or "").lower()
        assert "renew" in msg or "payment" in msg or "paypal" in msg


# ---------- Intake date approval workflow ----------
class TestIntakeApproval:
    def test_intake_change_goes_to_pending(self, member_client):
        # First record current value
        me = member_client.get(f"{BASE}/api/auth/me", timeout=20).json()
        current = (me.get("intake_completed_at") or "").strip()
        # Pick a new value distinct from current
        new_value = "2020-01-15" if current != "2020-01-15" else "2021-06-01"
        r = member_client.put(
            f"{BASE}/api/members/me",
            json={"intake_completed_at": new_value},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # intake_completed_at should NOT be overwritten
        assert (body.get("intake_completed_at") or "").strip() == current
        # pending should be set
        assert body.get("pending_intake_completed_at", "").startswith(new_value[:10])

    def test_intake_same_value_is_noop(self, member_client):
        me = member_client.get(f"{BASE}/api/auth/me", timeout=20).json()
        current = (me.get("intake_completed_at") or "").strip()
        if not current:
            pytest.skip("No current intake_completed_at to test no-op against")
        # Clear pending first (simulate via second update with no change)
        r = member_client.put(
            f"{BASE}/api/members/me",
            json={"intake_completed_at": current},
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        # Sending same value should NOT create a pending change
        # (pending may still hold the previous test's value — we tolerate that
        # but the same-value submission shouldn't have set it to current)
        pend = (body.get("pending_intake_completed_at") or "").strip()
        assert pend != current, "same-value submit should not stash pending equal to current"

    def test_admin_pending_intake_list(self, admin_client, member_client):
        # Force a pending change again
        member_client.put(
            f"{BASE}/api/members/me",
            json={"intake_completed_at": "2019-08-08"},
            timeout=20,
        )
        r = admin_client.get(f"{BASE}/api/admin/pending-intake-changes", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        member_emails = [row["email"] for row in rows]
        assert MEMBER["email"] in member_emails, f"member not in pending list: {member_emails}"

    def test_non_admin_pending_list_forbidden(self, member_client):
        r = member_client.get(f"{BASE}/api/admin/pending-intake-changes", timeout=20)
        assert r.status_code == 403

    def test_admin_reject_clears_pending(self, admin_client, member_client):
        # Ensure there's a pending change first
        member_client.put(
            f"{BASE}/api/members/me",
            json={"intake_completed_at": "2018-12-12"},
            timeout=20,
        )
        # Find member id
        me = member_client.get(f"{BASE}/api/auth/me", timeout=20).json()
        uid = me["id"]
        before_current = (me.get("intake_completed_at") or "").strip()

        r = admin_client.post(
            f"{BASE}/api/admin/members/{uid}/intake-completion-review",
            json={"action": "reject", "note": "test reject"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert not body.get("pending_intake_completed_at")
        # intake_completed_at untouched
        assert (body.get("intake_completed_at") or "").strip() == before_current

    def test_admin_approve_copies_pending(self, admin_client, member_client):
        import time
        # Pick a value distinct from the current saved one
        me = member_client.get(f"{BASE}/api/auth/me", timeout=20).json()
        current = (me.get("intake_completed_at") or "").strip()
        # Use a timestamp-based year-month to guarantee uniqueness across reruns
        target = f"2015-{(int(time.time()) % 12) + 1:02d}"
        if target == current:
            target = "2014-04"
        # Trigger pending
        member_client.put(
            f"{BASE}/api/members/me",
            json={"intake_completed_at": target},
            timeout=20,
        )
        uid = me["id"]
        r = admin_client.post(
            f"{BASE}/api/admin/members/{uid}/intake-completion-review",
            json={"action": "approve", "note": "test approve"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body.get("intake_completed_at") or "").startswith(target)
        assert not body.get("pending_intake_completed_at")


# ---------- Social media URLs ----------
class TestSocialUrls:
    SOCIAL_FIELDS = {
        "facebook_url": "https://facebook.com/test_aop",
        "instagram_url": "https://instagram.com/test_aop",
        "linkedin_url": "https://linkedin.com/in/test_aop",
        "twitter_url": "https://x.com/test_aop",
        "tiktok_url": "https://tiktok.com/@test_aop",
        "pinterest_url": "https://pinterest.com/test_aop",
        "youtube_url": "https://youtube.com/@test_aop",
        "website_url": "https://test-aop.example.com",
    }

    def test_member_update_social_urls(self, member_client):
        r = member_client.put(
            f"{BASE}/api/members/me", json=self.SOCIAL_FIELDS, timeout=20
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for k, v in self.SOCIAL_FIELDS.items():
            assert body.get(k) == v, f"field {k} not saved: got {body.get(k)}"

    def test_auth_me_returns_social_urls(self, member_client):
        r = member_client.get(f"{BASE}/api/auth/me", timeout=20)
        assert r.status_code == 200
        body = r.json()
        for k, v in self.SOCIAL_FIELDS.items():
            assert body.get(k) == v

    def test_get_member_by_id_returns_social(self, admin_client, member_client):
        me = member_client.get(f"{BASE}/api/auth/me", timeout=20).json()
        uid = me["id"]
        r = admin_client.get(f"{BASE}/api/members/{uid}", timeout=20)
        assert r.status_code == 200
        body = r.json()
        for k, v in self.SOCIAL_FIELDS.items():
            assert body.get(k) == v


# ---------- Free-form chapter creation ----------
class TestChapterCreation:
    created_ids = []

    @pytest.mark.parametrize("chapter_name", ["TEST_Carolinas", "TEST_Midwest", "TEST_Northeast"])
    def test_admin_create_arbitrary_chapter(self, admin_client, chapter_name):
        r = admin_client.post(
            f"{BASE}/api/chapters",
            json={"name": chapter_name, "state": "", "region": ""},
            timeout=20,
        )
        assert r.status_code in (200, 201), f"failed creating {chapter_name}: {r.status_code} {r.text}"
        body = r.json()
        assert body["name"] == chapter_name
        assert "id" in body
        TestChapterCreation.created_ids.append(body["id"])

    def test_cleanup_created_chapters(self, admin_client):
        for cid in TestChapterCreation.created_ids:
            admin_client.delete(f"{BASE}/api/chapters/{cid}", timeout=20)


# ---------- Auth refresh ----------
class TestAuthRefresh:
    def test_refresh_endpoint_works(self):
        s = _login(MEMBER)
        # Simulate access token eviction by removing it from the jar
        for c in list(s.cookies):
            if c.name == "access_token":
                s.cookies.clear(c.domain, c.path, c.name)
        # Try refresh — refresh_token cookie should still be present
        r = s.post(f"{BASE}/api/auth/refresh", timeout=20)
        assert r.status_code == 200, f"refresh failed: {r.status_code} {r.text}"
        # After refresh, /auth/me should work again
        r2 = s.get(f"{BASE}/api/auth/me", timeout=20)
        assert r2.status_code == 200


# ---------- Regression: existing endpoints still work ----------
class TestRegression:
    def test_members_list_admin(self, admin_client):
        r = admin_client.get(f"{BASE}/api/members", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_chapters_list(self, admin_client):
        r = admin_client.get(f"{BASE}/api/chapters", timeout=20)
        assert r.status_code == 200

    def test_events_list(self, admin_client):
        r = admin_client.get(f"{BASE}/api/events", timeout=20)
        assert r.status_code == 200

    def test_donations_endpoint(self, member_client):
        r = member_client.get(f"{BASE}/api/donations/mine", timeout=20)
        # Either 200 or 404, but not 500
        assert r.status_code in (200, 404)

    def test_omega_hero(self, admin_client):
        r = admin_client.get(f"{BASE}/api/omega/hero", timeout=20)
        assert r.status_code == 200
