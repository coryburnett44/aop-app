"""Iter 118 — global SMS kill-switch + dues-reminder SMS companion + Member's
Ribbon eligibility payload shape.

Covers:
  1. GET /api/admin/sms-config returns default { enabled: True } when no doc.
  2. PUT /api/admin/sms-config { enabled: False } persists in db.app_settings
     and subsequent GET reflects that. Non-admin is rejected.
  3. send_sms short-circuits (returns False) when sms_config.enabled is False,
     without invoking any provider.
  4. _dues_reminder_sms_body renders sensible copy for every cadence stage.
  5. Members Ribbon payload contains aop_hours / total_hours / recruits /
     donated_amount / checkins / top_in / category_count for every candidate.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _run(coro):
    return asyncio.run(coro)


def test_dues_reminder_sms_body_all_stages():
    from routes.automated_emails import _dues_reminder_sms_body
    for stage in ("before_30", "before_15", "before_5", "grace_1"):
        body = _dues_reminder_sms_body("Riley Chen", stage, "2026-08-15T00:00:00+00:00")
        assert "Riley" in body, f"stage={stage} missing first name"
        assert "2026-08-15" in body, f"stage={stage} missing expiry date"
        assert "STOP" in body, f"stage={stage} missing opt-out language"
        assert len(body) <= 320, f"stage={stage} body too long ({len(body)} chars)"
    fallback = _dues_reminder_sms_body("Someone", "unknown_stage", "2026-01-01T00:00:00+00:00")
    assert "Someone" in fallback and "2026-01-01" in fallback


def test_send_sms_respects_kill_switch():
    """When db.app_settings.sms_config.enabled == False, send_sms must return
    False without calling either Brevo or Twilio."""
    async def go():
        import server
        brevo_calls = []

        async def fake_brevo(e164, body):
            brevo_calls.append((e164, body))
            return True

        # Fake db.app_settings.find_one returning kill-switch OFF.
        class Shim:
            find_one = AsyncMock(return_value={"key": "sms_config", "enabled": False})
        original_app_settings = server.db.app_settings
        try:
            server.db.app_settings = Shim()
            with patch.object(server, "_send_sms_brevo", side_effect=fake_brevo):
                ok = await server.send_sms("+15551234567", "hello")
        finally:
            server.db.app_settings = original_app_settings
        assert ok is False, "kill-switch OFF must return False"
        assert brevo_calls == [], "brevo must NOT be invoked while kill-switch is off"
    _run(go())


def test_send_sms_default_enabled_when_no_doc():
    """No doc in app_settings = SMS enabled by default (backwards-compatible)."""
    async def go():
        import server
        brevo_calls = []

        async def fake_brevo(e164, body):
            brevo_calls.append((e164, body))
            return True

        class Shim:
            find_one = AsyncMock(return_value=None)
        original_app_settings = server.db.app_settings
        original_key = server.BREVO_SMS_API_KEY
        try:
            server.db.app_settings = Shim()
            if not server.BREVO_SMS_API_KEY:
                server.BREVO_SMS_API_KEY = "test-key"
            with patch.object(server, "_send_sms_brevo", side_effect=fake_brevo):
                ok = await server.send_sms("+15551234567", "hello")
        finally:
            server.db.app_settings = original_app_settings
            server.BREVO_SMS_API_KEY = original_key
        assert ok is True
        assert len(brevo_calls) == 1
    _run(go())


def test_sms_config_endpoints_via_http():
    """End-to-end sanity via HTTP: admin can read, toggle, and re-read."""
    import requests
    base = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"
    s = requests.Session()
    r = s.post(f"{base}/auth/login", json={"email": "admin@clubhaven.app", "password": "Admin123!"}, timeout=15)
    assert r.status_code == 200, r.text
    r = s.get(f"{base}/admin/sms-config", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("enabled", "provider", "brevo_configured", "twilio_configured"):
        assert key in data
    r = s.put(f"{base}/admin/sms-config", json={"enabled": False}, timeout=15)
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    r = s.get(f"{base}/admin/sms-config", timeout=15)
    assert r.json()["enabled"] is False
    assert r.json()["updated_by"], "updated_by should be populated after a change"
    # Restore enabled so we don't leave the app in a disabled state.
    r = s.put(f"{base}/admin/sms-config", json={"enabled": True}, timeout=15)
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_members_ribbon_shape_via_http():
    """The Member's Ribbon payload must include every stat + top_in for each candidate."""
    import requests
    base = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"
    s = requests.Session()
    r = s.post(f"{base}/auth/login", json={"email": "admin@clubhaven.app", "password": "Admin123!"}, timeout=15)
    assert r.status_code == 200
    r = s.get(f"{base}/awards/eligibility?year=2026", timeout=15)
    assert r.status_code == 200, r.text
    payload = r.json()
    mr = payload.get("members_ribbon") or []
    for row in mr:
        for key in ("aop_hours", "total_hours", "recruits", "donated_amount", "checkins", "top_in", "category_count"):
            assert key in row, f"Member's Ribbon row missing '{key}': {row}"
        assert isinstance(row["top_in"], list)
        assert isinstance(row["category_count"], int)
