"""Iteration 96 — Sign-in activity tracking + pending-password-setup auto-clear.

Two related deliverables:
  1. New `/api/admin/login-activity` (admin-only) lists recent sessions
     captured by `/auth/login`, `/auth/logout`, and `/activity/page-view`.
  2. A successful `/auth/login` now clears the `pending_set_password` flag
     so the "Pending Password Setup" pill disappears once the member has
     proven they can sign in.
"""
import os
import time

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def _login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@clubhaven.app", "Admin123!")["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_login_records_session_and_logout_stamps_duration():
    # Fresh login.
    t_before = time.time() - 1  # seconds since epoch, with a small slack
    body = _login("member@clubhaven.app", "Member123!")
    tok = body["access_token"]
    # Record a couple of page-views to drive last_seen forward.
    for p in ["/events", "/photos"]:
        r = requests.post(f"{BASE}/activity/page-view", headers=_h(tok), json={"path": p})
        assert r.status_code == 200, r.text
        time.sleep(0.05)
    # Logout closes the session.
    r = requests.post(f"{BASE}/auth/logout", headers=_h(tok))
    assert r.status_code == 200

    # Admin pulls the activity feed — most-recent first — and finds OUR session
    # (any older open sessions from prior test runs will sort lower because
    # they have an earlier login_at).
    admin_t = _login("admin@clubhaven.app", "Admin123!")["access_token"]
    r = requests.get(f"{BASE}/admin/login-activity?limit=50", headers=_h(admin_t))
    assert r.status_code == 200
    rows = r.json()
    # The most recent member session is the one we just created.
    member_rows = [row for row in rows if row["user_email"] == "member@clubhaven.app"]
    assert member_rows, "member session must be present in activity feed"
    ours = member_rows[0]  # already sorted by login_at desc by the endpoint
    from datetime import datetime
    login_at = datetime.fromisoformat(ours["login_at"].replace("Z", "+00:00")).timestamp()
    assert login_at >= t_before, "first row must be the session we just created"
    assert ours["logout_at"], "logout should have stamped logout_at on OUR session"
    assert ours["duration_seconds"] is not None
    assert ours["duration_seconds"] >= 0
    assert ours["pages_count"] >= 2


def test_admin_can_pull_session_detail_with_full_page_list(admin_token):
    rows = requests.get(f"{BASE}/admin/login-activity?limit=20", headers=_h(admin_token)).json()
    candidate = next((r for r in rows if r.get("pages_count", 0) > 0), None)
    assert candidate, "need at least one session with pages_visited (run the other test first)"
    detail = requests.get(f"{BASE}/admin/login-activity/{candidate['id']}", headers=_h(admin_token)).json()
    pages = detail.get("pages_visited") or []
    assert len(pages) > 0
    for p in pages:
        assert "path" in p and "at" in p


def test_non_admin_cannot_pull_activity():
    member_tok = _login("member@clubhaven.app", "Member123!")["access_token"]
    r = requests.get(f"{BASE}/admin/login-activity", headers=_h(member_tok))
    assert r.status_code == 403


def test_page_view_requires_auth():
    r = requests.post(f"{BASE}/activity/page-view", json={"path": "/events"})
    assert r.status_code == 401


def test_successful_login_clears_pending_set_password_flag():
    """If a member has `pending_set_password=true` and then logs in
    successfully (i.e. they DO have a working password), the pill should
    go away. We simulate this by flagging the member directly via Mongo,
    then logging in and verifying the flag is gone."""
    from pymongo import MongoClient
    db_name = os.environ.get("DB_NAME", "clubhaven_db")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db = MongoClient(mongo_url)[db_name]

    # Set the flag.
    db.users.update_one(
        {"email": "member@clubhaven.app"},
        {"$set": {"pending_set_password": True}},
    )
    assert db.users.find_one({"email": "member@clubhaven.app"}).get("pending_set_password") is True

    # Login.
    _login("member@clubhaven.app", "Member123!")

    # Flag should now be cleared.
    after = db.users.find_one({"email": "member@clubhaven.app"})
    assert not after.get("pending_set_password"), "pending_set_password should be unset after a successful login"
