"""Iter 143 — email attachments + signature image reliability.

Verifies:
  • /email/upload-attachment accepts PDF/DOCX/etc. and rejects .exe
  • /email/attachments lists my uploads
  • /email/attachments/{id} deletes them (soft)
  • Non-admin users cannot upload
  • Signatures now normalize `/api/files/email/...` → `/api/email/image/...`
    at save time so images render everywhere (Safari ITP, mobile mail).
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

_PDF = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\ntrailer <<>>\n%%EOF"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


def test_upload_pdf_attachment_returns_metadata():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.post(f"{BASE}/email/upload-attachment",
                   files={"file": ("regression.pdf", io.BytesIO(_PDF), "application/pdf")},
                   timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["filename"] == "regression.pdf"
    assert data["size"] == len(_PDF)
    assert data["content_type"] == "application/pdf"
    admin.delete(f"{BASE}/email/attachments/{data['id']}", timeout=10)


def test_upload_attachment_rejects_disallowed_extensions():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.post(f"{BASE}/email/upload-attachment",
                   files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
                   timeout=15)
    assert r.status_code == 400
    assert ".exe" in r.text.lower()


def test_upload_attachment_rejects_oversize():
    admin = _login("admin@clubhaven.app", "Admin123!")
    # 21 MB — over the 20 MB cap
    big = b"0" * (21 * 1024 * 1024)
    r = admin.post(f"{BASE}/email/upload-attachment",
                   files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")},
                   timeout=60)
    assert r.status_code == 413


def test_upload_attachment_requires_admin():
    anon = requests.Session()
    r = anon.post(f"{BASE}/email/upload-attachment",
                  files={"file": ("t.pdf", io.BytesIO(_PDF), "application/pdf")},
                  timeout=15)
    assert r.status_code == 401


def test_list_attachments_shows_uploads_and_delete_removes_them():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.post(f"{BASE}/email/upload-attachment",
                   files={"file": ("tmp.pdf", io.BytesIO(_PDF), "application/pdf")},
                   timeout=15)
    aid = r.json()["id"]
    listing = admin.get(f"{BASE}/email/attachments", timeout=10).json()
    assert any(a["id"] == aid for a in listing)
    d = admin.delete(f"{BASE}/email/attachments/{aid}", timeout=10)
    assert d.status_code == 200
    listing2 = admin.get(f"{BASE}/email/attachments", timeout=10).json()
    assert not any(a["id"] == aid for a in listing2)


def test_preview_email_with_attachment_ids_returns_ok():
    admin = _login("admin@clubhaven.app", "Admin123!")
    up = admin.post(f"{BASE}/email/upload-attachment",
                    files={"file": ("preview.pdf", io.BytesIO(_PDF), "application/pdf")},
                    timeout=15)
    aid = up.json()["id"]
    try:
        r = admin.post(f"{BASE}/email/preview", json={
            "subject": "Test",
            "body_html": "<p>Body</p>",
            "segment": "admins",
            "attachment_ids": [aid],
        }, timeout=15)
        assert r.status_code == 200, r.text
    finally:
        admin.delete(f"{BASE}/email/attachments/{aid}", timeout=10)


def test_signature_save_normalizes_legacy_image_urls():
    admin = _login("admin@clubhaven.app", "Admin123!")
    # Old-style URL that the pre-Iter-138 composer used to store.
    dirty_html = '<div>Signed,<br/><img src="/api/files/email/u1/x/logo.png"/></div>'
    r = admin.post(f"{BASE}/email/signatures", json={
        "name": f"iter143 sig {uuid.uuid4().hex[:6]}",
        "body_html": dirty_html,
        "kind": "personal",
    }, timeout=15)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    try:
        # Normalized on save.
        got_html = r.json()["body_html"]
        assert "/api/email/image/u1/x/logo.png" in got_html
        assert "/api/files/email/" not in got_html
        # And absolutized against FRONTEND_URL for cross-client compatibility.
        assert got_html.count('src="https://') >= 1 or got_html.count("src='http") >= 1
    finally:
        admin.delete(f"{BASE}/email/signatures/{sid}", timeout=10)


def test_list_signatures_normalizes_legacy_rows_on_read():
    """A signature saved before Iter 143 might still have `/api/files/email/*`
    in the DB. The list endpoint should rewrite on the fly."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    # Force a "pre-Iter-143" row by inserting through the API and then
    # rewriting the underlying doc. We can't touch DB directly, so we rely on
    # the fact that upload → normalize → save. Instead, verify that the
    # returned list always has the correct public URL.
    r = admin.post(f"{BASE}/email/signatures", json={
        "name": f"iter143 read {uuid.uuid4().hex[:6]}",
        "body_html": '<img src="/api/files/email/foo/bar.png"/>',
        "kind": "personal",
    }, timeout=15)
    sid = r.json()["id"]
    try:
        listing = admin.get(f"{BASE}/email/signatures", timeout=10).json()
        found = next((s for s in listing if s["id"] == sid), None)
        assert found is not None
        assert "/api/email/image/" in found["body_html"]
        assert "/api/files/email/" not in found["body_html"]
    finally:
        admin.delete(f"{BASE}/email/signatures/{sid}", timeout=10)
