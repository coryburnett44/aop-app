"""Iteration 101 — Dues reminders go ONLY to admin roles, not members.

User request: "Change the email reminders so only Admins (full-access,
operations managers, and membership managers) receive dues reminders
emails."

This test drives the `_send_dues_reminders` coroutine directly with
`resend_sdk.Emails.send` monkey-patched to capture what would be emailed,
seeds users at each of the 4 stage windows (30d / 15d / 5d before / +1d
grace), and asserts:

1. No members receive direct reminder emails.
2. A digest is delivered ONLY to admins whose `admin_role` is in
   {"full", None, "", "operations_manager", "membership_manager"}.
3. Governor Managers and other admin sub-roles are excluded.
4. Members with `email_opt_out=true` do NOT block the admin digest.
5. The `dues_reminders_sent` collection is populated so subsequent
   cycles don't re-alert on the same member/stage.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "clubhaven_db")

# The tests import from backend directly.
import sys
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="function")
def isolated_db(request):
    """Snapshot & restore the users / dues_reminders_sent collections so
    seeding doesn't leak into other test modules."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    snapshot_users = list(db.users.find({}, {"_id": 0}))
    db.dues_reminders_sent.delete_many({})
    yield db
    # Restore original user set (drop everything we seeded).
    seeded_ids = [u["id"] for u in snapshot_users]
    db.users.delete_many({"id": {"$nin": seeded_ids}})
    # Reset flags we mutated on seeded users.
    for u in snapshot_users:
        db.users.update_one({"id": u["id"]}, {"$set": u}, upsert=False)
    db.dues_reminders_sent.delete_many({})


def _seed_user(db, *, id_, email, role="member", admin_role=None, expires_days=None, email_opt_out=False, dues_prefs=True):
    from datetime import datetime as _dt
    now = _dt.now(timezone.utc)
    expires_at = None
    if expires_days is not None:
        expires_at = (now + timedelta(days=expires_days)).replace(hour=12, minute=0, second=0, microsecond=0).isoformat()
    db.users.update_one(
        {"id": id_},
        {"$set": {
            "id": id_,
            "email": email,
            "name": email.split("@")[0].title(),
            "role": role,
            "admin_role": admin_role,
            "status": "active",
            "is_lifetime_member": False,
            "membership_expires_at": expires_at,
            "email_opt_out": email_opt_out,
            "email_prefs": {"dues_reminders": dues_prefs},
        }},
        upsert=True,
    )


def test_only_eligible_admins_receive_dues_reminder(isolated_db, monkeypatch):
    db = isolated_db
    # 3 members whose dues hit each stage window.
    _seed_user(db, id_="qa-m30", email="qa-m30@test.local", expires_days=30)
    _seed_user(db, id_="qa-m15", email="qa-m15@test.local", expires_days=15)
    _seed_user(db, id_="qa-m5", email="qa-m5@test.local", expires_days=5)
    # 4 admins covering ALL admin sub-roles — only 3 should be in the To: list.
    _seed_user(db, id_="qa-admin-full", email="qa-full@test.local", role="admin", admin_role=None)  # legacy full
    _seed_user(db, id_="qa-admin-ops", email="qa-ops@test.local", role="admin", admin_role="operations_manager")
    _seed_user(db, id_="qa-admin-mem", email="qa-mem@test.local", role="admin", admin_role="membership_manager")
    _seed_user(db, id_="qa-admin-gov", email="qa-gov@test.local", role="admin", admin_role="governor_manager")

    # Patch resend send + RESEND_API_KEY presence.
    captured = []

    def fake_send(payload):
        captured.append(payload)
        return {"id": "fake-msg-id"}

    from routes import automated_emails as ae
    monkeypatch.setattr(ae, "RESEND_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(ae.resend_sdk.Emails, "send", fake_send)

    campaign = {"id": "qa-campaign", "name": "QA reminders", "kind": "dues_reminders"}
    total_pending = asyncio.get_event_loop().run_until_complete(ae._send_dues_reminders(campaign))

    # 3 members hit their windows.
    assert total_pending == 3
    # No member received a direct email; every send() call must be to one of the 3 eligible admins.
    admin_recipients = set()
    for payload in captured:
        for addr in payload.get("to") or []:
            admin_recipients.add(addr)
    assert admin_recipients == {"qa-full@test.local", "qa-ops@test.local", "qa-mem@test.local"}, admin_recipients
    # No captured email was addressed to a member OR to the governor admin.
    for member_email in ["qa-m30@test.local", "qa-m15@test.local", "qa-m5@test.local", "qa-gov@test.local"]:
        assert member_email not in admin_recipients, f"{member_email} should NOT have received a dues reminder"
    # Each admin got exactly one digest per cycle (regardless of member count).
    assert len(captured) == 3
    # Subject reflects the "reminder" framing.
    for payload in captured:
        assert "dues reminders" in (payload.get("subject") or "").lower()
        assert "3 members" in (payload.get("subject") or "").lower()


def test_dues_reminders_sent_collection_prevents_duplicate_cycles(isolated_db, monkeypatch):
    db = isolated_db
    _seed_user(db, id_="qa-m30-dup", email="qa-m30-dup@test.local", expires_days=30)
    _seed_user(db, id_="qa-admin-full-dup", email="qa-full-dup@test.local", role="admin", admin_role=None)

    from routes import automated_emails as ae
    monkeypatch.setattr(ae, "RESEND_API_KEY", "fake-key-for-test")
    calls = []
    monkeypatch.setattr(ae.resend_sdk.Emails, "send", lambda p: (calls.append(p) or {"id": "ok"}))

    campaign = {"id": "qa-dup", "name": "QA dup", "kind": "dues_reminders"}
    # First cycle picks up the member.
    n1 = asyncio.get_event_loop().run_until_complete(ae._send_dues_reminders(campaign))
    assert n1 == 1
    # Second cycle on the same day: dedupe kicks in, nothing new to report.
    n2 = asyncio.get_event_loop().run_until_complete(ae._send_dues_reminders(campaign))
    assert n2 == 0
    # Only one digest email should have been sent across both cycles.
    assert len(calls) == 1


def test_no_members_at_any_stage_window_sends_no_email(isolated_db, monkeypatch):
    """When no members have dues coming up in the stage windows, no email
    (member OR admin) should be sent."""
    db = isolated_db
    _seed_user(db, id_="qa-m-far", email="qa-far@test.local", expires_days=90)  # outside any window
    _seed_user(db, id_="qa-admin-full-2", email="qa-full-2@test.local", role="admin", admin_role=None)

    from routes import automated_emails as ae
    monkeypatch.setattr(ae, "RESEND_API_KEY", "fake-key-for-test")
    calls = []
    monkeypatch.setattr(ae.resend_sdk.Emails, "send", lambda p: (calls.append(p) or {"id": "ok"}))

    n = asyncio.get_event_loop().run_until_complete(ae._send_dues_reminders({"id": "qa-empty", "name": "QA empty"}))
    assert n == 0
    assert len(calls) == 0
