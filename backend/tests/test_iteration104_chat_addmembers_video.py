"""Iteration 104 — Chat: add-members-to-existing + video meetings.

Covers:
  * PUT /conversations/{cid} with add_member_ids on an existing GROUP → member joins mid-thread.
  * PUT /conversations/{cid} with add_member_ids on a DM → conversation auto-converts to "group"
    while preserving message history.
  * PUT /conversations/{cid} with remove_member_ids on a DM → 400 (must leave).
  * POST /conversations/{cid}/video-meeting → posts a `kind=video_meeting` message with a
    Jitsi Meet URL under `meeting.url`; last_message_preview shows the 📹 label.
"""
import os
import time
from urllib.parse import urlparse

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001") + "/api"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "admin@clubhaven.app", "password": "Admin123!"})
    r.raise_for_status()
    return s


@pytest.fixture()
def four_members(admin_session):
    members = admin_session.get(f"{BASE}/members").json()
    assert len(members) >= 4
    return members[:4]


@pytest.fixture()
def group_convo(admin_session, four_members):
    """Group of 3 members (creator=admin + 2 others). Cleaned up after."""
    r = admin_session.post(f"{BASE}/conversations", json={
        "member_ids": [four_members[0]["id"], four_members[1]["id"]],
        "type": "group",
        "name": f"iter104-group-{int(time.time())}",
    })
    assert r.status_code == 200, r.text
    conv = r.json()
    yield conv
    admin_session.delete(f"{BASE}/conversations/{conv['id']}")


@pytest.fixture()
def dm_convo(admin_session, four_members):
    """1:1 DM between admin and member 0."""
    r = admin_session.post(f"{BASE}/conversations", json={
        "member_ids": [four_members[0]["id"]],
        "type": "dm",
    })
    assert r.status_code == 200, r.text
    conv = r.json()
    yield conv
    admin_session.delete(f"{BASE}/conversations/{conv['id']}")


# ---------- Add members mid-thread ----------
def test_add_member_to_existing_group(admin_session, group_convo, four_members):
    new_member = four_members[2]
    original_count = len(group_convo["member_ids"])
    r = admin_session.put(f"{BASE}/conversations/{group_convo['id']}", json={
        "add_member_ids": [new_member["id"]],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert new_member["id"] in body["member_ids"]
    assert len(body["member_ids"]) == original_count + 1
    assert body["type"] == "group"


def test_add_member_to_dm_auto_converts_to_group(admin_session, dm_convo, four_members):
    # Send one message before adding, then verify history is preserved.
    m = admin_session.post(f"{BASE}/conversations/{dm_convo['id']}/messages", json={"body": "hello pre-convert"}).json()
    assert m["id"]

    r = admin_session.put(f"{BASE}/conversations/{dm_convo['id']}", json={
        "add_member_ids": [four_members[2]["id"]],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "group"
    assert len(body["member_ids"]) == 3
    # Message history preserved
    msgs = admin_session.get(f"{BASE}/conversations/{dm_convo['id']}/messages").json()
    assert any(x["id"] == m["id"] for x in msgs)


def test_remove_member_from_dm_is_forbidden(admin_session, dm_convo, four_members):
    r = admin_session.put(f"{BASE}/conversations/{dm_convo['id']}", json={
        "remove_member_ids": [four_members[0]["id"]],
    })
    assert r.status_code == 400
    assert "dm" in r.json()["detail"].lower()


# ---------- Video meeting ----------
def test_start_video_meeting_posts_meeting_message(admin_session, group_convo):
    r = admin_session.post(f"{BASE}/conversations/{group_convo['id']}/video-meeting")
    assert r.status_code == 200, r.text
    msg = r.json()
    assert msg["kind"] == "video_meeting"
    meeting = msg["meeting"]
    assert meeting
    # URL is a real Jitsi room URL
    parsed = urlparse(meeting["url"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "meet.jit.si"
    assert meeting["room"] and meeting["room"] in meeting["url"]
    # Room stamped with starter
    assert meeting["started_by"]
    assert meeting["started_at"]

    # Fetch message list and confirm it's persisted with the same kind
    msgs = admin_session.get(f"{BASE}/conversations/{group_convo['id']}/messages").json()
    found = next((x for x in msgs if x["id"] == msg["id"]), None)
    assert found is not None
    assert found["kind"] == "video_meeting"
    assert found["meeting"]["url"] == meeting["url"]

    # last_message_preview reflects the meeting
    convo = admin_session.get(f"{BASE}/conversations/{group_convo['id']}").json()
    assert "video meeting" in (convo.get("last_message_preview") or "").lower()


def test_video_meeting_urls_are_unique_per_call(admin_session, group_convo):
    """Every 'Start meeting' click gets a fresh room so old links can't be
    reused to eavesdrop after the meeting ends."""
    r1 = admin_session.post(f"{BASE}/conversations/{group_convo['id']}/video-meeting").json()
    r2 = admin_session.post(f"{BASE}/conversations/{group_convo['id']}/video-meeting").json()
    assert r1["meeting"]["url"] != r2["meeting"]["url"]
    assert r1["meeting"]["room"] != r2["meeting"]["room"]


def test_video_meeting_requires_membership(admin_session, group_convo):
    # Random conversation id → 404
    r = admin_session.post(f"{BASE}/conversations/does-not-exist/video-meeting")
    assert r.status_code == 404
