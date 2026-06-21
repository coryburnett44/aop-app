"""
Iteration 57 — Per-cause payment processor (PayPal vs Zeffy).

Covers:
  - POST /causes accepts {payment_processor, zeffy_url}
  - Default processor is "paypal", default zeffy_url is ""
  - Invalid processor value returns 422
  - PUT /causes/{id} can toggle processor and clear zeffy_url
  - GET /causes returns the new fields on every cause
  - Non-admin cannot create/update causes (403)

Run: REACT_APP_BACKEND_URL=... pytest /app/backend/tests/test_iteration57_cause_processor.py -v
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PW = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PW = "Member123!"

MARKER_TITLE = f"iter57-cause-{int(time.time())}"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def member():
    return _login(MEMBER_EMAIL, MEMBER_PW)


@pytest.fixture
def created_cause(admin):
    """Create a Zeffy cause, yield its id, then DELETE it after the test."""
    r = admin.post(
        f"{API}/causes",
        json={
            "title": f"{MARKER_TITLE} zeffy",
            "goal_amount": 500,
            "payment_processor": "zeffy",
            "zeffy_url": "https://www.zeffy.com/en-US/donation-form/test-fixture",
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    yield cid
    admin.delete(f"{API}/causes/{cid}", timeout=10)


def test_create_with_zeffy_persists_fields(created_cause, admin):
    r = admin.get(f"{API}/causes/{created_cause}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["payment_processor"] == "zeffy"
    assert d["zeffy_url"] == "https://www.zeffy.com/en-US/donation-form/test-fixture"


def test_create_defaults_to_paypal(admin):
    r = admin.post(
        f"{API}/causes",
        json={"title": f"{MARKER_TITLE} default", "goal_amount": 100},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    cid = d["id"]
    try:
        assert d["payment_processor"] == "paypal"
        assert d["zeffy_url"] == ""
    finally:
        admin.delete(f"{API}/causes/{cid}", timeout=10)


def test_invalid_processor_rejected(admin):
    r = admin.post(
        f"{API}/causes",
        json={"title": f"{MARKER_TITLE} bad", "payment_processor": "venmo"},
        timeout=10,
    )
    assert r.status_code == 422


def test_update_toggles_processor_and_clears_url(admin, created_cause):
    r = admin.put(
        f"{API}/causes/{created_cause}",
        json={"payment_processor": "paypal", "zeffy_url": ""},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["payment_processor"] == "paypal"
    assert d["zeffy_url"] == ""


def test_list_returns_new_fields(admin, created_cause):
    r = admin.get(f"{API}/causes", timeout=10)
    assert r.status_code == 200
    items = r.json()
    target = next((c for c in items if c["id"] == created_cause), None)
    assert target is not None
    assert "payment_processor" in target
    assert "zeffy_url" in target


def test_non_admin_cannot_create(member):
    r = member.post(
        f"{API}/causes",
        json={"title": f"{MARKER_TITLE} hack", "payment_processor": "zeffy", "zeffy_url": "https://x"},
        timeout=10,
    )
    assert r.status_code == 403


def test_non_admin_cannot_update(member, created_cause):
    r = member.put(
        f"{API}/causes/{created_cause}",
        json={"payment_processor": "zeffy"},
        timeout=10,
    )
    assert r.status_code == 403


def test_partial_update_preserves_existing_processor(admin, created_cause):
    # Re-set to zeffy + url so we have a known starting state
    admin.put(f"{API}/causes/{created_cause}", json={"payment_processor": "zeffy", "zeffy_url": "https://example.com/z"}, timeout=10)
    # Touch only an unrelated field — processor & url must survive
    r = admin.put(f"{API}/causes/{created_cause}", json={"goal_amount": 999}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["payment_processor"] == "zeffy"
    assert d["zeffy_url"] == "https://example.com/z"
    assert d["goal_amount"] == 999
