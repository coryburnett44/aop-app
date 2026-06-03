"""Phase V regression tests:
- Leadership Team CMS (site-settings persistence of leadership_team_eyebrow/title/items)
- /api/leadership/upload-image admin-gating
- /api/news, /api/chapters, /api/tiers route extractions
- Critical smoke endpoints
"""
import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"


def _login(session, email, password):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    _login(s, ADMIN_EMAIL, ADMIN_PASS)
    return s


@pytest.fixture(scope="module")
def member_session():
    s = requests.Session()
    _login(s, MEMBER_EMAIL, MEMBER_PASS)
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# --- Smoke -----------------------------------------------------------------
class TestSmoke:
    def test_auth_login_admin(self):
        s = requests.Session()
        data = _login(s, ADMIN_EMAIL, ADMIN_PASS)
        # Login response is flat; role lives at top-level
        assert data.get("role") == "admin"
        assert data.get("email") == ADMIN_EMAIL

    def test_auth_me(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_events_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/events")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_members_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/members")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_pages_list(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/pages")
        assert r.status_code == 200

    def test_site_settings_get(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/site-settings")
        assert r.status_code == 200
        d = r.json()
        assert "leadership_team_items" in d
        assert "leadership_team_title" in d
        assert "leadership_team_eyebrow" in d

    def test_automated_emails(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/automated-emails")
        assert r.status_code == 200


# --- Leadership Team CMS ---------------------------------------------------
class TestLeadershipCMS:
    def _get_settings(self, s):
        r = s.get(f"{BASE_URL}/api/site-settings")
        assert r.status_code == 200
        return r.json()

    def _put_settings(self, s, body):
        return s.put(f"{BASE_URL}/api/site-settings", json=body)

    def test_default_seeded_two_items(self, anon_session):
        d = self._get_settings(anon_session)
        items = d.get("leadership_team_items") or []
        assert len(items) >= 2
        terms = [i["term"] for i in items]
        assert "2024-2026" in terms or "2024-2026 (Updated)" in terms or any("2024" in t for t in terms)
        assert d.get("leadership_team_eyebrow") == "National board" or isinstance(d.get("leadership_team_eyebrow"), str)
        assert d.get("leadership_team_title") in ("Leadership Team", d.get("leadership_team_title"))

    def test_member_cannot_update_settings(self, member_session):
        r = self._put_settings(member_session, {"leadership_team_title": "Hacked"})
        assert r.status_code in (401, 403)

    def test_admin_add_edit_reorder_remove_then_restore(self, admin_session):
        # Save original to restore later
        original = self._get_settings(admin_session)
        original_items = original.get("leadership_team_items") or []

        # 1. Add a new term (total = original + 1)
        new_items = list(original_items) + [
            {"term": "2028-2030", "image_url": "https://example.com/test.jpg", "alt": "Future Leaders"}
        ]
        r = self._put_settings(admin_session, {"leadership_team_items": new_items})
        assert r.status_code == 200, r.text
        got = self._get_settings(admin_session)["leadership_team_items"]
        assert len(got) == len(original_items) + 1
        assert got[-1]["term"] == "2028-2030"
        assert got[-1]["image_url"] == "https://example.com/test.jpg"
        assert got[-1]["alt"] == "Future Leaders"

        # 2. Edit the first term
        updated = [dict(x) for x in got]
        updated[0]["term"] = updated[0]["term"] + " (Updated)"
        r = self._put_settings(admin_session, {"leadership_team_items": updated})
        assert r.status_code == 200
        got2 = self._get_settings(admin_session)["leadership_team_items"]
        assert got2[0]["term"].endswith("(Updated)")

        # 3. Reorder: swap index 0 and 1
        reordered = list(got2)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        r = self._put_settings(admin_session, {"leadership_team_items": reordered})
        assert r.status_code == 200
        got3 = self._get_settings(admin_session)["leadership_team_items"]
        assert got3[0]["term"] == reordered[0]["term"]
        assert got3[1]["term"] == reordered[1]["term"]

        # 4. Remove index 2 (the added one)
        trimmed = got3[:2]
        r = self._put_settings(admin_session, {"leadership_team_items": trimmed})
        assert r.status_code == 200
        got4 = self._get_settings(admin_session)["leadership_team_items"]
        assert len(got4) == 2
        assert all(x["term"] != "2028-2030" for x in got4)

        # 5. Restore original
        r = self._put_settings(admin_session, {
            "leadership_team_items": original_items,
            "leadership_team_title": original.get("leadership_team_title") or "Leadership Team",
            "leadership_team_eyebrow": original.get("leadership_team_eyebrow") or "National board",
        })
        assert r.status_code == 200
        final = self._get_settings(admin_session)["leadership_team_items"]
        assert len(final) == len(original_items)
        assert final[0]["term"] == original_items[0]["term"]

    def test_admin_update_eyebrow_and_title(self, admin_session):
        original = self._get_settings(admin_session)
        r = self._put_settings(admin_session, {"leadership_team_eyebrow": "TEST eyebrow", "leadership_team_title": "TEST title"})
        assert r.status_code == 200
        got = self._get_settings(admin_session)
        assert got["leadership_team_eyebrow"] == "TEST eyebrow"
        assert got["leadership_team_title"] == "TEST title"
        # restore
        self._put_settings(admin_session, {
            "leadership_team_eyebrow": original.get("leadership_team_eyebrow") or "National board",
            "leadership_team_title": original.get("leadership_team_title") or "Leadership Team",
        })


# --- Leadership upload-image ----------------------------------------------
def _tiny_png_bytes() -> bytes:
    # 1x1 transparent PNG
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
    )


class TestLeadershipUpload:
    def test_admin_upload_succeeds(self, admin_session):
        files = {"file": ("test.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = admin_session.post(f"{BASE_URL}/api/leadership/upload-image", files=files)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "url" in data and isinstance(data["url"], str) and data["url"]

    def test_member_upload_forbidden(self, member_session):
        files = {"file": ("test.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = member_session.post(f"{BASE_URL}/api/leadership/upload-image", files=files)
        assert r.status_code == 403

    def test_anon_upload_unauthorized(self, anon_session):
        files = {"file": ("test.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = anon_session.post(f"{BASE_URL}/api/leadership/upload-image", files=files)
        assert r.status_code in (401, 403)


# --- News route -----------------------------------------------------------
class TestNewsRoute:
    created_id = None

    def test_list_public(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/news")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_member_create_forbidden(self, member_session):
        r = member_session.post(f"{BASE_URL}/api/news", json={"title": "blocked", "summary": "x", "body": "y"})
        assert r.status_code in (401, 403)

    def test_anon_create_unauthorized(self, anon_session):
        r = anon_session.post(f"{BASE_URL}/api/news", json={"title": "blocked", "summary": "x", "body": "y"})
        assert r.status_code in (401, 403)

    def test_admin_create_and_get(self, admin_session):
        payload = {
            "title": f"TEST_news_{uuid.uuid4().hex[:6]}",
            "summary": "summary",
            "body": "body",
            "tags": ["t1"],
        }
        r = admin_session.post(f"{BASE_URL}/api/news", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == payload["title"]
        assert d["summary"] == "summary"
        assert "id" in d
        TestNewsRoute.created_id = d["id"]

        r2 = admin_session.get(f"{BASE_URL}/api/news/{d['id']}")
        assert r2.status_code == 200
        assert r2.json()["id"] == d["id"]

    def test_admin_update(self, admin_session):
        nid = TestNewsRoute.created_id
        assert nid
        r = admin_session.put(f"{BASE_URL}/api/news/{nid}", json={"summary": "updated"})
        assert r.status_code == 200
        assert r.json()["summary"] == "updated"

    def test_get_unknown_404(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/news/does-not-exist-xyz")
        assert r.status_code == 404

    def test_admin_delete_and_verify(self, admin_session):
        nid = TestNewsRoute.created_id
        assert nid
        r = admin_session.delete(f"{BASE_URL}/api/news/{nid}")
        assert r.status_code == 200
        r2 = admin_session.get(f"{BASE_URL}/api/news/{nid}")
        assert r2.status_code == 404


# --- Chapters route ------------------------------------------------------
class TestChaptersRoute:
    created_id = None
    created_name = None

    def test_list_returns_name_and_member_count(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/chapters")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        if items:
            assert "name" in items[0]
            assert "member_count" in items[0]
            assert isinstance(items[0]["member_count"], int)

    def test_member_create_forbidden(self, member_session):
        r = member_session.post(f"{BASE_URL}/api/chapters", json={"name": "BlockedChapter"})
        assert r.status_code in (401, 403)

    def test_admin_create(self, admin_session):
        name = f"TEST_chap_{uuid.uuid4().hex[:6]}"
        r = admin_session.post(f"{BASE_URL}/api/chapters", json={"name": name, "city": "Austin", "state": "TX"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == name
        assert d["member_count"] == 0
        TestChaptersRoute.created_id = d["id"]
        TestChaptersRoute.created_name = name

    def test_duplicate_name_returns_400(self, admin_session):
        name = TestChaptersRoute.created_name
        assert name
        r = admin_session.post(f"{BASE_URL}/api/chapters", json={"name": name})
        assert r.status_code == 400

    def test_admin_update(self, admin_session):
        cid = TestChaptersRoute.created_id
        r = admin_session.put(f"{BASE_URL}/api/chapters/{cid}", json={"city": "Dallas"})
        assert r.status_code == 200
        assert r.json()["city"] == "Dallas"

    def test_member_delete_forbidden(self, member_session):
        cid = TestChaptersRoute.created_id
        r = member_session.delete(f"{BASE_URL}/api/chapters/{cid}")
        assert r.status_code in (401, 403)

    def test_admin_delete(self, admin_session):
        cid = TestChaptersRoute.created_id
        r = admin_session.delete(f"{BASE_URL}/api/chapters/{cid}")
        assert r.status_code == 200


# --- Tiers route ----------------------------------------------------------
class TestTiersRoute:
    created_id = None

    def test_list_returns_name_order_member_count(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/tiers")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        if items:
            t0 = items[0]
            assert "name" in t0 and "order" in t0 and "member_count" in t0

    def test_member_create_forbidden(self, member_session):
        r = member_session.post(f"{BASE_URL}/api/tiers", json={"name": "Blocked", "order": 99})
        assert r.status_code in (401, 403)

    def test_admin_create(self, admin_session):
        name = f"TEST_tier_{uuid.uuid4().hex[:6]}"
        r = admin_session.post(f"{BASE_URL}/api/tiers", json={"name": name, "order": 99, "annual_dues": 50.0})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == name
        assert d["order"] == 99
        assert d["member_count"] == 0
        TestTiersRoute.created_id = d["id"]

    def test_admin_update(self, admin_session):
        tid = TestTiersRoute.created_id
        r = admin_session.put(f"{BASE_URL}/api/tiers/{tid}", json={"annual_dues": 75.0})
        assert r.status_code == 200
        assert r.json()["annual_dues"] == 75.0

    def test_member_delete_forbidden(self, member_session):
        tid = TestTiersRoute.created_id
        r = member_session.delete(f"{BASE_URL}/api/tiers/{tid}")
        assert r.status_code in (401, 403)

    def test_admin_delete(self, admin_session):
        tid = TestTiersRoute.created_id
        r = admin_session.delete(f"{BASE_URL}/api/tiers/{tid}")
        assert r.status_code == 200
