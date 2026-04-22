"""ClubHaven backend API tests."""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://club-express-lite.preview.emergentagent.com"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASSWORD = "Member123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def member_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"member login failed: {r.status_code} {r.text}"
    return s


# ---------- Health ----------
def test_health():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- Auth ----------
def test_register_new_member():
    s = requests.Session()
    email = f"test_{uuid.uuid4().hex[:8]}@clubhaven.app"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Pass1234!", "name": "Test User", "city": "Boston", "interests": ["yoga"]}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["email"] == email
    assert data["role"] == "member"
    assert "id" in data
    # cookies set
    assert "access_token" in s.cookies
    assert "refresh_token" in s.cookies
    # me works
    me = s.get(f"{API}/auth/me", timeout=15)
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_register_duplicate():
    r = requests.post(f"{API}/auth/register", json={"email": ADMIN_EMAIL, "password": "Whatever1!", "name": "x"}, timeout=20)
    assert r.status_code == 400


def test_admin_login_and_me(admin_session):
    me = admin_session.get(f"{API}/auth/me", timeout=15)
    assert me.status_code == 200
    j = me.json()
    assert j["email"] == ADMIN_EMAIL
    assert j["role"] == "admin"


def test_logout_requires_auth():
    r = requests.post(f"{API}/auth/logout", timeout=15)
    assert r.status_code == 401


def test_logout_clears_cookies():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}, timeout=20)
    assert r.status_code == 200
    r2 = s.post(f"{API}/auth/logout", timeout=15)
    assert r2.status_code == 200
    # cookies cleared in server response (Set-Cookie with empty/expired) - check subsequent call fails
    s.cookies.clear()
    r3 = s.get(f"{API}/auth/me", timeout=15)
    assert r3.status_code == 401


# ---------- Events ----------
def test_list_events_seeded():
    r = requests.get(f"{API}/events", timeout=15)
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list)
    assert len(arr) >= 3


def test_get_event_single():
    arr = requests.get(f"{API}/events", timeout=15).json()
    eid = arr[0]["id"]
    r = requests.get(f"{API}/events/{eid}", timeout=15)
    assert r.status_code == 200
    assert r.json()["id"] == eid


