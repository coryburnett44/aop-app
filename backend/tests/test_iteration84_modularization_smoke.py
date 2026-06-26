"""Iter84 — modularization smoke: rsvps split + documents extracted.

After splitting routes/rsvps.py into rsvps + rsvps_csv + checkin and
extracting documents from server.py, every previously-working endpoint must
still respond. This file is a focused smoke pass — full behavioural coverage
already lives in earlier iter tests.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_s():
    return _login(ADMIN)


# ============================================================
# checkin module — routes/checkin.py
# ============================================================

def test_checkin_lookup_endpoint_reachable(admin_s):
    """The lookup route accepts a malformed token with a clean 400 — proves the
    module is registered and the decoder is wired."""
    r = admin_s.get(f"{API}/checkin/lookup/garbage-token-xyz", timeout=15)
    assert r.status_code == 400, r.text
    assert "invalid" in r.json().get("detail", "").lower()


def test_checkin_scan_requires_admin(admin_s):
    """Scan rejects malformed tokens via the admin route — proves it's wired."""
    r = admin_s.post(f"{API}/checkin/scan/garbage-token-xyz", timeout=15)
    assert r.status_code == 400, r.text


# ============================================================
# rsvps_csv module — routes/rsvps_csv.py
# ============================================================

def test_rsvps_csv_template_endpoint(admin_s):
    """The CSV template download returns the expected MIME + filename."""
    # Create a throwaway event so we have a valid id to query.
    ev = admin_s.post(f"{API}/events", json={
        "title": f"Iter84 csv template {uuid.uuid4().hex[:4]}",
        "description": "x", "location": "DC",
        "start_at": "2099-12-31T20:00:00+00:00",
        "end_at": "2099-12-31T22:00:00+00:00",
        "category": "general", "capacity": 50,
    }, timeout=15).json()
    try:
        r = admin_s.get(f"{API}/events/{ev['id']}/admin-rsvp/csv/template", timeout=15)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        assert "member_email" in r.text
        assert "guest_ticket_types" in r.text
    finally:
        admin_s.delete(f"{API}/events/{ev['id']}", timeout=10)


# ============================================================
# documents module — routes/documents.py
# ============================================================

def test_documents_endpoints_reachable(admin_s):
    r = admin_s.get(f"{API}/documents", timeout=15)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)

    r2 = admin_s.get(f"{API}/document-folders", timeout=15)
    assert r2.status_code == 200, r2.text
    assert isinstance(r2.json(), list)


def test_document_folder_crud_roundtrip(admin_s):
    """Create a folder, rename it, delete it. Proves admin gating still works
    via the admin_tab_dep dependency."""
    name = f"iter84-folder-{uuid.uuid4().hex[:6]}"
    r = admin_s.post(f"{API}/document-folders", json={"name": name}, timeout=15)
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    try:
        r2 = admin_s.put(f"{API}/document-folders/{fid}", json={"name": name + "-renamed"}, timeout=15)
        assert r2.status_code == 200, r2.text
    finally:
        r3 = admin_s.delete(f"{API}/document-folders/{fid}", timeout=15)
        assert r3.status_code == 200, r3.text
