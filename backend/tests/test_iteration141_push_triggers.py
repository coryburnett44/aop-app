"""Iter 141 — extend OneSignal push to every user-facing trigger.

Verifies each trigger stamps a `push_notifications` row via the shared
`send_push_best_effort` helper. We don't assert on external OneSignal
delivery (their sandbox isn't reliable enough for CI); instead we check
that:
  • the helper is invoked
  • the row has the right `kind`
  • the target audience is the expected user
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import requests

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


def _wait_for_push(admin: requests.Session, *, kind: str, user_id: str | None = None, max_seconds: int = 15) -> dict | None:
    """Poll /admin/push/history for a matching row."""
    for _ in range(max_seconds * 2):
        time.sleep(0.5)
        rows = admin.get(f"{BASE}/admin/push/history", timeout=10).json()
        for r in rows:
            if r.get("kind") == kind:
                if user_id is None or user_id in (r.get("user_ids") or []):
                    return r
    return None


def test_award_grant_pushes_notification_to_recipient():
    admin = _login("admin@clubhaven.app", "Admin123!")
    # Find any award + any active non-admin member.
    awards = admin.get(f"{BASE}/awards", timeout=10).json()
    assert awards, "no awards available for test"
    award_id = awards[0]["id"]
    users = admin.get(f"{BASE}/members", timeout=15).json()
    assert users, "no members available for test"
    # Prefer a non-admin so we exercise a real recipient path.
    target = next((u for u in users if u.get("role") != "admin"), users[0])
    grant = admin.post(f"{BASE}/awards/{award_id}/grant", json={
        "user_id": target["id"],
        "reason": f"iter141 test {uuid.uuid4().hex[:6]}",
    }, timeout=15)
    assert grant.status_code == 200, grant.text
    grant_id = grant.json()["id"]
    try:
        row = _wait_for_push(admin, kind="award_granted", user_id=target["id"])
        assert row is not None, "expected a push_notifications row with kind=award_granted"
        assert row["title"].startswith("🏆")
        assert target["id"] in row.get("user_ids", [])
    finally:
        admin.delete(f"{BASE}/awards/grants/{grant_id}", timeout=10)


def test_hours_approval_pushes_notification_to_submitter():
    admin = _login("admin@clubhaven.app", "Admin123!")
    # Create a pending hours entry as the admin (self-log becomes pending
    # only if we skip auto-approve; easier path: log for the admin themselves
    # via POST /hours, then flip to approved via the review endpoint).
    from datetime import datetime, timezone
    payload = {
        "date": datetime.now(timezone.utc).isoformat(),
        "hours": 1.5,
        "activity": f"iter141 test {uuid.uuid4().hex[:6]}",
        "description": "regression",
        "event_type": "aop_related",
        "agency_name": "AOP Regression Suite",
        "host_name": "Regression Bot",
        "host_email": "bot@example.com",
        "host_phone": "555-000-0000",
    }
    r = admin.post(f"{BASE}/hours", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    entry = r.json()
    hid = entry["id"]
    try:
        # Force to pending in case admin auto-approves — then flip to approved.
        admin.put(f"{BASE}/hours/{hid}", json={"status": "pending"}, timeout=10)
        review = admin.put(f"{BASE}/hours/{hid}/review", json={"status": "approved"}, timeout=15)
        assert review.status_code == 200, review.text
        row = _wait_for_push(admin, kind="hours_approved")
        assert row is not None, "expected a push_notifications row with kind=hours_approved"
        assert "approved" in row["title"].lower()
    finally:
        admin.delete(f"{BASE}/hours/{hid}", timeout=10)


def test_chat_message_pushes_to_other_members():
    admin = _login("admin@clubhaven.app", "Admin123!")
    users = admin.get(f"{BASE}/members", timeout=15).json()
    me = admin.get(f"{BASE}/members/me", timeout=10).json()
    other = next((u for u in users if u.get("id") and u["id"] != me.get("id")), None)
    if other is None:
        import pytest
        pytest.skip("need at least 2 members in the roster to test chat push")
    conv = admin.post(f"{BASE}/conversations", json={
        "type": "dm", "member_ids": [other["id"]],
    }, timeout=15)
    assert conv.status_code in (200, 201), conv.text
    cid = conv.json()["id"]
    msg = admin.post(f"{BASE}/conversations/{cid}/messages", json={
        "body": f"iter141 test msg {uuid.uuid4().hex[:6]}",
    }, timeout=15)
    assert msg.status_code == 200, msg.text
    row = _wait_for_push(admin, kind="chat_message", user_id=other["id"])
    assert row is not None, "expected a push_notifications row with kind=chat_message"
    assert row["title"].startswith("💬")


def test_video_meeting_start_pushes_to_participants():
    admin = _login("admin@clubhaven.app", "Admin123!")
    users = admin.get(f"{BASE}/members", timeout=15).json()
    me = admin.get(f"{BASE}/members/me", timeout=10).json()
    other = next((u for u in users if u.get("id") and u["id"] != me.get("id")), None)
    if other is None:
        import pytest
        pytest.skip("need at least 2 members in the roster to test meeting push")
    conv = admin.post(f"{BASE}/conversations", json={
        "type": "dm", "member_ids": [other["id"]],
    }, timeout=15)
    cid = conv.json()["id"]
    r = admin.post(f"{BASE}/conversations/{cid}/video-meeting", timeout=20)
    assert r.status_code == 200, r.text
    row = _wait_for_push(admin, kind="meeting_started", user_id=other["id"])
    assert row is not None, "expected a push_notifications row with kind=meeting_started"
    assert "meeting" in row["title"].lower()


def test_news_article_still_fires_news_push():
    """Iter 140 covered this — re-assert nothing regressed."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    payload = {
        "title": f"Iter141 push regression {uuid.uuid4().hex[:6]}",
        "summary": "small summary",
        "body": "body",
        "body_html": "<p>body</p>",
    }
    r = admin.post(f"{BASE}/news", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    try:
        row = _wait_for_push(admin, kind="news_article")
        assert row is not None, "expected a push_notifications row with kind=news_article"
    finally:
        admin.delete(f"{BASE}/news/{nid}", timeout=10)
