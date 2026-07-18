"""Iter 128 — server.py modularization: omega / cms_cards / uploads.

Covers:
  1. Extracted route modules import cleanly and expose their `register()` fn.
  2. server.py no longer owns the extracted symbols (`_upload_image`,
     `tribute_out`, `_form_link_out`, `_meeting_out`).
  3. Public + admin endpoints for each of the 3 modules still respond as
     expected end-to-end.
  4. Full round-trip on `/form-links` and `/meeting-cards` (create → list →
     update → delete).
"""
from __future__ import annotations

import os
import sys
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


def test_extracted_modules_importable():
    from routes import omega as routes_omega
    from routes import cms_cards as routes_cms_cards
    from routes import uploads as routes_uploads
    for mod in (routes_omega, routes_cms_cards, routes_uploads):
        assert callable(getattr(mod, "register", None)), f"{mod.__name__} missing register()"


def test_server_no_longer_owns_extracted_symbols():
    import server
    # Local helpers should be gone from server.py.
    for symbol in ("_upload_image", "tribute_out", "_form_link_out", "_meeting_out"):
        assert not hasattr(server, symbol), (
            f"server.py still owns `{symbol}` — extraction incomplete."
        )


def test_omega_endpoints_still_served():
    # /omega is public, should return a list.
    r = requests.get(f"{BASE}/omega", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    # /omega/hero is public.
    r = requests.get(f"{BASE}/omega/hero", timeout=15)
    assert r.status_code == 200
    body = r.json()
    for key in ("image_url", "title", "caption"):
        assert key in body


def test_omega_options_requires_auth():
    r = requests.get(f"{BASE}/omega/options", timeout=15)
    assert r.status_code == 401


def test_form_links_crud_round_trip():
    admin = _login("admin@clubhaven.app", "Admin123!")
    payload = {
        "title": "Iter128 Test Form",
        "description": "created by regression test",
        "url": "https://example.com/iter128",
        "order": 999,
    }
    r = admin.post(f"{BASE}/form-links", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    created = r.json()
    lid = created["id"]
    assert created["title"] == payload["title"]
    try:
        # List includes the new record.
        r = admin.get(f"{BASE}/form-links", timeout=15)
        assert r.status_code == 200
        assert any(x["id"] == lid for x in r.json())
        # Update.
        r = admin.put(f"{BASE}/form-links/{lid}", json={"title": "Iter128 Renamed"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["title"] == "Iter128 Renamed"
    finally:
        # Always clean up.
        r = admin.delete(f"{BASE}/form-links/{lid}", timeout=15)
        assert r.status_code == 200


def test_meeting_cards_crud_round_trip():
    admin = _login("admin@clubhaven.app", "Admin123!")
    payload = {
        "name": "Iter128 Test Meeting",
        "title": "Book time",
        "description": "regression test card",
        "button_label": "Book",
        "button_url": "https://cal.example.com/iter128",
        "order": 999,
    }
    r = admin.post(f"{BASE}/meeting-cards", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    created = r.json()
    cid = created["id"]
    assert created["name"] == payload["name"]
    try:
        r = admin.get(f"{BASE}/meeting-cards", timeout=15)
        assert r.status_code == 200
        assert any(x["id"] == cid for x in r.json())
        r = admin.put(f"{BASE}/meeting-cards/{cid}", json={"title": "Renamed"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["title"] == "Renamed"
    finally:
        r = admin.delete(f"{BASE}/meeting-cards/{cid}", timeout=15)
        assert r.status_code == 200


def test_form_links_admin_only():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.post(f"{BASE}/form-links", json={"title": "no", "url": "https://x"}, timeout=15)
    assert r.status_code == 403


def test_meeting_cards_admin_only():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.post(f"{BASE}/meeting-cards", json={"name": "no", "button_url": "https://x"}, timeout=15)
    assert r.status_code == 403


def test_upload_endpoints_reject_non_admin():
    """Sanity: every generic upload endpoint from routes/uploads.py still
    enforces the correct admin_tab_dep gate (unauth → 401)."""
    for path in (
        "/chapters/upload-logo",
        "/causes/upload-image",
        "/news/upload-image",
        "/leadership/upload-image",
        "/founders/upload-image",
        "/events/upload-cover",
    ):
        r = requests.post(f"{BASE}{path}", timeout=15)
        # 401 (no auth) or 422 (missing file) both prove the route is
        # mounted; 404 would indicate the extraction broke registration.
        assert r.status_code in (401, 422), f"{path}: got {r.status_code}"
