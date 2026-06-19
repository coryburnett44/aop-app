"""
Iteration 53 — Admin summary email for dues-reminder auto-blast.

Validates `_send_admin_dues_summary` (server.py) in isolation by mocking
`server.db.users` and `resend_sdk.Emails.send`. We avoid touching the real
motor client to dodge the cross-event-loop issue when pytest spins up its
own loop.

Run: pytest /app/backend/tests/test_iteration53_dues_admin_summary.py -v
"""
import asyncio
import importlib
import sys
import types

import pytest


sys.path.insert(0, "/app/backend")
server = importlib.import_module("server")


class _FakeUsersCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _FakeUsersCollection:
    def __init__(self, admin_docs):
        self._admin_docs = admin_docs

    def find(self, query, projection=None):
        # The helper only ever filters by role/email/email_opt_out — return
        # whatever the test fixture seeded.
        return _FakeUsersCursor(self._admin_docs)


def _records(extra=None):
    base = [
        {
            "stage": "before_30",
            "stage_label": "30 days",
            "member_name": "Riley Chen",
            "member_email": "riley@example.com",
            "expires_at": "2026-07-15T00:00:00+00:00",
        },
        {
            "stage": "before_15",
            "stage_label": "15 days",
            "member_name": "Maya Patel",
            "member_email": "maya@example.com",
            "expires_at": "2026-06-30T00:00:00+00:00",
        },
    ]
    if extra:
        base.extend(extra)
    return base


@pytest.fixture
def fake_env(monkeypatch):
    """Stub `resend_sdk.Emails.send`, set RESEND_API_KEY, and stub `server.db`
    with a lightweight object whose `users.find(...)` returns the seeded admins."""
    sent: list[dict] = []
    monkeypatch.setattr(server.resend_sdk.Emails, "send", lambda payload: sent.append(payload) or {"id": f"id-{len(sent)}"})
    monkeypatch.setattr(server, "RESEND_API_KEY", "test-key", raising=False)

    fake_db = types.SimpleNamespace(users=_FakeUsersCollection([]))
    monkeypatch.setattr(server, "db", fake_db, raising=False)
    return {"sent": sent, "set_admins": lambda docs: setattr(fake_db, "users", _FakeUsersCollection(docs))}


def test_admin_summary_sends_one_email_per_admin(fake_env):
    fake_env["set_admins"]([
        {"id": "a1", "name": "Admin One", "email": "admin1@example.com"},
        {"id": "a2", "name": "Admin Two", "email": "admin2@example.com"},
    ])
    delivered = asyncio.run(
        server._send_admin_dues_summary({"id": "builtin_dues_reminders", "name": "Dues reminders"}, _records())
    )
    assert delivered == 2
    sent = fake_env["sent"]
    assert len(sent) == 2
    for payload in sent:
        assert "AOP dues reminders" in payload["subject"]
        assert "2 sent on" in payload["subject"]
        assert "Riley Chen" in payload["html"]
        assert "Maya Patel" in payload["html"]
        # Expiration dates rendered in a friendly format
        assert "Jul 15, 2026" in payload["html"]
        assert "Jun 30, 2026" in payload["html"]
        # Stage labels surface
        assert "30 days" in payload["html"]
        assert "15 days" in payload["html"]
        # Tags
        tag_map = {t["name"]: t["value"] for t in payload.get("tags", [])}
        assert tag_map.get("type") == "dues_admin_summary"
        assert tag_map.get("campaign_id") == "builtin_dues_reminders"


def test_admin_summary_noop_on_empty_records(fake_env):
    fake_env["set_admins"]([{"id": "a1", "name": "Admin", "email": "a@x.com"}])
    delivered = asyncio.run(
        server._send_admin_dues_summary({"id": "c", "name": "n"}, [])
    )
    assert delivered == 0
    assert fake_env["sent"] == []


def test_admin_summary_noop_when_no_admins(fake_env):
    fake_env["set_admins"]([])
    delivered = asyncio.run(
        server._send_admin_dues_summary({"id": "c", "name": "n"}, _records())
    )
    assert delivered == 0
    assert fake_env["sent"] == []


def test_admin_summary_noop_without_resend_key(fake_env, monkeypatch):
    monkeypatch.setattr(server, "RESEND_API_KEY", "", raising=False)
    fake_env["set_admins"]([{"id": "a1", "name": "Admin", "email": "a@x.com"}])
    delivered = asyncio.run(
        server._send_admin_dues_summary({"id": "c", "name": "n"}, _records())
    )
    assert delivered == 0
    assert fake_env["sent"] == []


def test_admin_summary_groups_by_stage_label(fake_env):
    fake_env["set_admins"]([{"id": "a1", "name": "Admin", "email": "a@x.com"}])
    extra = [
        {
            "stage": "before_30",
            "stage_label": "30 days",
            "member_name": "Jordan Reed",
            "member_email": "jordan@example.com",
            "expires_at": "2026-07-20T00:00:00+00:00",
        }
    ]
    delivered = asyncio.run(
        server._send_admin_dues_summary({"id": "c", "name": "Dues"}, _records(extra))
    )
    assert delivered == 1
    payload = fake_env["sent"][0]
    # Section header should reflect 2 members under "30 days"
    assert "30 days · 2 members" in payload["html"]
    # And 1 member under "15 days"
    assert "15 days · 1 member" in payload["html"]
    # All three names present
    assert "Riley Chen" in payload["html"]
    assert "Jordan Reed" in payload["html"]
    assert "Maya Patel" in payload["html"]


def test_admin_summary_escapes_html_in_member_name(fake_env):
    """Defense against a member with HTML characters in their display name."""
    fake_env["set_admins"]([{"id": "a1", "name": "Admin", "email": "a@x.com"}])
    rec = [{
        "stage": "before_30",
        "stage_label": "30 days",
        "member_name": "<script>x</script>",
        "member_email": "evil@example.com",
        "expires_at": "2026-09-01T00:00:00+00:00",
    }]
    delivered = asyncio.run(server._send_admin_dues_summary({"id": "c", "name": "n"}, rec))
    assert delivered == 1
    payload = fake_env["sent"][0]
    assert "<script>x</script>" not in payload["html"]
    assert "&lt;script&gt;" in payload["html"]
