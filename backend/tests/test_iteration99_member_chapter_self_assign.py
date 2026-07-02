"""Iteration 99 — Members can self-assign their chapter via /members/me.

User bug report: "The 'Chapter' field in the admin member tab and the
'Chapter' field in the member profile should match. When the member
selects their Chapter, it goes blank when they leave the profile page.
However, the admin member 'Chapter' field may have a chapter selected."

Root cause: `PUT /members/me` (ProfileUpdateIn) had no `chapter_id`
field, so the frontend routed chapter changes to
`PUT /members/{user_id}/chapter` — which is guarded by
`admin_tab_dep("members")` and 403s for regular members. The change
never persisted and the on-screen field went blank on the next load,
while the admin's view of that member kept whatever chapter had been
set by admin previously (hence the divergence).

Fix: add `chapter_id` to `ProfileUpdateIn`, validate it exists (or is
empty to clear), and let it flow through the same `$set` update as the
rest of the profile fields.
"""
import os

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def _login(email, pwd):
    return requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}).json()["access_token"]


@pytest.fixture(scope="module")
def member_token():
    return _login("member@clubhaven.app", "Member123!")


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@clubhaven.app", "Admin123!")


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def a_chapter(admin_token):
    """Grab any real chapter to attach to the member."""
    r = requests.get(f"{BASE}/chapters", headers=_h(admin_token))
    r.raise_for_status()
    ch = r.json()
    assert ch, "seed chapters missing"
    return ch[0]


def test_member_can_self_assign_chapter_and_admin_sees_same_value(member_token, admin_token, a_chapter):
    r = requests.put(
        f"{BASE}/members/me",
        headers=_h(member_token),
        json={"chapter_id": a_chapter["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["chapter_id"] == a_chapter["id"]

    # /auth/me after save must reflect the new chapter — this is the flow the
    # UI uses when navigating away from Profile and back.
    fresh = requests.get(f"{BASE}/auth/me", headers=_h(member_token)).json()
    assert fresh["chapter_id"] == a_chapter["id"]

    # Admin's members listing must show the same chapter.
    me = requests.get(f"{BASE}/auth/me", headers=_h(member_token)).json()
    listing = requests.get(f"{BASE}/members", headers=_h(admin_token)).json()
    row = next((x for x in listing if x["id"] == me["id"]), None)
    assert row is not None
    assert row["chapter_id"] == a_chapter["id"]


def test_member_can_clear_chapter_via_empty_string(member_token):
    # Ensure it's set first.
    r = requests.put(f"{BASE}/members/me", headers=_h(member_token), json={"chapter_id": ""})
    assert r.status_code == 200
    assert r.json().get("chapter_id") in ("", None)


def test_unknown_chapter_id_is_rejected(member_token, admin_token, a_chapter):
    r = requests.put(
        f"{BASE}/members/me",
        headers=_h(member_token),
        json={"chapter_id": "definitely-not-a-real-chapter-id"},
    )
    assert r.status_code == 400
    assert "Unknown chapter" in r.json()["detail"]
    # Restore for downstream tests.
    requests.put(f"{BASE}/members/me", headers=_h(member_token), json={"chapter_id": a_chapter["id"]})


def test_admin_only_chapter_endpoint_still_rejects_members(member_token):
    """The admin-side /members/{user_id}/chapter endpoint should keep its
    403 gate for non-admins — we've added the self-serve path but not
    weakened the admin path."""
    me = requests.get(f"{BASE}/auth/me", headers=_h(member_token)).json()
    r = requests.put(
        f"{BASE}/members/{me['id']}/chapter",
        headers=_h(member_token),
        json={"chapter_id": None},
    )
    assert r.status_code == 403
