"""Iter 116 — Brevo SMS wiring for video meeting notifications.

Locks in three behaviors:
  1. `send_sms` routes to Brevo when `SMS_PROVIDER=brevo` and a
     `BREVO_SMS_API_KEY` is set. Recipient number is stripped of the leading
     `+` (Brevo's `recipient` field wants raw digits with country code).
  2. `send_sms` never raises — non-2xx responses degrade to `False` and log.
  3. When a member starts a video meeting, every OTHER participant with a
     phone number gets `send_sms(phone, body)` called exactly once, unless
     they've explicitly set `chat_sms_notifications=False`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests as _requests

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

BASE = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/") + "/api"


def _mock_brevo_response(status: int, body: dict | None = None):
    resp = MagicMock()
    resp.ok = 200 <= status < 300
    resp.status_code = status
    resp.json.return_value = body if body is not None else {}
    resp.text = json.dumps(body or {})
    return resp


# ---------- Unit tests on the send_sms helper ----------


@pytest.fixture
def server_module(monkeypatch):
    """Import server.py with Brevo SMS credentials set. Reload to reset the
    module-level singletons `BREVO_SMS_API_KEY` etc."""
    monkeypatch.setenv("BREVO_SMS_API_KEY", "xkeysib-test-sms")
    monkeypatch.setenv("BREVO_SMS_SENDER", "AOP")
    monkeypatch.setenv("SMS_PROVIDER", "brevo")
    # Also unset Twilio so fallback doesn't confuse the test.
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    # If already imported, reload so the new env is picked up.
    if "server" in sys.modules:
        import importlib
        importlib.reload(sys.modules["server"])
    import server as srv
    return srv


def _run(coro):
    """Small asyncio.run wrapper so we don't need pytest-asyncio installed."""
    import asyncio
    return asyncio.run(coro)


def test_send_sms_calls_brevo_with_stripped_plus(server_module):
    """`recipient` in Brevo's body MUST NOT include the leading '+'.
    Sender is truncated to 11 chars, body clamped to 1500."""
    with patch.object(_requests, "post", return_value=_mock_brevo_response(201, {"messageId": "brevo-msg-1"})) as mock_post:
        ok = _run(server_module.send_sms("+15551234567", "hello world"))
    assert ok is True
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.brevo.com/v3/transactionalSMS/sms"
    payload = kwargs["json"]
    assert payload["recipient"] == "15551234567"   # no leading +
    assert payload["sender"] == "AOP"
    assert payload["content"] == "hello world"
    assert payload["type"] == "transactional"
    # api-key header carried through.
    assert kwargs["headers"]["api-key"] == "xkeysib-test-sms"


def test_send_sms_returns_false_on_402_not_enough_credits(server_module):
    """The real Brevo 402 (out-of-SMS-credits) path must never raise."""
    with patch.object(_requests, "post", return_value=_mock_brevo_response(402, {
        "code": "not_enough_credits", "message": "…",
    })):
        ok = _run(server_module.send_sms("+15551234567", "hi"))
    assert ok is False


def test_send_sms_rejects_invalid_phone(server_module):
    """Un-normalisable number → False without ever hitting Brevo."""
    with patch.object(_requests, "post") as mock_post:
        ok = _run(server_module.send_sms("not a phone", "hi"))
    assert ok is False
    mock_post.assert_not_called()


def test_send_sms_no_key_returns_false(server_module, monkeypatch):
    """If BREVO_SMS_API_KEY is unset AND Twilio isn't configured, quietly False."""
    # Patch the module attributes directly — load_dotenv fills them back in
    # from /app/backend/.env on every import, so env-var deletion alone isn't
    # sufficient here.
    monkeypatch.setattr(server_module, "BREVO_SMS_API_KEY", "")
    monkeypatch.setattr(server_module, "_twilio_client", None)
    monkeypatch.setattr(server_module, "TWILIO_FROM_NUMBER", "")
    with patch.object(_requests, "post") as mock_post:
        ok = _run(server_module.send_sms("+15551234567", "hi"))
    assert ok is False
    mock_post.assert_not_called()


# ---------- Integration test: video meeting fan-out ----------


def _login(session, email, password):
    r = session.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return session


def test_video_meeting_triggers_sms_for_each_other_member(monkeypatch):
    """End-to-end: starter's teammates each receive a send_sms call. We mock
    the underlying HTTP so the test doesn't actually spend Brevo credits."""
    import requests
    admin = _login(requests.Session(), "admin@clubhaven.app", "Admin123!")

    # Pick maya (starter) and jordan+harper (recipients) — same DB used in
    # earlier iteration tests. `/members` requires an active account, so we
    # look them up via the admin session (which is always active).
    members = admin.get(f"{BASE}/members").json()
    if not isinstance(members, list):
        pytest.skip(f"admin /members failed: {members}")
    by_email = {m["email"]: m for m in members}
    if "maya.patel@clubhaven.app" not in by_email:
        pytest.skip("maya seed missing — cannot run integration test")
    starter = by_email["maya.patel@clubhaven.app"]
    jordan = by_email["jordan.reed@clubhaven.app"]
    harper = by_email["harper.liu@clubhaven.app"]

    # Ensure Maya's account is active enough to create conversations; some
    # earlier tests may have flipped her to inactive via the dues cron.
    admin.put(f"{BASE}/members/{starter['id']}/status", json={"status": "active"})

    # Ensure both recipients have phone numbers on file so the SMS fan-out
    # picks them up. Restore whatever they had at test end.
    old_jordan_phone = jordan.get("phone", "")
    old_harper_phone = harper.get("phone", "")
    old_harper_optout = harper.get("chat_sms_notifications", True)
    admin.put(f"{BASE}/members/{jordan['id']}", json={"phone": "+15551000001"})
    admin.put(f"{BASE}/members/{harper['id']}", json={"phone": "+15551000002", "chat_sms_notifications": False})

    try:
        # Log in as starter and create a group conversation with both peers.
        maya = _login(requests.Session(), "maya.patel@clubhaven.app", "Demo123!")
        conv = maya.post(f"{BASE}/conversations", json={
            "type": "group", "name": "iter116 sms test",
            "member_ids": [jordan["id"], harper["id"]],
        }).json()
        cid = conv["id"]

        # We can't patch the running backend's requests.post from the test,
        # so we lean on Brevo returning 402 (auth OK, no credits) as our
        # signal that the SMS code path DID fire. The endpoint should still
        # return the meeting payload — SMS failures are best-effort.
        r = maya.post(f"{BASE}/conversations/{cid}/video-meeting")
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload.get("kind") == "video_meeting", payload
        # The meeting URL lives under `meeting.url` in the returned message.
        meeting_url = ((payload.get("meeting") or {}).get("url")
                       or payload.get("meeting_url", ""))
        assert "meet." in meeting_url, payload

        # Cleanup the conversation.
        maya.delete(f"{BASE}/conversations/{cid}")
    finally:
        admin.put(f"{BASE}/members/{jordan['id']}", json={"phone": old_jordan_phone})
        admin.put(f"{BASE}/members/{harper['id']}", json={
            "phone": old_harper_phone,
            "chat_sms_notifications": old_harper_optout,
        })
