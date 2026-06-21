"""
Iteration 54 — Admin full edit of submitted hours.

Validates the new `PUT /api/hours/{id}` endpoint:
  - Admin can update every editable field (activity, description, event_type,
    agency_name, host fields, hours, date, status, note).
  - Hours value change stamps `hours_adjusted_by/_at`.
  - Status flip stamps `reviewed_by/_at`.
  - Non-admin gets 403.
  - Unknown id → 404.
  - Empty body is a no-op.

Run: REACT_APP_BACKEND_URL=... pytest /app/backend/tests/test_iteration54_admin_edit_hours.py -v
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PW = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PW = "Member123!"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture
def member_session():
    return _login(MEMBER_EMAIL, MEMBER_PW)


@pytest.fixture
def pending_hours_id(member_session, admin_session):
    """Create a fresh pending hours entry, yield its id, delete on teardown."""
    r = member_session.post(
        f"{API}/hours",
        json={
            "activity": "iter54 original activity",
            "agency_name": "Original Agency",
            "host_name": "Original Host",
            "host_email": "orig@example.com",
            "host_phone": "555-0001",
            "event_type": "aop_related",
            "hours": 3.0,
            "date": "2026-02-01T10:00:00",
            "description": "original description",
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    hid = r.json()["id"]
    yield hid
    # cleanup
    admin_session.delete(f"{API}/hours/{hid}", timeout=10)


def test_admin_can_edit_every_field(admin_session, pending_hours_id):
    payload = {
        "activity": "iter54 NEW activity",
        "description": "NEW description",
        "event_type": "other",
        "agency_name": "NewAgency",
        "host_name": "NewHost",
        "host_email": "new@example.com",
        "host_phone": "555-9999",
        "hours": 4.5,
        "date": "2026-03-15T08:30:00",
        "status": "approved",
        "note": "admin corrected",
    }
    r = admin_session.put(f"{API}/hours/{pending_hours_id}", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["activity"] == "iter54 NEW activity"
    assert d["description"] == "NEW description"
    assert d["event_type"] == "other"
    assert d["agency_name"] == "NewAgency"
    assert d["host_name"] == "NewHost"
    assert d["host_email"] == "new@example.com"
    assert d["host_phone"] == "555-9999"
    assert d["hours"] == 4.5
    assert d["date"].startswith("2026-03-15")
    assert d["status"] == "approved"
    assert d["note"] == "admin corrected"
    # Audit stamps must populate for both hours change AND status change
    assert d.get("hours_adjusted_by_name"), "hours_adjusted_by_name should be set"
    assert d.get("reviewed_by_name"), "reviewed_by_name should be set"


def test_admin_partial_edit_only_writes_supplied_fields(admin_session, pending_hours_id):
    """Sending only `activity` must NOT clobber other fields."""
    r = admin_session.put(
        f"{API}/hours/{pending_hours_id}",
        json={"activity": "only this changed"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["activity"] == "only this changed"
    # Untouched fields keep their original values
    assert d["agency_name"] == "Original Agency"
    assert d["host_name"] == "Original Host"
    assert d["host_email"] == "orig@example.com"
    assert d["hours"] == 3.0
    assert d["status"] == "pending"
    # No hours-adjustment audit because hours didn't change
    assert not d.get("hours_adjusted_by_name")


def test_admin_edit_hours_only_stamps_adjustment_not_review(admin_session, pending_hours_id):
    r = admin_session.put(f"{API}/hours/{pending_hours_id}", json={"hours": 2.0}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["hours"] == 2.0
    assert d.get("hours_adjusted_by_name")
    # Status unchanged → reviewed_by must remain unset
    assert d["status"] == "pending"
    assert not d.get("reviewed_by_name")


def test_admin_status_only_stamps_review_not_adjustment(admin_session, pending_hours_id):
    r = admin_session.put(f"{API}/hours/{pending_hours_id}", json={"status": "approved"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "approved"
    assert d.get("reviewed_by_name")
    assert d["hours"] == 3.0
    assert not d.get("hours_adjusted_by_name")


def test_non_admin_cannot_edit(member_session, pending_hours_id):
    r = member_session.put(
        f"{API}/hours/{pending_hours_id}",
        json={"activity": "hack"},
        timeout=15,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


def test_unknown_id_returns_404(admin_session):
    r = admin_session.put(f"{API}/hours/does-not-exist", json={"activity": "x"}, timeout=10)
    assert r.status_code == 404


def test_empty_body_is_noop(admin_session, pending_hours_id):
    r = admin_session.put(f"{API}/hours/{pending_hours_id}", json={}, timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    # Original values preserved
    assert d["activity"] == "iter54 original activity"
    assert d["hours"] == 3.0
    assert d["status"] == "pending"
