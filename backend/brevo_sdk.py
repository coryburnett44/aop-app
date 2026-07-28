"""Brevo (formerly Sendinblue) transactional-email client — drop-in replacement
for the Resend Python SDK we previously used.

Why a shim?
    We were calling `resend.Emails.send({"from": ..., "to": ..., "subject": ...,
    "html": ...})` in ~15 places across the codebase. Migrating to Brevo without
    touching every call site is a matter of exposing an object with the exact
    same `.Emails.send(params)` shape and forwarding to Brevo's HTTP API.

Usage:
    from brevo_sdk import Brevo
    Brevo.api_key = os.environ["BREVO_API_KEY"]
    Brevo.Emails.send({
        "from": "Alpha Omega Phi <info@aop-app.org>",
        "to": ["member@example.com"],
        "subject": "Hi",
        "html": "<p>Hello</p>",
        "reply_to": "reply@aop-app.org",
        "text": "Hello",             # optional
        "tags": ["announcement"],    # optional (also accepts resend-style [{"name":"tag","value":"v"}])
        "cc": ["cc@example.com"],
        "bcc": ["bcc@example.com"],
        "headers": {"X-Foo": "bar"},
    })

The call is synchronous / blocking (mirrors resend's SDK). Callers already
wrap it in `asyncio.to_thread(...)` so we don't need internal async plumbing.

Errors:
    Non-2xx responses raise `BrevoError` (subclass of `Exception`) with the
    HTTP status and Brevo's JSON error body — matches the behavior of the
    Resend SDK closely enough that existing `try/except` blocks keep working.
"""
from __future__ import annotations

import json
import logging
import os
from email.utils import parseaddr
from typing import Any

import requests

logger = logging.getLogger(__name__)

_BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
_DEFAULT_TIMEOUT = 15  # seconds


class BrevoError(Exception):
    """Raised on non-2xx responses from Brevo. `status` is the HTTP status,
    `body` is the parsed JSON body (or the raw text if not JSON)."""

    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body
        super().__init__(f"Brevo HTTP {status}: {body!r}")


def _to_recipients(value: Any) -> list[dict]:
    """Normalise a resend-style `to`/`cc`/`bcc` value into Brevo's format:
        - "email@x" → [{"email": "email@x"}]
        - ["a@x", "b@x"] → [{"email": "a@x"}, {"email": "b@x"}]
        - [{"email": "a@x", "name": "A"}] → passed through
    Strips falsy entries so we never send an empty recipient object.
    """
    if not value:
        return []
    if isinstance(value, str):
        return [{"email": value}]
    out: list[dict] = []
    for item in value:
        if not item:
            continue
        if isinstance(item, str):
            out.append({"email": item})
        elif isinstance(item, dict) and item.get("email"):
            entry = {"email": item["email"]}
            if item.get("name"):
                entry["name"] = item["name"]
            out.append(entry)
    return out


def _parse_from(value: str) -> dict:
    """"Alpha Omega Phi <info@aop-app.org>" → {"name": "Alpha Omega Phi", "email": "info@aop-app.org"}
    Bare "info@aop-app.org" → {"email": "info@aop-app.org"}."""
    if not value:
        raise BrevoError(400, "from address is required")
    name, email = parseaddr(value)
    if not email:
        # `parseaddr` returned empty email — likely because the caller passed
        # something malformed. Bail out rather than sending to nowhere.
        raise BrevoError(400, f"could not parse from address '{value}'")
    sender: dict = {"email": email}
    if name:
        sender["name"] = name
    return sender


def _normalise_tags(tags: Any) -> list[str] | None:
    """Brevo tags are a flat list of strings. Resend also accepts
    [{"name": "x", "value": "y"}] — flatten those to just the name."""
    if not tags:
        return None
    if isinstance(tags, str):
        return [tags]
    out: list[str] = []
    for t in tags:
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, dict) and t.get("name"):
            out.append(str(t["name"]))
    return out or None


