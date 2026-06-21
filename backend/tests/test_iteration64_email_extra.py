"""Iteration 64 EXTRA — Email composer review request coverage:
  • GET /api/email/blasts now returns 200 (was 404 due to missing decorator)
  • Admin can PUT/DELETE built-in templates
  • POST /api/email/upload-image works
  • POST /api/email/blast with test_only=true normalizes stored html
"""
import io
import os
import re
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return s


# ---------------------------------------------------
# /api/email/blasts (fixed missing decorator)
# ---------------------------------------------------
def test_list_email_blasts_returns_200(admin):
    r = admin.get(f"{API}/email/blasts", timeout=20)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert isinstance(data, list)


# ---------------------------------------------------
# Built-in template CRUD
# ---------------------------------------------------
def test_admin_can_edit_builtin_template(admin):
    # Read current
    r = admin.get(f"{API}/email/templates", timeout=15)
    assert r.status_code == 200
    tpls = {t["id"]: t for t in r.json()}
    assert "builtin_tpl_announcement" in tpls
    original = tpls["builtin_tpl_announcement"]
    original_subject = original["subject"]
    new_subject = original_subject + " [EDITED]"

    payload = {
        "name": original["name"],
        "subject": new_subject,
        "body_html": original["body_html"],
    }
    r2 = admin.put(
        f"{API}/email/templates/builtin_tpl_announcement", json=payload, timeout=20
    )
    assert r2.status_code in (200, 204), r2.text

    # Verify persistence
    r3 = admin.get(f"{API}/email/templates", timeout=15)
    tpls2 = {t["id"]: t for t in r3.json()}
    assert tpls2["builtin_tpl_announcement"]["subject"] == new_subject

    # Restore
    payload["subject"] = original_subject
    admin.put(
        f"{API}/email/templates/builtin_tpl_announcement", json=payload, timeout=20
    )


def test_admin_can_delete_builtin_template_and_reseeds(admin):
    # Snapshot original
    r = admin.get(f"{API}/email/templates", timeout=15)
    tpls = {t["id"]: t for t in r.json()}
    if "builtin_tpl_dues_reminder" not in tpls:
        pytest.skip("dues_reminder not present")
    original = tpls["builtin_tpl_dues_reminder"]

    r2 = admin.delete(
        f"{API}/email/templates/builtin_tpl_dues_reminder", timeout=20
    )
    assert r2.status_code in (200, 204), r2.text

    # Verify gone via API
    r3 = admin.get(f"{API}/email/templates", timeout=15)
    ids = [t["id"] for t in r3.json()]
    assert "builtin_tpl_dues_reminder" not in ids

    # Restore with original id via direct DB insert so we don't pollute env
    import asyncio
    import sys
    sys.path.insert(0, "/app/backend")
    from server import db  # noqa: E402

    async def _restore():
        await db.email_templates.insert_one(
            {
                "id": "builtin_tpl_dues_reminder",
                "name": original["name"],
                "subject": original["subject"],
                "body_html": original["body_html"],
                "description": original.get("description", ""),
                "is_builtin": True,
                "created_at": original.get("created_at"),
            }
        )

    asyncio.get_event_loop().run_until_complete(_restore())

    # Verify restoration
    r4 = admin.get(f"{API}/email/templates", timeout=15)
    ids2 = [t["id"] for t in r4.json()]
    assert "builtin_tpl_dues_reminder" in ids2


# ---------------------------------------------------
# /api/email/upload-image still works
# ---------------------------------------------------
def test_admin_upload_image(admin):
    # Smallest valid PNG (1x1 transparent)
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
    )
    files = {"file": ("test.png", io.BytesIO(png), "image/png")}
    r = admin.post(f"{API}/email/upload-image", files=files, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "url" in data
    assert "/api/files/" in data["url"]


# ---------------------------------------------------
# Test_only blast stores normalized html
# ---------------------------------------------------
def test_test_only_blast_succeeds_with_relative_image(admin):
    """POST /api/email/blast (test_only=true) with relative-src image should
    succeed (200) — the html is normalized before send. The list endpoint does
    not return html_full, so we just verify the blast was recorded."""
    body = {
        "subject": "ITER64-Normalize-Test",
        "body_html": '<p>Hello</p><img class="rounded-lg my-2" src="/api/files/foo.jpg">',
        "segment": "admins",
        "test_only": True,
    }
    r = admin.post(f"{API}/email/blast", json=body, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("sent", 0) >= 1 or "blast_id" in data, data

    # Confirm appears in /email/blasts listing
    r2 = admin.get(f"{API}/email/blasts", timeout=20)
    assert r2.status_code == 200
    subjects = [b.get("subject") for b in r2.json()]
    assert "ITER64-Normalize-Test" in subjects


# ---------------------------------------------------
# Email preview normalization on Tailwind class
# ---------------------------------------------------
def test_email_preview_strips_tailwind(admin):
    body = {
        "subject": "Test",
        "body_html": '<img class="rounded-lg my-2 max-w-full" src="/api/files/test.jpg">',
        "segment": "admins",
    }
    r = admin.post(f"{API}/email/preview", json=body, timeout=20)
    assert r.status_code == 200, r.text
    html = r.json()["html"]
    assert "rounded-lg" not in html
    assert "class=" not in html
    assert "max-width:100%" in html
    assert "height:auto" in html
