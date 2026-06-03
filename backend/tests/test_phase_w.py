"""Phase W regression tests:
- Email-or-username login (BACKEND auth)
- HttpUrl-style validation for LeadershipItemIn.image_url + FounderItemIn.image_url
- /api/founders/upload-image admin-gating
- /api/events/upload-cover admin-gating
"""
import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
ADMIN_USERNAME = "clubadmin"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"


def _login(session, email_or_username, password):
    return session.post(f"{BASE_URL}/api/auth/login", json={"email": email_or_username, "password": password})


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
def anon_session():
    return requests.Session()


def _tiny_png_bytes() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
    )


# --- Email-or-username login ---------------------------------------------
class TestLoginEmailOrUsername:
    def test_login_by_email(self):
        s = requests.Session()
        r = _login(s, ADMIN_EMAIL, ADMIN_PASS)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("email") == ADMIN_EMAIL
        assert d.get("role") == "admin"

    def test_login_by_username(self):
        s = requests.Session()
        r = _login(s, ADMIN_USERNAME, ADMIN_PASS)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("email") == ADMIN_EMAIL
        assert d.get("role") == "admin"

    def test_login_by_username_case_insensitive(self):
        s = requests.Session()
        r = _login(s, ADMIN_USERNAME.upper(), ADMIN_PASS)
        assert r.status_code == 200, r.text
        assert r.json().get("email") == ADMIN_EMAIL

    def test_login_invalid_user_returns_401(self):
        s = requests.Session()
        r = _login(s, "baduser_xyz_does_not_exist", "anything")
        assert r.status_code == 401
        # Verify error message updated
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = r.text
        assert "email/username" in str(detail).lower() or "invalid" in str(detail).lower()

    def test_login_invalid_email_returns_401(self):
        s = requests.Session()
        r = _login(s, "noone@nowhere.test", "anything")
        assert r.status_code == 401

    def test_login_wrong_password_returns_401(self):
        s = requests.Session()
        r = _login(s, ADMIN_EMAIL, "WrongPass123!")
        assert r.status_code == 401


# --- Leadership image_url URL validation ----------------------------------
class TestLeadershipImageUrlValidation:
    def _get_settings(self, s):
        r = s.get(f"{BASE_URL}/api/site-settings")
        assert r.status_code == 200
        return r.json()

    def test_invalid_url_rejected_422(self, admin_session):
        original = self._get_settings(admin_session)
        items = list(original.get("leadership_team_items") or [])
        bad = items + [{"term": "TESTBAD", "image_url": "not a url", "alt": "x"}]
        r = admin_session.put(f"{BASE_URL}/api/site-settings", json={"leadership_team_items": bad})
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text}"
        # Verify Pydantic error message about URL
        body = r.text.lower()
        assert "url" in body or "path" in body

    def test_full_https_url_accepted(self, admin_session):
        original = self._get_settings(admin_session)
        items = list(original.get("leadership_team_items") or [])
        new = items + [{"term": "TEST_PHW_HTTPS", "image_url": "https://example.com/foo.jpg", "alt": "x"}]
        r = admin_session.put(f"{BASE_URL}/api/site-settings", json={"leadership_team_items": new})
        assert r.status_code == 200, r.text
        # restore
        admin_session.put(f"{BASE_URL}/api/site-settings", json={"leadership_team_items": items})

    def test_relative_path_accepted(self, admin_session):
        original = self._get_settings(admin_session)
        items = list(original.get("leadership_team_items") or [])
        new = items + [{"term": "TEST_PHW_REL", "image_url": "/api/files/leadership/abc.jpg", "alt": "x"}]
        r = admin_session.put(f"{BASE_URL}/api/site-settings", json={"leadership_team_items": new})
        assert r.status_code == 200, r.text
        # restore
        admin_session.put(f"{BASE_URL}/api/site-settings", json={"leadership_team_items": items})

    def test_empty_string_accepted(self, admin_session):
        original = self._get_settings(admin_session)
        items = list(original.get("leadership_team_items") or [])
        new = items + [{"term": "TEST_PHW_EMPTY", "image_url": "", "alt": "x"}]
        r = admin_session.put(f"{BASE_URL}/api/site-settings", json={"leadership_team_items": new})
        assert r.status_code == 200, r.text
        # restore
        admin_session.put(f"{BASE_URL}/api/site-settings", json={"leadership_team_items": items})


