"""Iteration 107 — Video meeting live participant indicator.

Covers:
  * POST /meetings/{mid}/heartbeat records a participant + refreshes last_seen_at.
  * GET  /meetings/{mid}/participants returns {active, count, is_over}.
  * `is_over` flips to true once every participant has left (or their heartbeat
    goes stale beyond the 30s window).
  * Membership gating: outsiders get 404 on both endpoints.
"""
import os
import time
from datetime import datetime, timedelta, timezone

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
def user_ids(admin):
    ms = admin.get(f"{BASE}/members").json()
    by_email = {m["email"]: m["id"] for m in ms}
    return {
        "creator": by_email["maya.patel@clubhaven.app"],
        "other": by_email["jordan.reed@clubhaven.app"],
        "outsider": by_email["harper.liu@clubhaven.app"],
    }


@pytest.fixture(scope="module", autouse=True)
def _activate(admin, user_ids):
    for uid in user_ids.values():
        admin.put(f"{BASE}/members/{uid}", json={"member_status": "active"})


@pytest.fixture(scope="module")
def creator():
    return _login("maya.patel@clubhaven.app", "Demo123!")


@pytest.fixture(scope="module")
def other():
    return _login("jordan.reed@clubhaven.app", "Demo123!")


@pytest.fixture(scope="module")
def outsider():
    return _login("harper.liu@clubhaven.app", "Demo123!")


@pytest.fixture()
def meeting(creator, other, user_ids):
    # Creator + other in a DM; start a meeting.
    conv = creator.post(f"{BASE}/conversations", json={
        "member_ids": [user_ids["other"]],
        "type": "dm",
    }).json()
    m = creator.post(f"{BASE}/conversations/{conv['id']}/video-meeting").json()
    yield {"conv_id": conv["id"], "message_id": m["id"], "meeting": m["meeting"]}
    creator.delete(f"{BASE}/conversations/{conv['id']}")


# ---------- Basic flow ----------
def test_summary_before_anyone_joins(creator, meeting):
    r = creator.get(f"{BASE}/meetings/{meeting['message_id']}/participants")
    assert r.status_code == 200
    s = r.json()
    assert s["count"] == 0
    assert s["is_over"] is False  # nobody joined → not yet started, not over
    assert s["any_ever_joined"] is False


def test_heartbeat_marks_user_active(creator, meeting):
    r = creator.post(f"{BASE}/meetings/{meeting['message_id']}/heartbeat")
    assert r.status_code == 200
    s = r.json()
    assert s["count"] == 1
    assert s["any_ever_joined"] is True
    assert s["is_over"] is False
    p = s["active"][0]
    assert p["user_name"]  # populated from user session


def test_two_participants_visible(creator, other, meeting):
    creator.post(f"{BASE}/meetings/{meeting['message_id']}/heartbeat")
    other.post(f"{BASE}/meetings/{meeting['message_id']}/heartbeat")
    s = creator.get(f"{BASE}/meetings/{meeting['message_id']}/participants").json()
    assert s["count"] == 2
    ids = {p["user_id"] for p in s["active"]}
    assert len(ids) == 2


def test_leave_marks_meeting_over_when_last_participant_exits(creator, other, meeting):
    creator.post(f"{BASE}/meetings/{meeting['message_id']}/heartbeat")
    other.post(f"{BASE}/meetings/{meeting['message_id']}/heartbeat")
    # Both explicitly leave.
    creator.post(f"{BASE}/meetings/{meeting['message_id']}/heartbeat?left=true")
    other.post(f"{BASE}/meetings/{meeting['message_id']}/heartbeat?left=true")
    s = creator.get(f"{BASE}/meetings/{meeting['message_id']}/participants").json()
    assert s["count"] == 0
    assert s["any_ever_joined"] is True
    assert s["is_over"] is True


# ---------- Access control ----------
def test_outsider_cannot_view_or_heartbeat(outsider, meeting):
    r = outsider.get(f"{BASE}/meetings/{meeting['message_id']}/participants")
    assert r.status_code == 404
    r = outsider.post(f"{BASE}/meetings/{meeting['message_id']}/heartbeat")
    assert r.status_code == 404


def test_heartbeat_on_missing_meeting_returns_404(creator):
    r = creator.post(f"{BASE}/meetings/does-not-exist/heartbeat")
    assert r.status_code == 404
