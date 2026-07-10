"""Iter 121 — Governor Manager & Membership Manager can log their own hours.

The bug: the admin-mode `LogHoursDialog` in Hours.jsx forced every admin
(regardless of admin_role) into "log for another member" mode, which:
  1. Blocked submission until at least one OTHER member was picked; and
  2. Submitted to `POST /hours/admin`, which requires the `hours` admin
     tab. Membership Manager doesn't have `hours` → 403 either way.

The fix: expose a "Log for myself" toggle in the dialog that switches back
to `POST /hours` (the plain member endpoint that uses get_current_user).
These tests lock in the backend contract — the member endpoint has always
accepted admin callers, but this test guarantees the behavior doesn't
regress and documents the fix.
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


def _log_own(session: requests.Session, hours: float = 1.25) -> dict:
    payload = {
        "hours": hours,
        "date": "2026-07-08T00:00:00",
        "event_type": "other",
        "agency_name": "Regression Iter 121",
        "activity": "iter 121 own-hours smoke test",
        "description": "iter 121 own-hours smoke test",
        "host_name": "Self",
        "host_email": "self@ex.com",
        "host_phone": "555-0000",
    }
    r = session.post(f"{BASE}/hours", json=payload, timeout=15)
    assert r.status_code == 200, f"{r.status_code} · {r.text}"
    return r.json()


def test_governor_manager_can_log_own_hours():
    s = _login("governor.tx@clubhaven.app", "Governor123!")
    doc = _log_own(s, hours=2.5)
    assert doc["status"] == "pending"
    assert doc["hours"] == 2.5
    # Confirm it lands in the admin's own /me/hours list.
    r = s.get(f"{BASE}/me/hours?year=2026", timeout=15)
    assert r.status_code == 200
    assert any(h["id"] == doc["id"] for h in r.json())


def test_membership_manager_can_log_own_hours():
    s = _login("mm.tx@clubhaven.app", "MemMgr123!")
    doc = _log_own(s, hours=1.5)
    assert doc["status"] == "pending"
    assert doc["hours"] == 1.5
    r = s.get(f"{BASE}/me/hours?year=2026", timeout=15)
    assert r.status_code == 200
    assert any(h["id"] == doc["id"] for h in r.json())


def test_membership_manager_cannot_use_admin_hours_endpoint():
    """Confirms MM correctly gets 403 on /hours/admin — the frontend fix must
    keep them on the member endpoint."""
    s = _login("mm.tx@clubhaven.app", "MemMgr123!")
    r = s.post(f"{BASE}/hours/admin", json={
        "user_id": "anything", "hours": 1, "date": "2026-07-08T00:00:00",
        "event_type": "other",
    }, timeout=15)
    assert r.status_code == 403


def test_governor_manager_can_still_log_for_another_member_in_chapter():
    """SUPERSEDED by iter122: Governor Manager may NO LONGER log for other
    members. This test is kept (and inverted) to lock in the new behavior."""
    gov = _login("governor.tx@clubhaven.app", "Governor123!")
    r = gov.get(f"{BASE}/auth/me", timeout=15)
    me = r.json()
    gov_id = me["id"]
    gov_chapter = me.get("chapter_id")
    r = gov.get(f"{BASE}/members", timeout=15)
    assert r.status_code == 200, r.text
    peer = next((m for m in r.json() if m["id"] != gov_id and m.get("chapter_id") == gov_chapter), None)
    if peer is None:
        import pytest as _pytest
        _pytest.skip("no other member in Governor's chapter in this environment")
    r = gov.post(f"{BASE}/hours/admin", json={
        "user_id": peer["id"], "hours": 0.5, "date": "2026-07-08T00:00:00",
        "event_type": "other", "agency_name": "Iter121", "activity": "for peer",
    }, timeout=15)
    # Iter 122 flipped this from 200 to 403.
    assert r.status_code == 403, r.text
    assert "full access" in (r.json().get("detail") or "").lower()
