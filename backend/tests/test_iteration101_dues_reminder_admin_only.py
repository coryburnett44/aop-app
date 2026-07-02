"""Iteration 101 — Dues reminders: members receive direct emails, and the
admin summary digest is scoped to full-access / operations_manager /
membership_manager (Governor Managers are excluded).

Verifies `_send_dues_reminders` end-to-end with fake db collections and
mocked delivery hooks (`send_bulk_email` + `resend_sdk.Emails.send`):

1. Members whose dues hit each stage window receive a direct reminder via
   `send_bulk_email`.
2. Governor Managers are excluded from the admin digest.
3. Full-access, operations_manager, and membership_manager admins DO
   receive the digest.
4. Dedupe collection prevents re-alerts within the same cycle.

Run: pytest /app/backend/tests/test_iteration101_dues_reminder_admin_only.py -v
"""
import asyncio
import importlib
import sys
import types
from datetime import timedelta

import pytest


sys.path.insert(0, "/app/backend")
server = importlib.import_module("server")
ae = importlib.import_module("routes.automated_emails")


# ---------- Async-aware fake collections ----------
class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _FakeUsers:
    """`db.users.find(query, projection)` filters an in-memory list against
    the fields `_send_dues_reminders` and `_send_admin_dues_summary`
    actually use (role, membership_expires_at range, email presence,
    email_opt_out, email_prefs.dues_reminders)."""
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, projection=None):
        out = []
        for u in self._docs:
            if "role" in query and u.get("role") != query["role"]:
                continue
            if "membership_expires_at" in query:
                rng = query["membership_expires_at"]
                exp = u.get("membership_expires_at")
                if not exp:
                    continue
                if "$gte" in rng and exp < rng["$gte"]:
                    continue
                if "$lt" in rng and exp >= rng["$lt"]:
                    continue
            if query.get("status", {}).get("$ne") == "inactive" and u.get("status") == "inactive":
                continue
            if query.get("is_lifetime_member", {}).get("$ne") is True and u.get("is_lifetime_member") is True:
                continue
            if "email" in query:
                email_q = query["email"]
                if email_q.get("$exists") and not u.get("email"):
                    continue
                if email_q.get("$ne") == "" and u.get("email") == "":
                    continue
            if query.get("email_opt_out", {}).get("$ne") is True and u.get("email_opt_out") is True:
                continue
            if query.get("email_prefs.dues_reminders", {}).get("$ne") is False:
                if (u.get("email_prefs") or {}).get("dues_reminders") is False:
                    continue
            out.append(u)
        return _FakeCursor(out)


class _FakeReminderSent:
    """Async-compatible fake for `db.dues_reminders_sent`."""
    def __init__(self):
        self._store = []

    async def find_one(self, query, projection=None):
        for r in self._store:
            if all(r.get(k) == v for k, v in query.items()):
                return r
        return None

    async def insert_one(self, doc):
        self._store.append(dict(doc))
        return types.SimpleNamespace(inserted_id=doc.get("id"))


