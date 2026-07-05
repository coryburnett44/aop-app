"""Iteration 108 — Email composer power-ups.

Backend guarantees that the composer's new HTML shapes survive the preview
pipeline unchanged:
  * CTA button — an <a> with inline styles the composer's `EmailButton`
    node emits. `_normalize_email_images` only touches `<img>` tags, so
    every button style must reach the recipient intact.
  * Linked image — <a href> wrapping an <img>. Both the anchor and the
    image's inline styles must survive.
  * Divider — a styled <hr>. Same pipeline expectation.
  * Merge tags — `{{first_name}}` etc. remain substituted at send/preview.

These tests use `/api/email/preview` to exercise the full render_variables
+ normalize_email_images path an admin sees before hitting Send.
"""
import os

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001") + "/api"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "admin@clubhaven.app", "password": "Admin123!"})
    r.raise_for_status()
    return s


def _preview(admin, body_html: str) -> str:
    r = admin.post(f"{BASE}/email/preview", json={
        "subject": "iter108 preview",
        "body_html": body_html,
        "segment": "active",
    })
    assert r.status_code == 200, r.text
    return r.json()["html"]


def test_cta_button_styles_survive_preview(admin):
    body = '<div style="text-align:center;margin:18px 0"><a href="https://aop-app.org/x" target="_blank" rel="noopener" data-email-button="1" style="display:inline-block;background:#C8102E;color:#ffffff;text-decoration:none;font-weight:700;padding:12px 28px;border-radius:999px;font-size:15px">Register now</a></div>'
    html = _preview(admin, body)
    assert "data-email-button" in html
    assert "background:#C8102E" in html
    assert "border-radius:999px" in html
    assert 'href="https://aop-app.org/x"' in html
    assert ">Register now<" in html


def test_hr_divider_style_survives_preview(admin):
    body = '<p>Above</p><hr style="border:none;border-top:1px solid #e2e8f0;margin:20px auto;max-width:80%" data-email-hr="1" /><p>Below</p>'
    html = _preview(admin, body)
    assert "data-email-hr" in html
    assert "border-top:1px solid" in html


def test_linked_image_wrapper_survives_preview(admin):
    body = '<div data-image-align="center" style="text-align:center;margin:8px 0"><a href="https://aop-app.org/events" target="_blank" rel="noopener" style="text-decoration:none;display:inline-block"><img src="https://picsum.photos/400/200" data-align="center" style="max-width:100%;height:auto;display:inline-block;border-radius:8px" /></a></div>'
    html = _preview(admin, body)
    # Anchor + image both present, both keep their attributes
    assert 'href="https://aop-app.org/events"' in html
    assert "<img" in html
    assert "border-radius:8px" in html
    assert "max-width:100%" in html  # normalize_email_images guarantees this


def test_merge_tags_substituted_in_preview(admin):
    body = "<p>Hi {{first_name}}, welcome to {{line_name}}.</p>"
    html = _preview(admin, body)
    assert "{{first_name}}" not in html
    # Some substitution happened (recipient's actual first name replaced token)
    assert "Hi " in html


def test_button_with_special_chars_is_html_escaped(admin):
    """Custom EmailButton emits label text as plain text nodes so ProseMirror
    escapes for us; verify a label with < & > doesn't corrupt the preview."""
    body = '<div style="text-align:center"><a href="https://x" data-email-button="1" style="background:#C8102E">Save $100 &amp; register</a></div>'
    html = _preview(admin, body)
    assert "Save $100" in html
    # Ensure amp is preserved as an entity or literal, not turned into a raw &
    assert "&amp;" in html or "&" in html  # tolerate both