def _translate(params: dict) -> dict:
    """Turn a Resend-shaped payload into a Brevo payload."""
    payload: dict = {
        "sender": _parse_from(params.get("from") or params.get("sender") or ""),
        "to": _to_recipients(params.get("to")),
        "subject": params.get("subject") or "",
    }
    if not payload["to"]:
        raise BrevoError(400, "`to` must have at least one recipient")

    if params.get("html"):
        payload["htmlContent"] = params["html"]
    if params.get("text"):
        payload["textContent"] = params["text"]
    # Brevo requires at least one of htmlContent / textContent.
    if "htmlContent" not in payload and "textContent" not in payload:
        raise BrevoError(400, "one of `html` or `text` is required")

    reply_to = params.get("reply_to") or params.get("replyTo")
    if reply_to:
        if isinstance(reply_to, str):
            payload["replyTo"] = {"email": reply_to}
        elif isinstance(reply_to, dict) and reply_to.get("email"):
            payload["replyTo"] = {k: v for k, v in reply_to.items() if k in ("email", "name")}

    cc = _to_recipients(params.get("cc"))
    if cc:
        payload["cc"] = cc
    bcc = _to_recipients(params.get("bcc"))
    if bcc:
        payload["bcc"] = bcc

    headers = params.get("headers")
    if isinstance(headers, dict) and headers:
        # Brevo accepts a flat {key: value} dict of custom headers.
        payload["headers"] = {str(k): str(v) for k, v in headers.items()}

    tags = _normalise_tags(params.get("tags"))
    if tags:
        payload["tags"] = tags

    if params.get("scheduled_at"):
        payload["scheduledAt"] = params["scheduled_at"]

    # Attachments — resend-style: [{filename, content (b64 or bytes), content_type}]
    # Brevo v3 shape: "attachment": [{"name": "...", "content": "<base64>"}]
    # (singular "attachment", key "name", content MUST be base64 string).
    attachments = params.get("attachments") or params.get("attachment") or []
    if attachments:
        import base64 as _b64
        out_att: list[dict] = []
        for a in attachments:
            if not isinstance(a, dict):
                continue
            name = a.get("filename") or a.get("name")
            content = a.get("content")
            url = a.get("url")
            if url and name:
                # Brevo also supports remote URLs — pass through.
                out_att.append({"url": url, "name": name})
                continue
            if not (name and content is not None):
                continue
            if isinstance(content, (bytes, bytearray)):
                content = _b64.b64encode(bytes(content)).decode("ascii")
            elif isinstance(content, str):
                # Assume already base64 unless it clearly isn't. We accept
                # both because callers historically passed base64 strings.
                content = content
            else:
                # Skip anything we can't serialize.
                continue
            out_att.append({"name": name, "content": content})
        if out_att:
            payload["attachment"] = out_att

    return payload


class _EmailsClient:
    """Mirrors `resend.Emails` — the only method callers use is `send(params)`."""

    def send(self, params: dict) -> dict:
        api_key = Brevo.api_key or os.environ.get("BREVO_API_KEY", "")
        if not api_key:
            # Match Resend SDK's behavior of raising rather than silently
            # dropping. Callers already guard on this with a `if not api_key`
            # check before invoking send, so this is a safety net.
            raise BrevoError(401, "BREVO_API_KEY is not set")

        payload = _translate(params)
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            resp = requests.post(
                _BREVO_ENDPOINT,
                headers=headers,
                data=json.dumps(payload),
                timeout=_DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise BrevoError(0, f"network error: {e}") from e

        if not resp.ok:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            logger.warning("Brevo send failed (%s): %s", resp.status_code, body)
            raise BrevoError(resp.status_code, body)

        try:
            data = resp.json()
        except ValueError:
            data = {}
        # Resend returns {"id": "..."} — Brevo returns {"messageId": "..."}.
        # Provide both keys so consumers that log `resp["id"]` still work.
        if "messageId" in data and "id" not in data:
            data["id"] = data["messageId"]
        return data


class _BrevoNamespace:
    """The single instance the codebase imports as a stand-in for the
    top-level `resend` module."""
    api_key: str = ""  # set at boot from environment
    Emails: _EmailsClient = _EmailsClient()


# The one and only public export — matches the import shape:
#     import brevo_sdk as resend_sdk
#     resend_sdk.api_key = "..."
#     resend_sdk.Emails.send({...})
Brevo = _BrevoNamespace()
api_key = ""   # module-level alias so `brevo_sdk.api_key = X` keeps working
Emails = Brevo.Emails


def __getattr__(name: str):
    # Route module-level attribute assignment (`brevo_sdk.api_key = "..."`)
    # onto the singleton so `Brevo.api_key` stays in sync.
    if name == "api_key":
        return Brevo.api_key
    raise AttributeError(name)
