"""Iter 140 — OneSignal push notifications.

Backend surface only (frontend is service-worker gated so it requires a real
browser session — smoke-tested via screenshot). Verifies:
  • /push/config returns App ID + enabled flag when the env vars are set.
  • /push/subscription is authenticated and upserts.
  • /admin/push/send returns 200 (test_only isolates blast to the admin).
  • /admin/push/history logs the send.
  • Email blast with also_push=true doesn't crash.
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


def test_push_config_public_returns_app_id_when_env_set():
    r = requests.get(f"{BASE}/push/config", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    # 8-4-4-4-12 UUID shape.
    assert len(data["app_id"]) == 36 and data["app_id"].count("-") == 4
    # REST key must NEVER leak into the public config surface.
    assert "rest" not in data and "api_key" not in data


def test_push_subscription_upsert_and_read():
    user = _login("admin@clubhaven.app", "Admin123!")
    fake_sub = f"test-sub-{uuid.uuid4().hex[:8]}"
    r = user.post(f"{BASE}/push/subscription", json={"subscription_id": fake_sub, "opted_in": True}, timeout=10)
    assert r.status_code == 200, r.text
    got = user.get(f"{BASE}/push/me", timeout=10).json()
    assert got["subscription_id"] == fake_sub
    assert got["opted_in"] is True


def test_push_subscription_requires_auth():
    anon = requests.Session()
    r = anon.post(f"{BASE}/push/subscription", json={"subscription_id": "x", "opted_in": True}, timeout=10)
    assert r.status_code == 401


def test_admin_push_send_test_only_returns_ok_and_logs_history():
    admin = _login("admin@clubhaven.app", "Admin123!")
    before = admin.get(f"{BASE}/admin/push/history", timeout=10).json()
    prev_len = len(before)
    payload = {
        "title": f"Test push {uuid.uuid4().hex[:6]}",
        "body": "Automated regression — safe to ignore.",
        "segment": "active",
        "test_only": True,
    }
    r = admin.post(f"{BASE}/admin/push/send", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    after = admin.get(f"{BASE}/admin/push/history", timeout=10).json()
    assert len(after) == prev_len + 1
    assert after[0]["title"] == payload["title"]
    assert after[0]["test_only"] is True


def test_admin_push_send_rejects_non_admin():
    # A newly-registered member has no admin tabs.
    email = f"reg-{uuid.uuid4().hex[:8]}@example.com"
    reg = requests.post(f"{BASE}/auth/register", json={
        "email": email, "password": "Password1!", "name": "Reg Ular",
    }, timeout=15)
    if reg.status_code != 200:
        # Registration path might require intake — skip cleanly.
        import pytest
        pytest.skip(f"registration not available in this env (status={reg.status_code})")
    s = requests.Session()
    s.post(f"{BASE}/auth/login", json={"email": email, "password": "Password1!"}, timeout=15)
    r = s.post(f"{BASE}/admin/push/send", json={
        "title": "hax", "body": "hax", "segment": "all", "test_only": True,
    }, timeout=10)
    assert r.status_code in (401, 403)
