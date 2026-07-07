"""Iter 119 — Member-side SMS preferences.

Covers:
  1. GET /api/me/sms-preferences returns { phone, sms_opt_out, sms_prefs }.
     Defaults are `sms_opt_out=False`, `sms_prefs.dues_reminders=True`.
  2. PUT /api/me/sms-preferences persists partial updates:
      - Setting `dues_reminders=False` disables just that category.
      - Setting `sms_opt_out=True` stamps `sms_opt_out_at`.
      - Re-enabling `dues_reminders` when master opt-out is on
        auto-clears both `sms_opt_out` and `sms_opt_out_at`.
  3. Dues-reminder SMS is suppressed when the member has
     `sms_prefs.dues_reminders=False`, even with a valid phone number
     and master opt-out cleared.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


def test_sms_preferences_defaults_and_toggle_flow():
    s = _login("member@clubhaven.app", "Member123!")

    # 1. Reset to a known-good state (dues on, master off).
    r = s.put(f"{BASE}/me/sms-preferences", json={"dues_reminders": True, "sms_opt_out": False}, timeout=15)
    assert r.status_code == 200

    # 2. GET returns the current shape.
    r = s.get(f"{BASE}/me/sms-preferences", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data.keys()) >= {"phone", "sms_opt_out", "sms_opt_out_at", "sms_prefs"}
    assert data["sms_opt_out"] is False
    assert data["sms_prefs"]["dues_reminders"] is True

    # 3. Disable just the dues category — master stays off.
    r = s.put(f"{BASE}/me/sms-preferences", json={"dues_reminders": False}, timeout=15)
    assert r.status_code == 200 and r.json()["sms_prefs"]["dues_reminders"] is False
    assert r.json()["sms_opt_out"] is False

    # 4. Master opt-out stamps sms_opt_out_at.
    r = s.put(f"{BASE}/me/sms-preferences", json={"sms_opt_out": True}, timeout=15)
    assert r.status_code == 200 and r.json()["sms_opt_out"] is True
    r = s.get(f"{BASE}/me/sms-preferences", timeout=15)
    assert r.json()["sms_opt_out_at"], "sms_opt_out_at should be stamped when opting out"

    # 5. Re-enabling any sub-category auto-clears the master opt-out.
    r = s.put(f"{BASE}/me/sms-preferences", json={"dues_reminders": True}, timeout=15)
    assert r.status_code == 200
    assert r.json()["sms_opt_out"] is False
    r = s.get(f"{BASE}/me/sms-preferences", timeout=15)
    assert not r.json().get("sms_opt_out_at")


def test_sms_preferences_requires_auth():
    r = requests.get(f"{BASE}/me/sms-preferences", timeout=15)
    assert r.status_code in (401, 403)


def test_dues_reminder_respects_sms_prefs():
    """The dues-reminder SMS fan-out must honor sms_prefs.dues_reminders=False
    (per-category opt-out) even when phone is present and master opt-out is
    cleared."""
    async def go():
        from routes import automated_emails
        calls = []

        async def fake_send_sms(phone, body):
            calls.append((phone, body))
            return True

        # Minimal in-memory DB stub covering just the collections the helper
        # touches. `find` returns an async cursor; `find_one` returns None
        # so the dedupe check passes; `insert_one` is a noop.
        USER_ON = {
            "id": "u-on", "name": "Opted In", "email": "on@example.com",
            "membership_expires_at": "2026-08-15T00:00:00+00:00",
            "phone": "5551110001",
            "sms_opt_out": False,
            "sms_prefs": {"dues_reminders": True},
        }
        USER_OFF = {
            "id": "u-off", "name": "Opted Out", "email": "off@example.com",
            "membership_expires_at": "2026-08-15T00:00:00+00:00",
            "phone": "5551110002",
            "sms_opt_out": False,
            "sms_prefs": {"dues_reminders": False},
        }

        class _Cursor:
            def __init__(self, docs):
                self._docs = list(docs)
                self._i = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._i >= len(self._docs):
                    raise StopAsyncIteration
                d = self._docs[self._i]
                self._i += 1
                return d

        class _Users:
            def find(self, *a, **kw):
                # Only return docs on the 30d bucket; the other stages get empty.
                offset = a[0].get("membership_expires_at", {}).get("$gte", "")
                # First stage checked is before_30 whose target day matches
                # our seeded expires. All subsequent day-buckets get empty.
                if not getattr(_Users, "_served", False):
                    _Users._served = True
                    return _Cursor([USER_ON, USER_OFF])
                return _Cursor([])

        class _DedupeSent:
            async def find_one(self, *a, **kw): return None
            async def insert_one(self, *a, **kw): return None

        class _DB:
            users = _Users()
            dues_reminders_sent = _DedupeSent()

        # send_bulk_email is called for the email side — we don't care about
        # the return, just that it doesn't raise.
        sent_emails = []

        async def fake_send_bulk_email(**kwargs):
            sent_emails.append(kwargs)
            return True

        # Patch module-level state and helpers.
        automated_emails.db = _DB()
        automated_emails.iso = lambda dt: dt.isoformat()
        automated_emails.now_utc = lambda: __import__("datetime").datetime(2026, 7, 16, tzinfo=__import__("datetime").timezone.utc)
        automated_emails.logger = __import__("logging").getLogger("test")
        automated_emails.RESEND_API_KEY = "test-key"
        automated_emails.send_bulk_email = fake_send_bulk_email
        automated_emails.send_sms = fake_send_sms

        try:
            await automated_emails._send_dues_reminders({
                "id": "camp-test", "name": "Dues Reminders Test", "kind": "dues_reminders",
            })
        finally:
            # Clear class-level state so re-runs are clean.
            try:
                del automated_emails.db.users.__class__._served
            except AttributeError:
                pass

        # Only the opted-in member should have gotten an SMS.
        phones = [c[0] for c in calls]
        assert "5551110001" in phones, f"opted-in member did NOT receive SMS: {phones}"
        assert "5551110002" not in phones, f"opted-out member DID receive SMS: {phones}"

    asyncio.run(go())
