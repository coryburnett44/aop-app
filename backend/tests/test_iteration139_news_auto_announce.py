"""Iter 139 — News auto-announcement emails.

When an admin creates a news article we send every active, opted-in member
an email with the title, summary, and a Read-more link. Passing `notify=false`
suppresses the email; edits never re-blast.
"""
from __future__ import annotations

import os
import sys
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


def _latest_blast(admin, kind: str = "news_announcement"):
    r = admin.get(f"{BASE}/email/blasts", timeout=10)
    assert r.status_code == 200
    items = r.json()
    return next((b for b in items if b.get("kind") == kind), None)


def test_creating_news_with_default_notify_logs_a_news_announcement_blast():
    admin = _login("admin@clubhaven.app", "Admin123!")
    tag = uuid.uuid4().hex[:6]
    payload = {
        "title": f"Iter139 auto-notify {tag}",
        "summary": "This is a small summary that should show in the email.",
        "body": "Long body text of the article.",
        "body_html": "<p>Long body <strong>text</strong>.</p>",
    }
    r = admin.post(f"{BASE}/news", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    try:
        # Background task needs a beat to run — poll for up to ~10s.
        import time
        blast = None
        for _ in range(20):
            time.sleep(0.5)
            blasts = admin.get(f"{BASE}/email/blasts", timeout=10).json()
            blast = next((b for b in blasts if b.get("kind") == "news_announcement" and b.get("news_id") == nid), None)
            if blast:
                break
        assert blast is not None, "Expected a news_announcement blast log entry"
        assert blast["subject"].startswith("[News] ")
        # `recipient_count` is stamped up-front so the log row appears in the
        # UI immediately; `sent_count` catches up as the background loop runs.
        assert blast.get("recipient_count", 0) >= 1 or blast.get("sent_count", 0) >= 1
    finally:
        admin.delete(f"{BASE}/news/{nid}", timeout=10)


def test_creating_news_with_notify_false_does_not_send_or_log_blast():
    admin = _login("admin@clubhaven.app", "Admin123!")
    tag = uuid.uuid4().hex[:6]
    payload = {"title": f"Silent {tag}", "summary": "", "body": "x", "body_html": "<p>x</p>"}
    r = admin.post(f"{BASE}/news?notify=false", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    try:
        import time
        time.sleep(1.5)  # Give any accidental background task a chance to fire.
        blasts = admin.get(f"{BASE}/email/blasts", timeout=10).json()
        match = next((b for b in blasts if b.get("kind") == "news_announcement" and b.get("news_id") == nid), None)
        assert match is None, "notify=false should NOT log a blast"
    finally:
        admin.delete(f"{BASE}/news/{nid}", timeout=10)


def test_updating_news_never_reblasts():
    admin = _login("admin@clubhaven.app", "Admin123!")
    tag = uuid.uuid4().hex[:6]
    created = admin.post(f"{BASE}/news?notify=false", json={
        "title": f"Base {tag}", "summary": "", "body": "hi", "body_html": "<p>hi</p>",
    }, timeout=15).json()
    nid = created["id"]
    try:
        r = admin.put(f"{BASE}/news/{nid}", json={"title": f"Updated {tag}", "body_html": "<p>updated</p>"}, timeout=15)
        assert r.status_code == 200
        import time
        time.sleep(1.5)
        blasts = admin.get(f"{BASE}/email/blasts", timeout=10).json()
        assert not any(b for b in blasts if b.get("kind") == "news_announcement" and b.get("news_id") == nid), \
            "PUT /news must never trigger a member-wide email blast"
    finally:
        admin.delete(f"{BASE}/news/{nid}", timeout=10)
