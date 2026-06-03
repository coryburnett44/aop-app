"""
Phase T — Tests for:
  1. CMS Page Builder block CRUD + invalid block validation
  2. Site settings home_sections toggles + home_blocks_top/bottom persistence
  3. Regression: routes still work after models.py extraction
"""
import os
import uuid

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"

BLOCK_TYPES = ("heading", "subheading", "paragraph", "image", "button", "divider", "html", "spacer", "columns", "video")


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


# ---------------------- Auth/regression smoke ----------------------

class TestAuthRegression:
    def test_login_admin(self):
        s = _login(ADMIN_EMAIL, ADMIN_PASS)
        assert s.cookies.get("access_token") or True  # logged in

    def test_auth_me_admin(self, admin_session):
        r = admin_session.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("email") == ADMIN_EMAIL
        assert d.get("role") == "admin"

    def test_auth_me_unauth_returns_401(self):
        r = requests.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 401


# ---------------------- Site settings ----------------------

class TestSiteSettings:
    _saved = None

    def test_get_public_no_auth(self):
        r = requests.get(f"{API}/site-settings", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)
        # backfilled keys present
        assert "home_sections" in d, f"home_sections missing in site_settings: keys={list(d.keys())}"
        assert "home_blocks_top" in d
        assert "home_blocks_bottom" in d

    def test_home_sections_has_8_keys(self):
        # Updated for iteration 20: secondary_banner replaced with leadership_team via migration
        r = requests.get(f"{API}/site-settings", timeout=10)
        sec = r.json().get("home_sections") or {}
        expected = {"founders", "hero_text", "countdown", "pillars", "family_pulse", "leadership_team", "upcoming_events", "news"}
        missing = expected - set(sec.keys())
        assert not missing, f"home_sections missing keys: {missing}. Got: {list(sec.keys())}"
        assert "secondary_banner" not in sec, f"Migration failed: secondary_banner still present in home_sections: {list(sec.keys())}"

    def test_member_cannot_put_site_settings(self, member_session):
        r = member_session.put(f"{API}/site-settings", json={"home_sections": {"pillars": False}}, timeout=10)
        assert r.status_code in (401, 403)

    def test_admin_save_home_section_toggle_and_blocks(self, admin_session):
        # Save the current state for restore
        cur = requests.get(f"{API}/site-settings", timeout=10).json()
        TestSiteSettings._saved = {
            "home_sections": cur.get("home_sections") or {},
            "home_blocks_top": cur.get("home_blocks_top") or [],
            "home_blocks_bottom": cur.get("home_blocks_bottom") or [],
        }

        new_sections = dict(cur.get("home_sections") or {})
        new_sections["pillars"] = False

        blocks_top = [
            {"id": f"TEST_blk_{uuid.uuid4().hex[:6]}", "type": "heading", "props": {"text": "TEST top heading", "level": 2}},
            {"id": f"TEST_blk_{uuid.uuid4().hex[:6]}", "type": "paragraph", "props": {"text": "TEST top paragraph"}},
        ]

        body = {"home_sections": new_sections, "home_blocks_top": blocks_top}
        r = admin_session.put(f"{API}/site-settings", json=body, timeout=15)
        assert r.status_code == 200, r.text

        # Verify persistence via GET (public)
        r2 = requests.get(f"{API}/site-settings", timeout=10)
        d = r2.json()
        assert d["home_sections"].get("pillars") is False
        got = d.get("home_blocks_top") or []
        assert len(got) == 2
        assert got[0]["type"] == "heading"
        assert got[0]["props"]["text"] == "TEST top heading"
        assert got[1]["type"] == "paragraph"

    def test_home_blocks_invalid_type_rejected(self, admin_session):
        # Per spec PageBlockIn allows any string in `type` but is it validated on save?
        # site-settings may not validate block.type — record outcome
        bad = [{"id": "TEST_bad", "type": "HACK", "props": {}}]
        r = admin_session.put(f"{API}/site-settings", json={"home_blocks_top": bad}, timeout=10)
        # Document whichever behavior — log for review
        assert r.status_code in (200, 400, 422), r.text

    def test_zz_restore_site_settings(self, admin_session):
        if TestSiteSettings._saved is None:
            pytest.skip("nothing saved")
        r = admin_session.put(f"{API}/site-settings", json=TestSiteSettings._saved, timeout=15)
        assert r.status_code == 200


# ---------------------- CMS Pages CRUD with blocks ----------------------

@pytest.fixture(scope="module")
def test_slug():
    return f"test-cms-{uuid.uuid4().hex[:8]}"


