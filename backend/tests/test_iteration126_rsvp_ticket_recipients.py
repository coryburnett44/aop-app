"""Iter 126 — RSVP ticket email must always CC info@alphaomegaphi.org.

Locks in the recipient contract so a future refactor can't accidentally
drop the AOP events inbox from the delivery list.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class _Cursor:
    def __init__(self, docs): self._docs = docs; self._i = 0
    def __aiter__(self): return self
    async def __anext__(self):
        if self._i >= len(self._docs): raise StopAsyncIteration
        d = self._docs[self._i]; self._i += 1; return d


class _RsvpsCol:
    async def update_one(self, *_a, **_kw): return None


class _DB:
    rsvps = _RsvpsCol()


class _API:
    """Duck-types just enough of `FastAPI().router` for `register()` to
    decorate its route handlers without actually mounting them."""
    def get(self, *_a, **_kw):    return lambda f: f
    def post(self, *_a, **_kw):   return lambda f: f
    def put(self, *_a, **_kw):    return lambda f: f
    def delete(self, *_a, **_kw): return lambda f: f
    def patch(self, *_a, **_kw):  return lambda f: f


def _setup_module(mock_resend, events_inbox="info@alphaomegaphi.org"):
    from routes import rsvps
    os.environ["EVENTS_INBOX_EMAIL"] = events_inbox
    rsvps.register(
        _API(),
        db=_DB(),
        get_current_user=lambda: {"id": "u-member"},
        require_admin=lambda: {"id": "admin"},
        event_out=lambda e: e,
        iso=lambda dt: dt.isoformat(),
        now_utc=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        resend_sdk=mock_resend,
        resend_api_key="test-key",
        resend_from="AOP <notify@alphaomegaphi.org>",
        jwt_secret=lambda: "test-jwt-secret",
        jwt_algorithm="HS256",
        logger=__import__("logging").getLogger("test"),
    )
    return rsvps


def test_rsvp_ticket_email_includes_info_inbox():
    """The `to:` list must always contain BOTH the member and the AOP
    events inbox (info@alphaomegaphi.org). This is the recipient contract
    the user explicitly asked us to protect."""
    async def go():
        sends: list = []

        class _MockEmails:
            def send(self, params): sends.append(params); return {"id": "mock"}

        mock_resend = MagicMock()
        mock_resend.Emails = _MockEmails()
        rsvps = _setup_module(mock_resend)
        send = rsvps.register.send_rsvp_ticket_email

        member = {"id": "u-member", "name": "Riley", "email": "riley@example.com"}
        event = {"id": "evt-1", "title": "Iter126 Ticket", "start_at": "2026-08-15T18:00:00+00:00", "location": "Nashville"}
        rsvp_doc = {"id": "rsvp-1", "event_id": "evt-1", "user_id": "u-member",
                    "ticket_id": "tkt-1", "ticket_type": "general", "guests": []}

        ok = await send(member, event, rsvp_doc)
        assert ok is True
        assert len(sends) == 1, f"expected 1 send, got {len(sends)}"
        to_list = sends[0].get("to")
        assert isinstance(to_list, list) and len(to_list) == 2
        assert "riley@example.com" in to_list
        assert "info@alphaomegaphi.org" in to_list, f"info inbox missing from {to_list}"
        assert "Iter126 Ticket" in sends[0]["subject"]

    asyncio.run(go())


def test_rsvp_ticket_email_no_duplicate_when_member_is_events_inbox():
    """If the member's email happens to match the events inbox, dedupe
    so Brevo doesn't get a duplicate `to:` entry."""
    async def go():
        sends: list = []

        class _MockEmails:
            def send(self, params): sends.append(params); return {"id": "mock"}

        mock_resend = MagicMock()
        mock_resend.Emails = _MockEmails()
        rsvps = _setup_module(mock_resend)
        send = rsvps.register.send_rsvp_ticket_email

        member = {"id": "u-inbox", "name": "AOP Inbox", "email": "INFO@alphaomegaphi.org"}
        event = {"id": "evt-2", "title": "Inbox Event", "start_at": "2026-08-15T18:00:00+00:00"}
        rsvp_doc = {"id": "r2", "event_id": "evt-2", "user_id": "u-inbox",
                    "ticket_id": "t2", "ticket_type": "general", "guests": []}

        ok = await send(member, event, rsvp_doc)
        assert ok is True
        to_list = sends[0].get("to")
        lowered = [x.lower() for x in to_list]
        assert lowered.count("info@alphaomegaphi.org") == 1, f"dedupe failed: {to_list}"

    asyncio.run(go())


def test_events_inbox_email_env_var_override():
    """A different EVENTS_INBOX_EMAIL env value must be honored so a
    chapter can point RSVP CCs at their own address."""
    async def go():
        sends: list = []

        class _MockEmails:
            def send(self, params): sends.append(params); return {"id": "mock"}

        mock_resend = MagicMock()
        mock_resend.Emails = _MockEmails()
        os.environ["EVENTS_INBOX_EMAIL"] = "chapter@example.com"
        rsvps = _setup_module(mock_resend, events_inbox="chapter@example.com")
        send = rsvps.register.send_rsvp_ticket_email

        member = {"id": "u", "email": "member@example.com", "name": "M"}
        event = {"id": "e", "title": "Chapter Event", "start_at": "2026-08-01T18:00:00+00:00"}
        rsvp_doc = {"id": "r", "event_id": "e", "user_id": "u",
                    "ticket_id": "t", "ticket_type": "general", "guests": []}

        await send(member, event, rsvp_doc)
        to_list = sends[0].get("to")
        assert "chapter@example.com" in to_list
        # Restore default for other tests.
        os.environ["EVENTS_INBOX_EMAIL"] = "info@alphaomegaphi.org"

    asyncio.run(go())