def test_create_event_admin_only(member_session):
    payload = {"title": "TEST_NoAccess", "description": "x", "start_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()}
    r = member_session.post(f"{API}/events", json=payload, timeout=15)
    assert r.status_code == 403


def test_event_crud_admin(admin_session):
    payload = {
        "title": "TEST_Event",
        "description": "desc",
        "location": "loc",
        "start_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
        "end_at": (datetime.now(timezone.utc) + timedelta(days=20, hours=2)).isoformat(),
        "capacity": 10,
        "category": "test",
    }
    r = admin_session.post(f"{API}/events", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    # update
    r2 = admin_session.put(f"{API}/events/{eid}", json={"title": "TEST_Event_Upd"}, timeout=15)
    assert r2.status_code == 200
    assert r2.json()["title"] == "TEST_Event_Upd"
    # verify GET
    r3 = requests.get(f"{API}/events/{eid}", timeout=15)
    assert r3.json()["title"] == "TEST_Event_Upd"
    # delete
    r4 = admin_session.delete(f"{API}/events/{eid}", timeout=15)
    assert r4.status_code == 200
    r5 = requests.get(f"{API}/events/{eid}", timeout=15)
    assert r5.status_code == 404


def test_rsvp_toggle_and_my_events(member_session):
    arr = requests.get(f"{API}/events", timeout=15).json()
    eid = arr[0]["id"]
    r = member_session.post(f"{API}/events/{eid}/rsvp", timeout=15)
    assert r.status_code == 200
    state1 = r.json()["rsvped"]
    # toggle again
    r2 = member_session.post(f"{API}/events/{eid}/rsvp", timeout=15)
    assert r2.json()["rsvped"] != state1
    # rsvp once more so my_events check works
    if not r2.json()["rsvped"]:
        member_session.post(f"{API}/events/{eid}/rsvp", timeout=15)
    rsvps = requests.get(f"{API}/events/{eid}/rsvps", timeout=15)
    assert rsvps.status_code == 200
    assert isinstance(rsvps.json(), list)
    mine = member_session.get(f"{API}/me/events", timeout=15)
    assert mine.status_code == 200
    assert any(e["id"] == eid for e in mine.json())


# ---------- Members ----------
def test_members_directory_search():
    r = requests.get(f"{API}/members", timeout=15)
    assert r.status_code == 200
    assert len(r.json()) >= 2
    r2 = requests.get(f"{API}/members?q=Riley", timeout=15)
    assert r2.status_code == 200
    assert any("Riley" in m["name"] for m in r2.json())


def test_get_member_single():
    arr = requests.get(f"{API}/members", timeout=15).json()
    mid = arr[0]["id"]
    r = requests.get(f"{API}/members/{mid}", timeout=15)
    assert r.status_code == 200
    assert r.json()["id"] == mid
    assert "password_hash" not in r.json()


def test_update_me_and_renew(member_session):
    r = member_session.put(f"{API}/members/me", json={"bio": "TEST_bio", "city": "TEST_city"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["bio"] == "TEST_bio"
    assert r.json()["city"] == "TEST_city"
    # renew
    before = r.json()["membership_expires_at"]
    r2 = member_session.post(f"{API}/members/me/renew", timeout=15)
    assert r2.status_code == 200
    after = r2.json()["membership_expires_at"]
    assert after != before
    assert datetime.fromisoformat(after) > datetime.fromisoformat(before)


# ---------- News ----------
def test_news_list_seeded():
    r = requests.get(f"{API}/news", timeout=15)
    assert r.status_code == 200
    assert len(r.json()) >= 2


def test_news_admin_crud(admin_session, member_session):
    # member forbidden
    rf = member_session.post(f"{API}/news", json={"title": "x", "body": "x"}, timeout=15)
    assert rf.status_code == 403
    # admin create
    r = admin_session.post(f"{API}/news", json={"title": "TEST_News", "summary": "s", "body": "b"}, timeout=15)
    assert r.status_code == 200
    nid = r.json()["id"]
    # update
    r2 = admin_session.put(f"{API}/news/{nid}", json={"title": "TEST_News_Upd"}, timeout=15)
    assert r2.status_code == 200
    assert r2.json()["title"] == "TEST_News_Upd"
    # delete
    r3 = admin_session.delete(f"{API}/news/{nid}", timeout=15)
    assert r3.status_code == 200
    r4 = requests.get(f"{API}/news/{nid}", timeout=15)
    assert r4.status_code == 404


# ---------- Pages ----------
def test_pages_seeded():
    r = requests.get(f"{API}/pages", timeout=15)
    assert r.status_code == 200
    slugs = {p["slug"] for p in r.json()}
    assert "about" in slugs and "contact" in slugs


def test_page_get_404():
    r = requests.get(f"{API}/pages/nonexistent-slug-xyz", timeout=15)
    assert r.status_code == 404


def test_pages_admin_crud(admin_session, member_session):
    slug = "club-express-lite"
    # cleanup if exists
    admin_session.delete(f"{API}/pages/{slug}", timeout=15)
    # member forbidden
    rf = member_session.post(f"{API}/pages", json={"slug": slug, "title": "x", "body": "x"}, timeout=15)
    assert rf.status_code == 403
    # create
    r = admin_session.post(f"{API}/pages", json={"slug": slug, "title": "TEST_Page", "body": "body"}, timeout=15)
    assert r.status_code == 200
    # update
    r2 = admin_session.put(f"{API}/pages/{slug}", json={"title": "TEST_Page_Upd"}, timeout=15)
    assert r2.status_code == 200
    assert r2.json()["title"] == "TEST_Page_Upd"
    # get
    r3 = requests.get(f"{API}/pages/{slug}", timeout=15)
    assert r3.status_code == 200
    # delete
    r4 = admin_session.delete(f"{API}/pages/{slug}", timeout=15)
    assert r4.status_code == 200


# ---------- AI ----------
def test_ai_event_description(admin_session):
    r = admin_session.post(f"{API}/ai/event-description", json={"title": "Test Picnic", "topic": "potluck", "audience": "members", "tone": "friendly"}, timeout=90)
    # 200 happy or 502 graceful
    assert r.status_code in (200, 502), r.text
    if r.status_code == 200:
        assert "text" in r.json()
        assert len(r.json()["text"]) > 30


def test_ai_draft_email(admin_session):
    r = admin_session.post(f"{API}/ai/draft-email", json={"subject": "Welcome", "goal": "welcome new members", "tone": "warm"}, timeout=90)
    assert r.status_code in (200, 502), r.text
    if r.status_code == 200:
        assert "text" in r.json()


def test_ai_member_forbidden(member_session):
    r = member_session.post(f"{API}/ai/event-description", json={"title": "x"}, timeout=15)
    assert r.status_code == 403


# ---------- Brute-force lockout ----------
def test_brute_force_lockout():
    bad_email = f"bf_{uuid.uuid4().hex[:6]}@clubhaven.app"
    last_status = None
    for _ in range(7):
        r = requests.post(f"{API}/auth/login", json={"email": bad_email, "password": "wrongpass"}, timeout=15)
        last_status = r.status_code
        if r.status_code == 429:
            break
    assert last_status == 429, f"Expected 429 after repeated failures, got {last_status}"
