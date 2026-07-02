"""Iteration 100 — Governor Managers cannot change their own chapter.

User request: "Ensure that members coded as a Governor Manager (Admin)
cannot change their chapter in their profile."

Governor Managers are chapter-scoped admins — their admin authority is
tied to their assigned chapter. Iter99 opened up member self-service on
`chapter_id` via `/members/me`, but that path must NOT extend to
governors or they could silently migrate their scope without oversight.
Only a full-access admin can reassign a governor.
"""
import os

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
DB = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "clubhaven_db")]


def _login(email, pwd):
    return requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}).json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@clubhaven.app", "Admin123!")


@pytest.fixture
def promote_member_to_governor():
    """Promote member@clubhaven.app to admin_role=governor_manager for the
    duration of a single test. Restores plain-member role afterwards so
    other test modules aren't affected."""
    DB.users.update_one(
        {"email": "member@clubhaven.app"},
        {"$set": {"role": "admin", "admin_role": "governor_manager"}},
    )
    yield
    DB.users.update_one(
        {"email": "member@clubhaven.app"},
        {"$set": {"role": "member", "admin_role": None}},
    )


def _get_other_chapter_than(current_chapter_id, token):
    chapters = requests.get(f"{BASE}/chapters", headers=_h(token)).json()
    for c in chapters:
        if c["id"] != current_chapter_id:
            return c["id"]
    pytest.skip("Need at least 2 chapters in the DB")


def test_governor_cannot_change_own_chapter_via_profile(promote_member_to_governor):
    gov_tok = _login("member@clubhaven.app", "Member123!")
    me = requests.get(f"{BASE}/auth/me", headers=_h(gov_tok)).json()
    current = me.get("chapter_id")
    other = _get_other_chapter_than(current, gov_tok)

    r = requests.put(
        f"{BASE}/members/me",
        headers=_h(gov_tok),
        json={"chapter_id": other},
    )
    assert r.status_code == 403
    assert "Governor Manager" in r.json()["detail"]

    # The DB value must not have changed.
    fresh = requests.get(f"{BASE}/auth/me", headers=_h(gov_tok)).json()
    assert fresh["chapter_id"] == current


def test_governor_can_still_edit_other_profile_fields(promote_member_to_governor):
    """A governor updating bio (with chapter_id echoed as the SAME value)
    should succeed — the block is specifically on chapter CHANGES, not on
    saving the profile at all."""
    gov_tok = _login("member@clubhaven.app", "Member123!")
    me = requests.get(f"{BASE}/auth/me", headers=_h(gov_tok)).json()
    r = requests.put(
        f"{BASE}/members/me",
        headers=_h(gov_tok),
        json={"bio": "Governor bio update test", "chapter_id": me["chapter_id"]},
    )
    assert r.status_code == 200
    assert r.json().get("bio") == "Governor bio update test"


def test_full_admin_can_still_reassign_governor(admin_token, promote_member_to_governor):
    """A full-access admin must retain the ability to move a governor to a
    different chapter via the admin path."""
    gov_tok = _login("member@clubhaven.app", "Member123!")
    me = requests.get(f"{BASE}/auth/me", headers=_h(gov_tok)).json()
    current = me["chapter_id"]
    other = _get_other_chapter_than(current, admin_token)

    r = requests.put(
        f"{BASE}/members/{me['id']}/chapter",
        headers=_h(admin_token),
        json={"chapter_id": other},
    )
    assert r.status_code == 200
    fresh = requests.get(f"{BASE}/auth/me", headers=_h(gov_tok)).json()
    assert fresh["chapter_id"] == other
    # Restore.
    requests.put(f"{BASE}/members/{me['id']}/chapter", headers=_h(admin_token), json={"chapter_id": current})


def test_regular_member_still_can_change_chapter(admin_token):
    """Iter99 self-service must still work for plain members — this
    guardrail is scoped exclusively to governor_manager admins."""
    mem_tok = _login("member@clubhaven.app", "Member123!")
    me = requests.get(f"{BASE}/auth/me", headers=_h(mem_tok)).json()
    # Only run if member@ is currently a plain member (not accidentally
    # promoted by another test).
    if me.get("role") == "admin":
        pytest.skip("member@ is currently an admin — test is not applicable")
    current = me.get("chapter_id")
    other = _get_other_chapter_than(current, mem_tok)
    r = requests.put(f"{BASE}/members/me", headers=_h(mem_tok), json={"chapter_id": other})
    assert r.status_code == 200
    assert r.json()["chapter_id"] == other
    # Restore.
    requests.put(f"{BASE}/members/me", headers=_h(mem_tok), json={"chapter_id": current})
