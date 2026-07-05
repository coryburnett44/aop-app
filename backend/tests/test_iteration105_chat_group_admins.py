"""Iteration 105 — Chat: group admin roles + creator-only policy toggle.

Every group chat now has an implicit creator + an explicit `admin_ids` list.
This suite exercises the full permission matrix via three real sessions
(site-admin, member-A = creator, member-B = participant):

  * Creator promotes/demotes members to group-admin.
  * Creator + group-admins can add/remove members; regular members cannot
    (unless the creator flips `member_add_policy` to "anyone").
  * The creator cannot be demoted or removed.
  * Removing a group-admin automatically drops them from `admin_ids`.
  * A group-admin who leaves the chat is auto-dropped from `admin_ids`.
"""
import os
import time

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001") + "/api"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@clubhaven.app", "Admin123!")


@pytest.fixture(scope="module")
def creator():
    """`maya.patel@clubhaven.app` (regular member) — will create groups."""
    return _login("maya.patel@clubhaven.app", "Demo123!")


@pytest.fixture(scope="module")
def other():
    """`jordan.reed@clubhaven.app` — a regular member participant."""
    return _login("jordan.reed@clubhaven.app", "Demo123!")


@pytest.fixture(scope="module")
def user_ids(admin):
    ms = admin.get(f"{BASE}/members").json()
    by_email = {m["email"]: m["id"] for m in ms}
    return {
        "creator": by_email["maya.patel@clubhaven.app"],
        "other": by_email["jordan.reed@clubhaven.app"],
        "third": by_email["harper.liu@clubhaven.app"],
        "fourth": by_email["member@clubhaven.app"],
    }


@pytest.fixture(scope="module", autouse=True)
def _activate_demo_members(admin, user_ids):
    """The demo/seed members can drift to `status="inactive"` across resets;
    reactivate them so their login sessions can hit chat endpoints."""
    for uid in user_ids.values():
        admin.put(f"{BASE}/members/{uid}", json={"member_status": "active"})
    yield


@pytest.fixture()
def group_convo(creator, user_ids):
    """Fresh 3-person group owned by `creator`. Cleaned up afterward."""
    r = creator.post(f"{BASE}/conversations", json={
        "member_ids": [user_ids["other"], user_ids["third"]],
        "type": "group",
        "name": f"iter105-{int(time.time())}",
    })
    assert r.status_code == 200, r.text
    conv = r.json()
    assert conv["created_by"] == user_ids["creator"]
    assert conv["admin_ids"] == []
    assert conv["member_add_policy"] == "admins_only"
    yield conv
    creator.delete(f"{BASE}/conversations/{conv['id']}")


# ---------- Promotion ----------
def test_creator_can_promote_and_demote_member(creator, group_convo, user_ids):
    r = creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"promote_ids": [user_ids["other"]]})
    assert r.status_code == 200
    assert user_ids["other"] in r.json()["admin_ids"]

    r = creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"demote_ids": [user_ids["other"]]})
    assert r.status_code == 200
    assert user_ids["other"] not in r.json()["admin_ids"]


def test_group_admin_cannot_promote_others(creator, other, group_convo, user_ids):
    creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"promote_ids": [user_ids["other"]]})
    r = other.put(f"{BASE}/conversations/{group_convo['id']}", json={"promote_ids": [user_ids["third"]]})
    assert r.status_code == 403
    assert "creator" in r.json()["detail"].lower()


def test_creator_cannot_be_demoted(creator, group_convo, user_ids):
    r = creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"demote_ids": [user_ids["creator"]]})
    assert r.status_code == 400


def test_cannot_promote_non_member(creator, group_convo, user_ids):
    r = creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"promote_ids": [user_ids["fourth"]]})
    assert r.status_code == 400


# ---------- Member changes ----------
def test_regular_member_cannot_add_by_default(creator, other, group_convo, user_ids):
    """Default policy is admins_only — a regular participant is 403."""
    r = other.put(f"{BASE}/conversations/{group_convo['id']}", json={"add_member_ids": [user_ids["fourth"]]})
    assert r.status_code == 403
    assert "admin" in r.json()["detail"].lower()


def test_regular_member_can_add_when_policy_is_anyone(creator, other, group_convo, user_ids):
    # Creator flips the toggle
    r = creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"member_add_policy": "anyone"})
    assert r.status_code == 200 and r.json()["member_add_policy"] == "anyone"
    # Now the participant can add
    r = other.put(f"{BASE}/conversations/{group_convo['id']}", json={"add_member_ids": [user_ids["fourth"]]})
    assert r.status_code == 200
    assert user_ids["fourth"] in r.json()["member_ids"]


def test_group_admin_can_remove_a_regular_member(creator, other, group_convo, user_ids):
    # Promote `other` first
    creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"promote_ids": [user_ids["other"]]})
    # `other` (now group-admin) removes `third`
    r = other.put(f"{BASE}/conversations/{group_convo['id']}", json={"remove_member_ids": [user_ids["third"]]})
    assert r.status_code == 200
    assert user_ids["third"] not in r.json()["member_ids"]


def test_regular_member_cannot_remove(creator, other, group_convo, user_ids):
    r = other.put(f"{BASE}/conversations/{group_convo['id']}", json={"remove_member_ids": [user_ids["third"]]})
    assert r.status_code == 403


def test_creator_cannot_be_removed(creator, group_convo, user_ids):
    r = creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"remove_member_ids": [user_ids["creator"]]})
    assert r.status_code == 400


def test_removing_group_admin_also_strips_admin_role(creator, group_convo, user_ids):
    creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"promote_ids": [user_ids["other"]]})
    r = creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"remove_member_ids": [user_ids["other"]]})
    assert r.status_code == 200
    body = r.json()
    assert user_ids["other"] not in body["member_ids"]
    assert user_ids["other"] not in body["admin_ids"]


def test_group_admin_who_leaves_is_dropped_from_admin_ids(creator, other, group_convo, user_ids):
    creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"promote_ids": [user_ids["other"]]})
    r = other.post(f"{BASE}/conversations/{group_convo['id']}/leave")
    assert r.status_code == 200
    # Creator refetches
    conv = creator.get(f"{BASE}/conversations/{group_convo['id']}").json()
    assert user_ids["other"] not in conv["member_ids"]
    assert user_ids["other"] not in conv["admin_ids"]


# ---------- Policy toggle guard rails ----------
def test_only_creator_can_flip_policy(other, group_convo):
    r = other.put(f"{BASE}/conversations/{group_convo['id']}", json={"member_add_policy": "anyone"})
    assert r.status_code == 403


def test_site_admin_gets_creator_level_powers_in_any_group(creator, admin, group_convo, user_ids):
    """Org-level admin gains creator-level powers on any chat they're
    added to — matches the existing delete-conversation rule (must be a
    member first, then site-admin can moderate)."""
    # Get admin's own user id and add them to the group
    admin_id = admin.get(f"{BASE}/auth/me").json()["id"]
    creator.put(f"{BASE}/conversations/{group_convo['id']}", json={"add_member_ids": [admin_id]})
    # Now the site-admin can promote non-creator members
    r = admin.put(f"{BASE}/conversations/{group_convo['id']}", json={"promote_ids": [user_ids["third"]]})
    assert r.status_code == 200, r.text
    assert user_ids["third"] in r.json()["admin_ids"]
