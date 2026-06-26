"""Iteration 89.4 — `routes/members_admin.py` extraction smoke test.

This is a thin smoke test that the lift-and-shift of the admin member CRUD
out of server.py preserves wire compatibility (paths and status codes
unchanged). The deeper happy-path is already covered by older iterations.
"""
import os
import uuid
import time

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/")

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}


@pytest.fixture(scope="module")
def admin_s():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return s


def test_routes_members_admin_module_importable():
    import sys
    sys.path.insert(0, "/app/backend")
    import importlib
    m = importlib.import_module("routes.members_admin")
    for name in ("register", "_map_row", "_parse_date", "_normalize_title", "_BULK_COLUMN_ALIASES"):
        assert hasattr(m, name), f"missing export: {name}"


def test_server_py_no_longer_owns_admin_member_endpoints():
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    for token in [
        "async def admin_create_member(",
        "async def admin_bulk_import_members(",
        "async def admin_bulk_import_template(",
        "async def admin_resend_set_password(",
        "async def admin_bulk_resend_set_password(",
        "async def admin_update_member(",
        "async def admin_delete_member(",
        "async def update_member_role(",
        "async def assign_chapter(",
        "async def assign_tier(",
    ]:
        assert token not in src, f"server.py still owns extracted symbol: {token!r}"


def test_bulk_import_template_endpoint(admin_s):
    r = admin_s.get(f"{BASE_URL}/api/admin/members/bulk-import/template", timeout=20)
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    text = r.text
    assert "Email" in text
    assert "Renewal Date" in text


def test_create_update_delete_member_roundtrip(admin_s):
    email = f"iter89-4-rt-{uuid.uuid4().hex[:8]}@example.com"
    body = {
        "email": email,
        "first_name": "Iter89.4",
        "last_name": "Roundtrip",
        "password": "Temp123!",
        "role": "member",
    }
    r = admin_s.post(f"{BASE_URL}/api/admin/members", json=body, timeout=20)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]

    try:
        # PUT update
        r = admin_s.put(f"{BASE_URL}/api/members/{uid}", json={"city": "Houston"}, timeout=20)
        assert r.status_code == 200 and r.json()["city"] == "Houston"

        # Chapter assignment
        chapters = admin_s.get(f"{BASE_URL}/api/chapters", timeout=20).json()
        assert chapters, "no chapters in environment"
        chap_id = chapters[0]["id"]
        r = admin_s.put(f"{BASE_URL}/api/members/{uid}/chapter",
                        json={"chapter_id": chap_id}, timeout=20)
        assert r.status_code == 200 and r.json()["chapter_id"] == chap_id

        # Role change
        r = admin_s.put(f"{BASE_URL}/api/members/{uid}/role",
                        json={"role": "admin"}, timeout=20)
        assert r.status_code == 200 and r.json()["role"] == "admin"
    finally:
        r = admin_s.delete(f"{BASE_URL}/api/members/{uid}", timeout=20)
        assert r.status_code == 200


def test_duplicate_email_rejected(admin_s):
    email = f"iter89-4-dup-{uuid.uuid4().hex[:8]}@example.com"
    body = {
        "email": email,
        "first_name": "Dup",
        "last_name": "First",
        "password": "Temp123!",
        "role": "member",
    }
    r = admin_s.post(f"{BASE_URL}/api/admin/members", json=body, timeout=20)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    try:
        # second creation with same email must 400
        r = admin_s.post(f"{BASE_URL}/api/admin/members", json=body, timeout=20)
        assert r.status_code == 400
        assert "already registered" in r.text.lower()
    finally:
        admin_s.delete(f"{BASE_URL}/api/members/{uid}", timeout=20)