# ---------- Fixture ----------
@pytest.fixture
def dues_env(monkeypatch):
    """Wire up fake db + capture mocks for both member delivery and admin
    digest delivery."""
    member_emails: list[dict] = []
    admin_emails: list[dict] = []

    async def fake_send_bulk(*, to_email, subject, html_body, recipient_id=None, tags=None, **kw):
        member_emails.append({
            "to": to_email, "subject": subject, "html": html_body,
            "recipient_id": recipient_id, "tags": tags or [],
        })

    monkeypatch.setattr(ae, "send_bulk_email", fake_send_bulk, raising=False)
    monkeypatch.setattr(ae, "RESEND_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(ae, "resend_sdk", server.resend_sdk, raising=False)
    monkeypatch.setattr(ae, "RESEND_FROM", "test@local", raising=False)
    monkeypatch.setattr(ae, "RESEND_REPLY_TO", "test@local", raising=False)
    monkeypatch.setattr(ae, "iso", server.iso, raising=False)
    monkeypatch.setattr(ae, "now_utc", server.now_utc, raising=False)
    monkeypatch.setattr(ae, "logger", server.logger, raising=False)
    monkeypatch.setattr(
        server.resend_sdk.Emails, "send",
        lambda payload: admin_emails.append(payload) or {"id": f"id-{len(admin_emails)}"},
    )

    state = {
        "users": [],
        "reminder_sent": _FakeReminderSent(),
        "member_emails": member_emails,
        "admin_emails": admin_emails,
    }

    def _set_users(docs):
        state["users"] = docs
        fake_db = types.SimpleNamespace(
            users=_FakeUsers(state["users"]),
            dues_reminders_sent=state["reminder_sent"],
        )
        monkeypatch.setattr(ae, "db", fake_db, raising=False)

    state["set_users"] = _set_users
    _set_users([])  # default empty
    return state


def _member(id_, email, expires_days, **overrides):
    now = server.now_utc()
    exp = (now + timedelta(days=expires_days)).replace(hour=12, minute=0, second=0, microsecond=0)
    return {
        "id": id_, "email": email, "name": email.split("@")[0].title(),
        "role": "member", "status": "active", "is_lifetime_member": False,
        "membership_expires_at": exp.isoformat(),
        "email_opt_out": False, "email_prefs": {"dues_reminders": True},
        **overrides,
    }


def _admin(id_, email, admin_role):
    return {
        "id": id_, "email": email, "name": email.split("@")[0].title(),
        "role": "admin", "admin_role": admin_role, "status": "active",
        "email_opt_out": False, "email_prefs": {"dues_reminders": True},
    }


# ---------- Tests ----------
def test_members_receive_reminders_and_digest_excludes_governor(dues_env):
    dues_env["set_users"]([
        _member("m30", "m30@ex.com", expires_days=30),
        _member("m15", "m15@ex.com", expires_days=15),
        _member("m5",  "m5@ex.com",  expires_days=5),
        _admin("a-full", "full@ex.com", None),  # legacy full-access
        _admin("a-full2", "full2@ex.com", "full"),
        _admin("a-ops", "ops@ex.com", "operations_manager"),
        _admin("a-mem", "mem@ex.com", "membership_manager"),
        _admin("a-gov", "gov@ex.com", "governor_manager"),  # MUST be excluded
    ])
    sent = asyncio.run(ae._send_dues_reminders({
        "id": "c1", "name": "Dues reminders", "kind": "dues_reminders",
    }))
    assert sent == 3

    # Members received direct reminders (one per stage window).
    member_recipients = {e["to"] for e in dues_env["member_emails"]}
    assert member_recipients == {"m30@ex.com", "m15@ex.com", "m5@ex.com"}

    # Admin digest sent to full/full2/ops/mem — NOT the governor manager.
    admin_recipients = set()
    for payload in dues_env["admin_emails"]:
        for addr in payload.get("to", []) or []:
            admin_recipients.add(addr)
    assert admin_recipients == {"full@ex.com", "full2@ex.com", "ops@ex.com", "mem@ex.com"}
    assert "gov@ex.com" not in admin_recipients

    # Each eligible admin got exactly one digest.
    assert len(dues_env["admin_emails"]) == 4
    for payload in dues_env["admin_emails"]:
        assert "3 members to follow up on" in payload["subject"]


def test_dedupe_prevents_duplicate_sends_in_same_cycle(dues_env):
    dues_env["set_users"]([
        _member("m30-dup", "dup@ex.com", expires_days=30),
        _admin("a-full", "full@ex.com", None),
    ])
    campaign = {"id": "c2", "name": "Dues reminders", "kind": "dues_reminders"}
    n1 = asyncio.run(ae._send_dues_reminders(campaign))
    n2 = asyncio.run(ae._send_dues_reminders(campaign))
    assert n1 == 1
    assert n2 == 0
    # Only ONE member email and ONE admin digest across both cycles.
    assert len(dues_env["member_emails"]) == 1
    assert len(dues_env["admin_emails"]) == 1


def test_no_members_in_window_sends_nothing(dues_env):
    dues_env["set_users"]([
        _member("m-far", "far@ex.com", expires_days=90),  # outside all windows
        _admin("a-full", "full@ex.com", None),
    ])
    n = asyncio.run(ae._send_dues_reminders({
        "id": "c3", "name": "Dues reminders", "kind": "dues_reminders",
    }))
    assert n == 0
    assert dues_env["member_emails"] == []
    assert dues_env["admin_emails"] == []


def test_member_opt_out_skips_that_member_but_still_notifies_others(dues_env):
    dues_env["set_users"]([
        _member("m30-opt", "opt@ex.com", expires_days=30, email_opt_out=True),
        _member("m15-keep", "keep@ex.com", expires_days=15),
        _admin("a-full", "full@ex.com", None),
    ])
    n = asyncio.run(ae._send_dues_reminders({
        "id": "c4", "name": "Dues reminders", "kind": "dues_reminders",
    }))
    assert n == 1
    to_list = {e["to"] for e in dues_env["member_emails"]}
    assert to_list == {"keep@ex.com"}
    # Admin still gets a digest for the 1 opted-in member.
    assert len(dues_env["admin_emails"]) == 1
    assert "1 member to follow up on" in dues_env["admin_emails"][0]["subject"]
