"""
Phase U — Tests for iteration 20:
  1. home_sections migration: leadership_team in, secondary_banner out
  2. Route-module extraction sanity: /api/pages, /api/site-settings, /api/ai still work after refactor
  3. AI endpoints admin-gating (no actual LLM call required — verify 401/403 for unauth/member)
  4. Auth regression: /api/auth/login, /me, /refresh
  5. Critical route regressions: events/members/chapters/tiers/automated-emails
"""
import os
import uuid

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL is required for tests"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def member_session():
    return _login(MEMBER_EMAIL, MEMBER_PASS)


# ---------------------- Auth flows ----------------------

class TestAuth:
    def test_login_admin_returns_200_and_cookies(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
        assert r.status_code == 200
        # httpOnly cookies should be set
        assert s.cookies.get("access_token") is not None, f"access_token cookie not set; cookies={list(s.cookies.keys())}"

    def test_login_invalid_password_401(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-pw-xyz"}, timeout=15)
        assert r.status_code in (400, 401), f"expected 4xx for invalid login, got {r.status_code}"

    def test_auth_me_admin(self, admin_session):
        r = admin_session.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("email") == ADMIN_EMAIL
        assert d.get("role") == "admin"

    def test_auth_me_member(self, member_session):
        r = member_session.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("email") == MEMBER_EMAIL

    def test_auth_refresh_admin(self, admin_session):
        r = admin_session.post(f"{API}/auth/refresh", timeout=10)
        # Should refresh successfully; some impls return 200 + new cookie
        assert r.status_code == 200, f"refresh failed: {r.status_code} {r.text}"


# ---------------------- Migration: leadership_team in, secondary_banner out ----------------------

class TestLeadershipTeamMigration:
    def test_home_sections_contains_leadership_team(self):
        r = requests.get(f"{API}/site-settings", timeout=10)
        assert r.status_code == 200
        sec = r.json().get("home_sections") or {}
        assert "leadership_team" in sec, f"leadership_team missing from home_sections: {list(sec.keys())}"

    def test_home_sections_does_not_contain_secondary_banner(self):
        r = requests.get(f"{API}/site-settings", timeout=10)
        assert r.status_code == 200
        sec = r.json().get("home_sections") or {}
        assert "secondary_banner" not in sec, f"Migration FAILED: secondary_banner still present in home_sections: {list(sec.keys())}"

    def test_leadership_team_default_true(self):
        r = requests.get(f"{API}/site-settings", timeout=10)
        sec = r.json().get("home_sections") or {}
        assert sec.get("leadership_team") is True, f"leadership_team should default True, got {sec.get('leadership_team')}"

    def test_admin_can_toggle_leadership_team_and_persist(self, admin_session):
        cur = requests.get(f"{API}/site-settings", timeout=10).json()
        saved = dict(cur.get("home_sections") or {})

        # Toggle off
        new_sec = dict(saved)
        new_sec["leadership_team"] = False
        r = admin_session.put(f"{API}/site-settings", json={"home_sections": new_sec}, timeout=15)
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text}"
        assert r.json().get("home_sections", {}).get("leadership_team") is False

        # Verify GET persistence (after migration runs again on next GET — should NOT bring secondary_banner back)
        r2 = requests.get(f"{API}/site-settings", timeout=10)
        sec2 = r2.json().get("home_sections") or {}
        assert sec2.get("leadership_team") is False
        assert "secondary_banner" not in sec2, "migration must not re-introduce secondary_banner"

        # Restore
        r3 = admin_session.put(f"{API}/site-settings", json={"home_sections": saved}, timeout=15)
        assert r3.status_code == 200


# ---------------------- Routes extracted: /api/pages CRUD sanity ----------------------

class TestPagesRouteModule:
    """Verifies routes/pages.py register() wired everything correctly."""
    created_slug = None

    def test_pages_list_public(self):
        r = requests.get(f"{API}/pages", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_pages_get_unknown_returns_404(self):
        r = requests.get(f"{API}/pages/__nonexistent_{uuid.uuid4().hex[:6]}", timeout=10)
        assert r.status_code == 404

    def test_member_cannot_create_page(self, member_session):
        r = member_session.post(f"{API}/pages", json={"slug": "test-x", "title": "x", "body": ""}, timeout=10)
        assert r.status_code in (401, 403)

    def test_unauth_cannot_create_page(self):
        r = requests.post(f"{API}/pages", json={"slug": "test-x", "title": "x", "body": ""}, timeout=10)
        assert r.status_code in (401, 403)

    def test_admin_create_page_with_blocks(self, admin_session):
        slug = f"test-phase-u-{uuid.uuid4().hex[:6]}"
        TestPagesRouteModule.created_slug = slug
        payload = {
            "slug": slug,
            "title": "Phase U Test Page",
            "body": "",
            "blocks": [
                {"id": "b1", "type": "heading", "props": {"text": "Hello", "level": 2}},
                {"id": "b2", "type": "paragraph", "props": {"text": "World"}},
            ],
        }
        r = admin_session.post(f"{API}/pages", json=payload, timeout=15)
        assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
        d = r.json()
        assert d["slug"] == slug
        assert d["title"] == "Phase U Test Page"
        assert len(d["blocks"]) == 2
        assert d["blocks"][0]["type"] == "heading"

    def test_admin_get_created_page(self, admin_session):
        slug = TestPagesRouteModule.created_slug
        assert slug, "previous create test must run first"
        r = requests.get(f"{API}/pages/{slug}", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["slug"] == slug
        assert len(d.get("blocks") or []) == 2

    def test_admin_update_page(self, admin_session):
        slug = TestPagesRouteModule.created_slug
        r = admin_session.put(f"{API}/pages/{slug}", json={"title": "Phase U Updated"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["title"] == "Phase U Updated"

    def test_invalid_block_type_returns_400(self, admin_session):
        slug = f"test-bad-{uuid.uuid4().hex[:6]}"
        r = admin_session.post(f"{API}/pages", json={
            "slug": slug, "title": "bad", "body": "",
            "blocks": [{"id": "x", "type": "NOT_A_TYPE", "props": {}}],
        }, timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_admin_delete_page(self, admin_session):
        slug = TestPagesRouteModule.created_slug
        r = admin_session.delete(f"{API}/pages/{slug}", timeout=10)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/pages/{slug}", timeout=10)
        assert r2.status_code == 404


# ---------------------- /api/site-settings route module sanity ----------------------

class TestSiteSettingsRouteModule:
    def test_get_site_settings_public(self):
        r = requests.get(f"{API}/site-settings", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "home_sections" in d
        assert "home_blocks_top" in d
        assert "home_blocks_bottom" in d
        assert "hero_headline" in d

    def test_member_cannot_put(self, member_session):
        r = member_session.put(f"{API}/site-settings", json={"hero_headline": "hax"}, timeout=10)
        assert r.status_code in (401, 403)

    def test_admin_invalid_block_in_home_blocks_top_400(self, admin_session):
        bad = {"home_blocks_top": [{"id": "x", "type": "BOGUS_TYPE", "props": {}}]}
        r = admin_session.put(f"{API}/site-settings", json=bad, timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"


# ---------------------- /api/ai admin-gating ----------------------

class TestAIRouteModule:
    """Verify admin-only gating without making real LLM calls (member/unauth should 401/403 BEFORE LLM)."""

    def test_ai_event_description_unauth_blocked(self):
        r = requests.post(f"{API}/ai/event-description", json={
            "title": "x", "topic": "y", "audience": "z", "tone": "warm"
        }, timeout=15)
        assert r.status_code in (401, 403), f"unauth should be blocked, got {r.status_code}"

    def test_ai_event_description_member_blocked(self, member_session):
        r = member_session.post(f"{API}/ai/event-description", json={
            "title": "x", "topic": "y", "audience": "z", "tone": "warm"
        }, timeout=15)
        assert r.status_code in (401, 403), f"member should be 403, got {r.status_code}"

    def test_ai_draft_email_unauth_blocked(self):
        r = requests.post(f"{API}/ai/draft-email", json={
            "subject": "x", "goal": "y", "tone": "warm"
        }, timeout=15)
        assert r.status_code in (401, 403)

    def test_ai_draft_email_member_blocked(self, member_session):
        r = member_session.post(f"{API}/ai/draft-email", json={
            "subject": "x", "goal": "y", "tone": "warm"
        }, timeout=15)
        assert r.status_code in (401, 403)


# ---------------------- Critical other routes still working after refactor ----------------------

class TestOtherRoutesRegression:
    def test_events_list(self, admin_session):
        r = admin_session.get(f"{API}/events", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_members_list_admin(self, admin_session):
        r = admin_session.get(f"{API}/members", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_chapters_list(self, admin_session):
        r = admin_session.get(f"{API}/chapters", timeout=10)
        assert r.status_code == 200

    def test_tiers_list(self, admin_session):
        r = admin_session.get(f"{API}/tiers", timeout=10)
        assert r.status_code == 200

    def test_automated_emails_list(self, admin_session):
        r = admin_session.get(f"{API}/automated-emails", timeout=10)
        assert r.status_code == 200
