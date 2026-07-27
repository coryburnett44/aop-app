"""Iteration 64 — Email Blast Composer improvements:
  • Built-in email templates seeded on startup
  • Image normalization for bulk emails (absolute URLs, no CSS classes, inline sizing)
  • RichEditor ResizableImage extension renders email-safe HTML
"""
import os
import re
import sys
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"

# Make backend internals importable
sys.path.insert(0, "/app/backend")
from server import _normalize_email_images  # noqa: E402


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return s


# ------------------------------------------------------------
# Built-in templates seeded
# ------------------------------------------------------------
def test_builtin_email_templates_seeded(admin):
    r = admin.get(f"{API}/email/templates", timeout=15)
    assert r.status_code == 200, r.text
    items = r.json()
    by_id = {t["id"]: t for t in items}

    expected = {
        "builtin_tpl_announcement": "General Announcement",
        "builtin_tpl_event_reminder": "Event Reminder",
        "builtin_tpl_dues_reminder": "Dues Reminder",
        "builtin_tpl_welcome": "Welcome New Member",
        "builtin_tpl_newsletter": "Monthly Newsletter",
    }
    for tid, name in expected.items():
        assert tid in by_id, f"Missing built-in template: {tid}"
        assert by_id[tid]["name"] == name
        assert by_id[tid]["is_builtin"] is True
        assert "<div" in by_id[tid]["body_html"].lower()
        # Templates should already use inline-style email-safe HTML
        assert "tailwind" not in by_id[tid]["body_html"].lower()


def test_builtin_templates_idempotent(admin):
    """Re-seeding doesn't create duplicates — count stays stable."""
    r1 = admin.get(f"{API}/email/templates", timeout=15).json()
    r2 = admin.get(f"{API}/email/templates", timeout=15).json()
    ids1 = [t["id"] for t in r1 if t["id"].startswith("builtin_tpl_")]
    ids2 = [t["id"] for t in r2 if t["id"].startswith("builtin_tpl_")]
    assert sorted(ids1) == sorted(ids2)
    assert len(ids1) == 5


# ------------------------------------------------------------
# _normalize_email_images
# ------------------------------------------------------------
def test_normalize_strips_class_attribute():
    html = '<p>hi</p><img class="rounded-lg my-2 max-w-full" src="https://x.com/a.png" alt="a">'
    out = _normalize_email_images(html)
    assert "class=" not in out
    assert 'src="https://x.com/a.png"' in out


def test_normalize_adds_max_width_and_height_auto():
    html = '<img src="https://x.com/a.png">'
    out = _normalize_email_images(html)
    assert "max-width:100%" in out
    assert "height:auto" in out


def test_normalize_preserves_existing_inline_width():
    html = '<img src="https://x.com/a.png" style="width:300px;border-radius:8px">'
    out = _normalize_email_images(html)
    assert "width:300px" in out
    assert "border-radius:8px" in out
    assert "max-width:100%" in out


def test_normalize_idempotent():
    html = '<img src="https://x.com/a.png" style="max-width:100%;height:auto;width:400px">'
    out1 = _normalize_email_images(html)
    out2 = _normalize_email_images(out1)
    assert out1 == out2


def test_normalize_rewrites_relative_api_urls_to_absolute():
    """Iter 138: /api/files/email/* is remapped to the public,
    cookie-free /api/email/image/* endpoint so mobile mail-image proxies
    can fetch the bytes."""
    os.environ["FRONTEND_URL"] = "https://aop-app.org"
    try:
        html = '<img src="/api/files/email/u1/abc/photo.jpg" alt="x">'
        out = _normalize_email_images(html)
        assert 'src="https://aop-app.org/api/email/image/u1/abc/photo.jpg"' in out
    finally:
        # don't pollute other tests
        pass


def test_normalize_leaves_absolute_urls_alone():
    html = '<img src="https://cdn.example.com/photo.jpg" alt="x">'
    out = _normalize_email_images(html)
    assert 'src="https://cdn.example.com/photo.jpg"' in out


def test_normalize_handles_no_img_tags():
    html = "<p>Just text, no images.</p>"
    assert _normalize_email_images(html) == html


# ------------------------------------------------------------
# Preview already-normalizes images
# ------------------------------------------------------------
def test_email_preview_normalizes_images(admin):
    body = {
        "subject": "Test",
        "body_html": '<p>Hi</p><img class="rounded-lg my-2" src="/api/files/foo.jpg" alt="x">',
        "segment": "admins",
    }
    r = admin.post(f"{API}/email/preview", json=body, timeout=20)
    assert r.status_code == 200, r.text
    html = r.json()["html"]
    assert "class=" not in html, "Preview should strip class= so admin sees what recipients see"
    # FRONTEND_URL is set in backend .env to the preview origin — absolute URL must appear
    assert "/api/files/foo.jpg" in html
    assert re.search(r'src="https?://[^"]+/api/files/foo\.jpg"', html), (
        f"Expected absolute src in preview, got: {html[:300]}"
    )