# --- Founders image_url URL validation + persistence ----------------------
class TestFoundersValidation:
    def _get_settings(self, s):
        r = s.get(f"{BASE_URL}/api/site-settings")
        assert r.status_code == 200
        return r.json()

    def test_founders_fields_exist(self, anon_session):
        d = self._get_settings(anon_session)
        # The keys are part of the API contract
        assert "founders_items" in d, f"founders_items missing: keys={list(d.keys())[:30]}"
        assert isinstance(d["founders_items"], list)

    def test_founders_invalid_url_rejected_422(self, admin_session):
        original = self._get_settings(admin_session)
        items = list(original.get("founders_items") or [])
        bad = items + [{"name": "TESTBAD", "role": "x", "image_url": "not a url"}]
        r = admin_session.put(f"{BASE_URL}/api/site-settings", json={"founders_items": bad})
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text}"

    def test_founders_full_url_and_relative_accepted(self, admin_session):
        original = self._get_settings(admin_session)
        items = list(original.get("founders_items") or [])
        new_items = items + [
            {"name": "TEST_PHW_https", "role": "x", "image_url": "https://example.com/p.jpg"},
            {"name": "TEST_PHW_rel", "role": "x", "image_url": "/api/files/founders/p.jpg"},
            {"name": "TEST_PHW_empty", "role": "x", "image_url": ""},
        ]
        r = admin_session.put(f"{BASE_URL}/api/site-settings", json={"founders_items": new_items})
        assert r.status_code == 200, r.text
        got = self._get_settings(admin_session)["founders_items"]
        # ensure persisted
        names = [i.get("name") for i in got]
        assert "TEST_PHW_https" in names and "TEST_PHW_rel" in names and "TEST_PHW_empty" in names
        # restore
        admin_session.put(f"{BASE_URL}/api/site-settings", json={"founders_items": items})
        restored = self._get_settings(admin_session)["founders_items"]
        assert len(restored) == len(items)

    def test_member_cannot_update_founders(self, member_session):
        r = member_session.put(f"{BASE_URL}/api/site-settings", json={"founders_items": []})
        assert r.status_code in (401, 403)


# --- Founders upload-image -----------------------------------------------
class TestFoundersUpload:
    def test_admin_upload_succeeds(self, admin_session):
        files = {"file": ("test.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = admin_session.post(f"{BASE_URL}/api/founders/upload-image", files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "url" in d and isinstance(d["url"], str) and d["url"]

    def test_member_upload_forbidden(self, member_session):
        files = {"file": ("test.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = member_session.post(f"{BASE_URL}/api/founders/upload-image", files=files)
        assert r.status_code == 403

    def test_anon_upload_unauthorized(self, anon_session):
        files = {"file": ("test.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = anon_session.post(f"{BASE_URL}/api/founders/upload-image", files=files)
        assert r.status_code in (401, 403)


# --- Events upload-cover -------------------------------------------------
class TestEventsUploadCover:
    def test_admin_upload_succeeds(self, admin_session):
        files = {"file": ("event.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = admin_session.post(f"{BASE_URL}/api/events/upload-cover", files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "url" in d and isinstance(d["url"], str) and d["url"]

    def test_member_upload_forbidden(self, member_session):
        files = {"file": ("event.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = member_session.post(f"{BASE_URL}/api/events/upload-cover", files=files)
        assert r.status_code == 403

    def test_anon_upload_unauthorized(self, anon_session):
        files = {"file": ("event.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
        r = anon_session.post(f"{BASE_URL}/api/events/upload-cover", files=files)
        assert r.status_code in (401, 403)


# --- Regression smoke ----------------------------------------------------
class TestSmoke:
    def test_auth_me(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_events_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/events")
        assert r.status_code == 200

    def test_members_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/members")
        assert r.status_code == 200

    def test_pages_list(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/pages")
        assert r.status_code == 200

    def test_site_settings_get(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/site-settings")
        assert r.status_code == 200
        d = r.json()
        assert "leadership_team_items" in d
        assert "founders_items" in d

    def test_automated_emails(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/automated-emails")
        assert r.status_code == 200
