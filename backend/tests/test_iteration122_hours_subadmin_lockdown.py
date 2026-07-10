"""Iter 122 — Sub-admin lock-down on hours.

Rules enforced:
  1. Governor Manager and Membership Manager can log hours for THEMSELVES
     only (via `POST /hours`).
  2. `POST /hours/admin`, `POST /hours/admin/bulk`, and
     `POST /hours/admin/csv` are restricted to Full Access + Operations
     Manager admins.
  3. `PUT /hours/{id}/review` and `PUT /hours/{id}` (status/hours edits)
     are also restricted to Full Access + Operations Manager admins.
  4. Full Access admins remain unrestricted (they still auto-approve).

These tests exercise the backend directly — the frontend UI already
hides the "Log for others" toggle and the Review Queue tab for these
sub-roles.
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


def _own_payload(activity: str = "iter122 self", hours: float = 1.0) -> dict:
    return {
        "hours": hours, "date": "2026-07-10T00:00:00",
        "event_type": "other", "agency_name": "AOP",
        "activity": activity, "description": activity,
        "host_name": "Self", "host_email": "self@ex.com", "host_phone": "555-1234",
    }


# ============================================================
# 1) Sub-admins CANNOT log for others via /hours/admin(/bulk|/csv)
# ============================================================
def test_governor_manager_blocked_from_hours_admin():
    gov = _login("governor.tx@clubhaven.app", "Governor123!")
    r = gov.post(f"{BASE}/hours/admin", json={
        "user_id": "irrelevant", "hours": 1, "date": "2026-07-10T00:00:00",
        "event_type": "other", "agency_name": "x", "activity": "y",
    }, timeout=15)
    assert r.status_code == 403
    assert "full access" in (r.json().get("detail") or "").lower() or "operations manager" in (r.json().get("detail") or "").lower()


def test_governor_manager_blocked_from_hours_admin_bulk():
    gov = _login("governor.tx@clubhaven.app", "Governor123!")
    r = gov.post(f"{BASE}/hours/admin/bulk", json={
        "user_ids": ["a"], "hours": 1, "date": "2026-07-10T00:00:00", "event_type": "other",
    }, timeout=15)
    assert r.status_code == 403


def test_membership_manager_blocked_from_hours_admin_and_bulk():
    mm = _login("mm.tx@clubhaven.app", "MemMgr123!")
    # MM lacks the `hours` admin tab entirely — expect 403 either way.
    for path in ("/hours/admin", "/hours/admin/bulk"):
        r = mm.post(f"{BASE}{path}", json={"user_id": "x", "user_ids": ["x"], "hours": 1, "date": "2026-07-10T00:00:00", "event_type": "other"}, timeout=15)
        assert r.status_code == 403, f"{path} should reject MM — got {r.status_code}"


# ============================================================
# 2) Sub-admins CAN still log for themselves
# ============================================================
def test_governor_manager_can_log_own_hours():
    gov = _login("governor.tx@clubhaven.app", "Governor123!")
    r = gov.post(f"{BASE}/hours", json=_own_payload("iter122 gov self", 1.75), timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"


def test_membership_manager_can_log_own_hours():
    mm = _login("mm.tx@clubhaven.app", "MemMgr123!")
    r = mm.post(f"{BASE}/hours", json=_own_payload("iter122 mm self", 2.25), timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"


# ============================================================
# 3) Only Full Access + Operations Manager can review pending hours
# ============================================================
def test_governor_manager_blocked_from_review():
    """Governor Manager loses its former ability to review — approval is
    now reserved for Full Access + Operations Manager."""
    gov = _login("governor.tx@clubhaven.app", "Governor123!")
    # Create a pending entry as the Governor themselves.
    r = gov.post(f"{BASE}/hours", json=_own_payload("iter122 gov review target", 0.5), timeout=15)
    assert r.status_code == 200
    hid = r.json()["id"]
    # Governor tries to approve → 403.
    r = gov.put(f"{BASE}/hours/{hid}/review", json={"status": "approved"}, timeout=15)
    assert r.status_code == 403, f"expected 403 got {r.status_code} · {r.text}"


def test_full_admin_can_still_review():
    """Regression — Full Access admin can still approve pending entries."""
    gov = _login("governor.tx@clubhaven.app", "Governor123!")
    r = gov.post(f"{BASE}/hours", json=_own_payload("iter122 gov approval target", 0.5), timeout=15)
    hid = r.json()["id"]
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.put(f"{BASE}/hours/{hid}/review", json={"status": "approved"}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json().get("reviewed_by")
