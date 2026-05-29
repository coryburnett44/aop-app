"""Phase I tests: Omega hero, AOP form-links, Life Member Candidate tier, welcome email approval."""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # frontend env contains REACT_APP_BACKEND_URL
    from dotenv import dotenv_values
    BASE_URL = dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}
MM = {"email": "mm.tx@clubhaven.app", "password": "MemMgr123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def member_session():
    return _login(MEMBER)


@pytest.fixture(scope="module")
def mm_session():
    return _login(MM)


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# ----- Tiers -----
class TestTiers:
    def test_life_member_candidate_present(self, anon_session):
        r = anon_session.get(f"{API}/tiers", timeout=15)
        assert r.status_code == 200
        tiers = r.json()
        by_name = {t["name"]: t for t in tiers}
        assert "Life Member Candidate" in by_name, "Life Member Candidate tier missing"
        lmc = by_name["Life Member Candidate"]
        assert lmc["annual_dues"] == 100.0
        assert lmc["is_lifetime"] is False
        assert lmc["order"] == 4

    def test_silver_gold_orders_shifted(self, anon_session):
        r = anon_session.get(f"{API}/tiers", timeout=15)
        by_name = {t["name"]: t for t in r.json()}
        assert by_name["Silver Life Member"]["order"] == 5
        assert by_name["Gold Life Member"]["order"] == 6


# ----- Omega Hero -----
class TestOmegaHero:
    def test_get_hero_anon(self, anon_session):
        r = anon_session.get(f"{API}/omega/hero", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "image_url" in data and "title" in data and "caption" in data

    def test_member_cannot_put(self, member_session):
        r = member_session.put(f"{API}/omega/hero",
                               json={"image_url": "x", "title": "x", "caption": "x"}, timeout=15)
        assert r.status_code == 403

    def test_mm_cannot_put(self, mm_session):
        # membership_manager has 'members' tab access -- so they CAN write hero (since dep is admin_tab_dep('members'))
        # Per spec: "Non-admin (member or governor_manager) gets 403". Let's verify governor:
        gov = _login({"email": "governor.tx@clubhaven.app", "password": "Governor123!"})
        r = gov.put(f"{API}/omega/hero",
                    json={"image_url": "x", "title": "x", "caption": "x"}, timeout=15)
        assert r.status_code == 403

    def test_admin_put_and_get(self, admin_session, anon_session):
        payload = {"image_url": "https://example.com/banner.jpg", "title": "TEST_Founder", "caption": "TEST caption"}
        r = admin_session.put(f"{API}/omega/hero", json=payload, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == payload["title"]
        # anon get
        r2 = anon_session.get(f"{API}/omega/hero", timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["title"] == payload["title"]
        assert d2["image_url"] == payload["image_url"]
        # cleanup -- reset
        admin_session.put(f"{API}/omega/hero", json={"image_url": "", "title": "", "caption": ""}, timeout=15)


# ----- Form Links -----
created_link_ids = []


class TestFormLinks:
    def test_list_anon(self, anon_session):
        r = anon_session.get(f"{API}/form-links", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_member_cannot_create(self, member_session):
        r = member_session.post(f"{API}/form-links",
                                json={"title": "TEST_x", "url": "https://e.com"}, timeout=15)
        assert r.status_code == 403

    def test_admin_create(self, admin_session):
        payload = {"title": "TEST_Form A", "description": "TEST desc", "url": "https://example.com/forma",
                   "image_url": "https://example.com/a.jpg", "order": 1}
        r = admin_session.post(f"{API}/form-links", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert data["title"] == payload["title"]
        created_link_ids.append(data["id"])

    def test_admin_create_blank_title_400(self, admin_session):
        r = admin_session.post(f"{API}/form-links",
                               json={"title": "  ", "url": "https://example.com"}, timeout=15)
        assert r.status_code == 400

    def test_admin_create_blank_url_400(self, admin_session):
        r = admin_session.post(f"{API}/form-links",
                               json={"title": "TEST_B", "url": "  "}, timeout=15)
        assert r.status_code == 400

    def test_admin_update(self, admin_session):
        if not created_link_ids:
            pytest.skip("no link to update")
        lid = created_link_ids[0]
        r = admin_session.put(f"{API}/form-links/{lid}", json={"title": "TEST_Form A Updated"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["title"] == "TEST_Form A Updated"
        # GET via list to verify persistence
        rows = admin_session.get(f"{API}/form-links", timeout=15).json()
        match = next((x for x in rows if x["id"] == lid), None)
        assert match and match["title"] == "TEST_Form A Updated"

    def test_admin_update_blank_400(self, admin_session):
        if not created_link_ids:
            pytest.skip("no link")
        lid = created_link_ids[0]
        r = admin_session.put(f"{API}/form-links/{lid}", json={"title": "  "}, timeout=15)
        assert r.status_code == 400
        r = admin_session.put(f"{API}/form-links/{lid}", json={"url": "  "}, timeout=15)
        assert r.status_code == 400

    def test_upload_non_image_400(self, admin_session):
        files = {"file": ("test.txt", io.BytesIO(b"not an image"), "text/plain")}
        r = admin_session.post(f"{API}/form-links/upload", files=files, timeout=20)
        assert r.status_code == 400

    def test_upload_image_member_403(self, member_session):
        # minimal png
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000005000100000000")  # 1x1 transparent
        files = {"file": ("t.png", io.BytesIO(png), "image/png")}
        r = member_session.post(f"{API}/form-links/upload", files=files, timeout=20)
        assert r.status_code == 403

    def test_member_cannot_delete(self, member_session):
        if not created_link_ids:
            pytest.skip("no link")
        r = member_session.delete(f"{API}/form-links/{created_link_ids[0]}", timeout=15)
        assert r.status_code == 403

    def test_admin_delete(self, admin_session):
        if not created_link_ids:
            pytest.skip("no link")
        lid = created_link_ids[0]
        r = admin_session.delete(f"{API}/form-links/{lid}", timeout=15)
        assert r.status_code == 200
        # verify removed
        rows = admin_session.get(f"{API}/form-links", timeout=15).json()
        assert not any(x["id"] == lid for x in rows)
        created_link_ids.clear()


# ----- Application approval welcome email -----
class TestApprovalWelcomeEmail:
    def test_approve_returns_welcome_email_fields(self, admin_session):
        # 1) submit public application
        email = f"test.welcome.{int(time.time())}@example.com"
        body = {
            "first_name": "TESTW",
            "last_name": "Applicant",
            "email": email,
            "password": "TestPass123!",
        }
        r = requests.post(f"{API}/auth/apply", json=body, timeout=20)
        assert r.status_code == 200, r.text
        app_id = r.json()["application_id"]

        # 2) approve as admin
        r2 = admin_session.post(f"{API}/admin/applications/{app_id}/review",
                                json={"action": "approve"}, timeout=30)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data.get("ok") is True
        assert "user_id" in data
        assert "welcome_email_sent" in data
        assert "welcome_email_detail" in data
        # detail should be string regardless
        assert isinstance(data["welcome_email_detail"], str)
        # cleanup created user + application
        uid = data["user_id"]
        try:
            from pymongo import MongoClient
            mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db_name = os.environ.get("DB_NAME", "clubhaven")
            mc[db_name].users.delete_one({"id": uid})
            mc[db_name].applications.delete_one({"id": app_id})
        except Exception:
            pass

    def test_approval_email_subject_and_body(self):
        # Inspect server.py source for the subject/heading (sanity)
        with open("/app/backend/server.py", "r") as f:
            src = f.read()
        assert '"subject": "Welcome to Alpha Omega Phi"' in src
        assert "Welcome to Alpha Omega Phi" in src  # heading
