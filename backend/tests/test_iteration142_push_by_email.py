"""Iter 142 — admin push composer accepts recipient emails.

The old UI required opaque Mongo user_ids. Admins know members by email,
so the composer now takes `custom_emails: List[str]` and resolves them
server-side. Missing addresses are surfaced back to the caller.
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


def test_push_by_email_resolves_matching_members():
    admin = _login("admin@clubhaven.app", "Admin123!")
    payload = {
        "title": f"iter142 email test {uuid.uuid4().hex[:6]}",
        "body": "regression body",
        "segment": "custom",
        "custom_emails": ["admin@clubhaven.app"],
    }
    r = admin.post(f"{BASE}/admin/push/send", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "admin@clubhaven.app" in data["matched_emails"]
    assert data["unmatched_emails"] == []
    assert data["target_count"] == 1


def test_push_by_email_surfaces_unmatched_but_still_sends_when_partial_match():
    admin = _login("admin@clubhaven.app", "Admin123!")
    payload = {
        "title": f"iter142 partial test {uuid.uuid4().hex[:6]}",
        "body": "regression body",
        "segment": "custom",
        "custom_emails": ["admin@clubhaven.app", f"ghost-{uuid.uuid4().hex[:8]}@example.com"],
    }
    r = admin.post(f"{BASE}/admin/push/send", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "admin@clubhaven.app" in data["matched_emails"]
    assert len(data["unmatched_emails"]) == 1
    assert data["target_count"] == 1


def test_push_by_email_rejects_when_no_email_matches():
    admin = _login("admin@clubhaven.app", "Admin123!")
    payload = {
        "title": f"iter142 all-invalid {uuid.uuid4().hex[:6]}",
        "body": "regression body",
        "segment": "custom",
        "custom_emails": [f"nobody-{uuid.uuid4().hex[:8]}@example.com"],
    }
    r = admin.post(f"{BASE}/admin/push/send", json=payload, timeout=15)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "no_matching_recipients"
    assert len(detail["unmatched_emails"]) == 1


def test_push_by_email_is_case_insensitive():
    admin = _login("admin@clubhaven.app", "Admin123!")
    payload = {
        "title": f"iter142 case test {uuid.uuid4().hex[:6]}",
        "body": "regression body",
        "segment": "custom",
        "custom_emails": ["ADMIN@Clubhaven.App"],  # mixed case
    }
    r = admin.post(f"{BASE}/admin/push/send", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_count"] == 1
    assert data["unmatched_emails"] == []


def test_legacy_user_ids_path_still_works_for_backwards_compat():
    """The composer still accepts `user_ids` directly — used by callers
    (like automated triggers) that already have the id in hand."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    # Resolve the admin's user_id via the email path (works everywhere).
    resolved = admin.post(f"{BASE}/admin/push/send", json={
        "title": "uid-lookup", "body": "x", "segment": "custom",
        "custom_emails": ["admin@clubhaven.app"], "test_only": False,
    }, timeout=15).json()
    hist = admin.get(f"{BASE}/admin/push/history", timeout=10).json()
    admin_uid = next((h["user_ids"][0] for h in hist if h.get("user_ids")), None)
    assert admin_uid, f"expected admin uid in push history (resolved={resolved})"
    payload = {
        "title": f"iter142 uid test {uuid.uuid4().hex[:6]}",
        "body": "regression body",
        "segment": "custom",
        "user_ids": [admin_uid],
    }
    r = admin.post(f"{BASE}/admin/push/send", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_count"] == 1
