"""Iter 115 — Brevo email migration.

Locks in the Resend → Brevo drop-in swap:
  * `brevo_sdk.Emails.send({...})` accepts the same Resend-shaped payload
    (from / to / subject / html / text / reply_to / tags / cc / bcc / headers).
  * Payload translation matches Brevo's REST body (sender / to / htmlContent /
    replyTo / tags / cc / bcc / headers).
  * Ambiguous inputs (bare "from" email, mixed-type tags, string vs list "to")
    are all normalised without crashing.

These are pure unit tests — they never hit Brevo's HTTP endpoint. Network
calls are patched via `unittest.mock`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure the backend folder is on sys.path so we can import brevo_sdk
# whether we're invoked from repo root or /app/backend.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import brevo_sdk  # noqa: E402


def _make_response(status: int = 201, body: dict | None = None):
    resp = MagicMock()
    resp.ok = 200 <= status < 300
    resp.status_code = status
    resp.json.return_value = body if body is not None else {"messageId": "<test@brevo>"}
    resp.text = json.dumps(body or {})
    return resp


@pytest.fixture(autouse=True)
def _configure_key():
    """Every test needs a non-empty api_key so the shim doesn't 401 early."""
    prev = brevo_sdk.Brevo.api_key
    brevo_sdk.Brevo.api_key = "xkeysib-test-key"
    yield
    brevo_sdk.Brevo.api_key = prev


def test_resend_style_payload_maps_to_brevo_body():
    """The workhorse — verifies every Resend param has a Brevo counterpart."""
    with patch("brevo_sdk.requests.post", return_value=_make_response()) as mock_post:
        brevo_sdk.Brevo.Emails.send({
            "from": "Alpha Omega Phi <info@aop-app.org>",
            "to": ["a@example.com", "b@example.com"],
            "subject": "Hi there",
            "html": "<p>Hello</p>",
            "text": "Hello",
            "reply_to": "reply@aop-app.org",
            "cc": ["c@example.com"],
            "bcc": ["bcc@example.com"],
            "headers": {"X-Foo": "bar"},
            "tags": [{"name": "type", "value": "welcome"}, "manual-tag"],
        })
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.brevo.com/v3/smtp/email"
    assert kwargs["headers"]["api-key"] == "xkeysib-test-key"
    body = json.loads(kwargs["data"])
    assert body["sender"] == {"name": "Alpha Omega Phi", "email": "info@aop-app.org"}
    assert body["to"] == [{"email": "a@example.com"}, {"email": "b@example.com"}]
    assert body["subject"] == "Hi there"
    assert body["htmlContent"] == "<p>Hello</p>"
    assert body["textContent"] == "Hello"
    assert body["replyTo"] == {"email": "reply@aop-app.org"}
    assert body["cc"] == [{"email": "c@example.com"}]
    assert body["bcc"] == [{"email": "bcc@example.com"}]
    assert body["headers"] == {"X-Foo": "bar"}
    # Tag dict → name; plain string preserved.
    assert body["tags"] == ["type", "manual-tag"]


def test_bare_email_from_and_string_to():
    with patch("brevo_sdk.requests.post", return_value=_make_response()) as mock_post:
        brevo_sdk.Brevo.Emails.send({
            "from": "info@aop-app.org",
            "to": "single@example.com",
            "subject": "s",
            "html": "<p>h</p>",
        })
    body = json.loads(mock_post.call_args[1]["data"])
    assert body["sender"] == {"email": "info@aop-app.org"}  # no name key
    assert body["to"] == [{"email": "single@example.com"}]


def test_response_exposes_both_messageId_and_id():
    """Callers do `.get('id')` (from the Resend SDK). Preserve that."""
    with patch("brevo_sdk.requests.post", return_value=_make_response(body={"messageId": "<abc>"})):
        resp = brevo_sdk.Brevo.Emails.send({
            "from": "info@aop-app.org",
            "to": "x@example.com",
            "subject": "s",
            "html": "<p>h</p>",
        })
    assert resp["messageId"] == "<abc>"
    assert resp["id"] == "<abc>"


def test_missing_body_raises():
    with pytest.raises(brevo_sdk.BrevoError, match="html.*text"):
        brevo_sdk.Brevo.Emails.send({
            "from": "info@aop-app.org",
            "to": "x@example.com",
            "subject": "s",
        })


def test_missing_from_raises():
    with pytest.raises(brevo_sdk.BrevoError, match="from"):
        brevo_sdk.Brevo.Emails.send({
            "to": "x@example.com",
            "subject": "s",
            "html": "<p>h</p>",
        })


def test_empty_to_raises():
    with pytest.raises(brevo_sdk.BrevoError, match="recipient"):
        brevo_sdk.Brevo.Emails.send({
            "from": "info@aop-app.org",
            "to": [],
            "subject": "s",
            "html": "<p>h</p>",
        })


def test_missing_api_key_raises():
    brevo_sdk.Brevo.api_key = ""
    with pytest.raises(brevo_sdk.BrevoError) as excinfo:
        brevo_sdk.Brevo.Emails.send({
            "from": "info@aop-app.org",
            "to": "x@example.com",
            "subject": "s",
            "html": "<p>h</p>",
        })
    assert excinfo.value.status == 401


def test_non_2xx_raises_with_status_and_body():
    with patch("brevo_sdk.requests.post", return_value=_make_response(400, {"code": "bad", "message": "sender invalid"})):
        with pytest.raises(brevo_sdk.BrevoError) as excinfo:
            brevo_sdk.Brevo.Emails.send({
                "from": "info@aop-app.org",
                "to": "x@example.com",
                "subject": "s",
                "html": "<p>h</p>",
            })
    assert excinfo.value.status == 400
    assert "sender invalid" in str(excinfo.value.body)
