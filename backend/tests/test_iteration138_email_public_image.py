"""Iter 138 — public /api/email/image/* endpoint + rich editor color/bg.

Ensures mobile email clients (Gmail/iOS Mail) can fetch embedded images
without needing a session cookie, and that admin-composed emails can set
a background color which wraps the message body when sent/previewed.
"""
from __future__ import annotations

import io
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


# Smallest valid PNG (1x1 transparent)
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)


def test_email_upload_returns_public_email_image_url():
    admin = _login("admin@clubhaven.app", "Admin123!")
    files = {"file": ("t.png", io.BytesIO(_PNG), "image/png")}
    r = admin.post(f"{BASE}/email/upload-image", files=files, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["url"].startswith("/api/email/image/email/"), data["url"]


def test_public_email_image_endpoint_no_cookie_required():
    admin = _login("admin@clubhaven.app", "Admin123!")
    files = {"file": ("t.png", io.BytesIO(_PNG), "image/png")}
    r = admin.post(f"{BASE}/email/upload-image", files=files, timeout=30)
    url_path = r.json()["url"]
    # New, cookie-less session — mimics a mail-image proxy fetching the src.
    anon = requests.Session()
    resp = anon.get(f"{BASE.replace('/api', '')}{url_path}", timeout=15)
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("Content-Type", "").startswith("image/")
    # It must NOT tumble to a login page or return 401.


def test_public_email_image_endpoint_rejects_non_email_paths():
    # Even with an anonymous fetch, non-email storage paths cannot be leaked.
    anon = requests.Session()
    r = anon.get(f"{BASE}/email/image/random/xyz.png", timeout=10)
    assert r.status_code == 404


def test_email_preview_wraps_body_with_background_color():
    admin = _login("admin@clubhaven.app", "Admin123!")
    body = {
        "subject": "Test {{name}}",
        "body_html": '<p>Hi</p>',
        "background_color": "#F0F9FF",
        "segment": "admins",
    }
    r = admin.post(f"{BASE}/email/preview", json=body, timeout=15)
    assert r.status_code == 200, r.text
    html = r.json()["html"]
    assert "#F0F9FF" in html or "#f0f9ff" in html.lower()
    assert 'style="background-color:#F0F9FF' in html


def test_email_preview_rewrites_files_email_to_public_image_endpoint():
    admin = _login("admin@clubhaven.app", "Admin123!")
    body = {
        "subject": "Test",
        "body_html": '<p><img src="/api/files/email/u/a/p.png"/></p>',
        "segment": "admins",
    }
    r = admin.post(f"{BASE}/email/preview", json=body, timeout=15)
    assert r.status_code == 200, r.text
    html = r.json()["html"]
    # Image URL rewritten AND absolutized.
    assert "/api/email/image/u/a/p.png" in html
    assert "/api/files/email/" not in html


def test_news_accepts_body_html_and_background_color():
    admin = _login("admin@clubhaven.app", "Admin123!")
    tag = uuid.uuid4().hex[:6]
    payload = {
        "title": f"Rich article {tag}",
        "summary": "s",
        "body": "plain fallback",
        "body_html": '<p style="color:#C8102E"><strong>Rich</strong> content <u>underlined</u> and <mark style="background-color:#FEF3C7">highlighted</mark>.</p>',
        "background_color": "#FFF7ED",
    }
    r = admin.post(f"{BASE}/news", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    try:
        got = admin.get(f"{BASE}/news/{nid}", timeout=10).json()
        assert got["body_html"].startswith('<p style="color:#C8102E">')
        assert got["background_color"] == "#FFF7ED"
        # Legacy plain-text body still stored for older readers/search.
        assert got["body"] == "plain fallback"
    finally:
        admin.delete(f"{BASE}/news/{nid}", timeout=10)