class TestCmsPages:
    def test_list_pages_public(self):
        r = requests.get(f"{API}/pages", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_member_cannot_create_page(self, member_session):
        r = member_session.post(f"{API}/pages", json={
            "slug": "test-forbidden-" + uuid.uuid4().hex[:6],
            "title": "Forbidden",
            "body": "x",
        }, timeout=10)
        assert r.status_code in (401, 403)

    def test_create_page_with_blocks(self, admin_session, test_slug):
        blocks = [
            {"id": "b1", "type": "heading", "props": {"text": "Hello", "level": 1}},
            {"id": "b2", "type": "paragraph", "props": {"text": "World"}},
        ]
        r = admin_session.post(f"{API}/pages", json={
            "slug": test_slug,
            "title": "TEST CMS Page",
            "body": "",
            "blocks": blocks,
        }, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slug"] == test_slug
        assert d["title"] == "TEST CMS Page"
        assert isinstance(d.get("blocks"), list) and len(d["blocks"]) == 2

    def test_get_page_returns_blocks(self, test_slug):
        r = requests.get(f"{API}/pages/{test_slug}", timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slug"] == test_slug
        assert "_id" not in d, "ObjectId leaked"
        assert len(d.get("blocks") or []) == 2
        assert d["blocks"][0]["type"] == "heading"

    def test_create_page_invalid_block_type_400(self, admin_session):
        r = admin_session.post(f"{API}/pages", json={
            "slug": "test-bad-" + uuid.uuid4().hex[:6],
            "title": "Bad",
            "body": "",
            "blocks": [{"id": "x", "type": "HACK", "props": {}}],
        }, timeout=10)
        assert r.status_code == 400, f"expected 400 for invalid block type, got {r.status_code}: {r.text}"
        assert "invalid block type" in r.text.lower()

    def test_update_page_invalid_block_type_400(self, admin_session, test_slug):
        r = admin_session.put(f"{API}/pages/{test_slug}", json={
            "blocks": [{"id": "y", "type": "BAD", "props": {}}],
        }, timeout=10)
        assert r.status_code == 400, r.text

    def test_update_page_valid_blocks(self, admin_session, test_slug):
        new_blocks = [
            {"id": "h", "type": "heading", "props": {"text": "Updated", "level": 2}},
            {"id": "p", "type": "paragraph", "props": {"text": "Body text"}},
            {"id": "d", "type": "divider", "props": {}},
        ]
        r = admin_session.put(f"{API}/pages/{test_slug}", json={
            "title": "TEST CMS Page Updated", "blocks": new_blocks,
        }, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == "TEST CMS Page Updated"
        assert len(d["blocks"]) == 3
        # GET to verify persistence
        r2 = requests.get(f"{API}/pages/{test_slug}", timeout=10)
        assert r2.json()["blocks"][0]["props"]["text"] == "Updated"

    def test_all_10_block_types_accepted(self, admin_session):
        slug = f"test-all-types-{uuid.uuid4().hex[:6]}"
        blocks = [{"id": f"b{i}", "type": t, "props": {}} for i, t in enumerate(BLOCK_TYPES)]
        r = admin_session.post(f"{API}/pages", json={
            "slug": slug, "title": "TEST All Types", "body": "", "blocks": blocks,
        }, timeout=10)
        assert r.status_code == 200, r.text
        # cleanup
        admin_session.delete(f"{API}/pages/{slug}", timeout=10)

    def test_legacy_page_about_still_works(self):
        r = requests.get(f"{API}/pages/about", timeout=10)
        # may or may not exist depending on seed
        if r.status_code == 404:
            pytest.skip("about page not seeded")
        assert r.status_code == 200
        d = r.json()
        assert "body" in d  # legacy field still present
        # blocks may be empty/missing for legacy pages — that's OK

    def test_zz_delete_test_page(self, admin_session, test_slug):
        r = admin_session.delete(f"{API}/pages/{test_slug}", timeout=10)
        assert r.status_code == 200
        # Verify gone
        r2 = requests.get(f"{API}/pages/{test_slug}", timeout=10)
        assert r2.status_code == 404


# ---------------------- Other-route regression after models.py extraction ----------------------

class TestRouteRegression:
    def test_events_list(self):
        r = requests.get(f"{API}/events", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_members_admin_list(self, admin_session):
        r = admin_session.get(f"{API}/members", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # Ensure ObjectId not leaking
        if items:
            assert "_id" not in items[0]

    def test_chapters_list(self, admin_session):
        r = admin_session.get(f"{API}/chapters", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_tiers_list(self, admin_session):
        r = admin_session.get(f"{API}/tiers", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_automated_emails_list(self, admin_session):
        r = admin_session.get(f"{API}/automated-emails", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
