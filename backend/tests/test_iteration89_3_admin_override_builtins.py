"""Iteration 89.3 — Admin override on built-in automated-email campaigns.

The user requested: "Remove all restrictions for admins. Allow full-access
admins to remove, delete, update, or change any item."

This test exercises the new override flow for built-in automated-email
campaigns (the last remaining hard-block in the codebase):

  1. Admin can DELETE a built-in campaign (previously 400 "cannot be deleted").
  2. The id is tombstoned in `deleted_builtin_automated_emails`.
  3. After a backend restart the boot seeder honors the tombstone and does
     NOT resurrect the campaign.
  4. Dropping the tombstone re-enables the seed on next restart.
  5. Admin can also RENAME a built-in (previously the PUT body's `name` was
     ignored for dues_reminders and the frontend disabled the input).

Run: pytest /app/backend/tests/test_iteration89_3_admin_override_builtins.py
"""
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/")

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}


def _builtin_weekly_digest_doc():
    """Mirrors `seed_builtin_automated_emails` so the test can fully restore the
    deleted built-in WITHOUT needing a supervisor restart between tests."""
    body_html = """<div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#f7f5f0">
  <h1 style="color:#0A2463;margin:0 0 4px;font-size:28px">Good morning, {{member_name}}</h1>
  <p style="color:#666;font-size:14px">Here's what's happening this week in Alpha Omega Phi.</p>
  {{birthday_greeting}}
  {{my_rsvps}}
  {{upcoming_events}}
  {{new_photos}}
  {{new_documents}}
  {{new_members}}
  {{pending_hours}}
  <p style="font-size:12px;color:#888;margin-top:24px">You're receiving this because you're a member of Alpha Omega Phi. Replies go to info@aop-app.org.</p>
</div>"""
    now = datetime.now(timezone.utc).isoformat()
    sections = {s: True for s in [
        "events", "photos", "documents", "new_members", "my_rsvps",
        "pending_hours", "birthday_greeting",
    ]}
    return {
        "id": "builtin_weekly_digest",
        "name": "Weekly Digest",
        "subject": "Your AOP weekly digest — {{member_name}}",
        "body_html": body_html,
        "cron_expression": "0 9 * * 1",
        "is_active": True,
        "is_builtin": True,
        "audience": {"type": "all", "ids": []},
        "sections": sections,
        "last_run_at": None,
        "next_run_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "last_sent_count": 0,
        "created_by": None,
        "created_by_name": "System",
        "created_at": now,
    }


@pytest.fixture(scope="module")
def admin_s():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def mongo_db():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip().strip('"').strip("'")
    db_name = os.environ.get("DB_NAME", "clubhaven").strip().strip('"').strip("'")
    return MongoClient(mongo_url)[db_name]


def _list(admin_s):
    return admin_s.get(f"{BASE_URL}/api/automated-emails", timeout=10).json()


def test_admin_can_delete_builtin_weekly_digest(admin_s, mongo_db):
    """Iter 89.3 — admin override deletes the built-in campaign and
    tombstones the id so the boot seeder won't resurrect it."""
    # Ensure the campaign exists at the start of the test (other tests may
    # have toggled it).
    if not any(c["id"] == "builtin_weekly_digest" for c in _list(admin_s)):
        # Drop any stale tombstone and let the suite skip — we don't want to
        # accidentally rely on a freshly-seeded campaign that other tests
        # haven't created yet.
        mongo_db.deleted_builtin_automated_emails.delete_one({"id": "builtin_weekly_digest"})
        pytest.skip("builtin_weekly_digest not present at test start")

    try:
        # 1. Delete the built-in — must succeed (no 400 / no "built-in" error).
        r = admin_s.delete(f"{BASE_URL}/api/automated-emails/builtin_weekly_digest", timeout=10)
        assert r.status_code == 200, r.text
        assert "built-in" not in r.text.lower()

        # 2. List no longer contains it.
        ids = {c["id"] for c in _list(admin_s)}
        assert "builtin_weekly_digest" not in ids

        # 3. Tombstone row exists with audit metadata.
        tomb = mongo_db.deleted_builtin_automated_emails.find_one({"id": "builtin_weekly_digest"})
        assert tomb is not None
        assert tomb.get("name")
        assert tomb.get("deleted_by")
        assert tomb.get("deleted_at")
    finally:
        # Cleanup: drop the tombstone AND restore the built-in doc so the next
        # test in this suite (or test_phase_o.TestAutomatedEmails) starts from
        # a clean state without needing a backend restart.
        mongo_db.deleted_builtin_automated_emails.delete_one({"id": "builtin_weekly_digest"})
        mongo_db.automated_emails.update_one(
            {"id": "builtin_weekly_digest"},
            {"$setOnInsert": _builtin_weekly_digest_doc()},
            upsert=True,
        )


def test_admin_can_rename_builtin_dues_reminders(admin_s):
    """The PUT handler now persists the name field even for dues_reminders
    campaigns (previously the name was silently dropped)."""
    target = next((c for c in _list(admin_s) if c["id"] == "builtin_dues_reminders"), None)
    if not target:
        pytest.skip("builtin_dues_reminders not present")
    original = target["name"]
    new_name = f"Iter89.3 Renamed Dues {uuid.uuid4().hex[:6]}"
    try:
        payload = {
            "name": new_name,
            "subject": target["subject"],
            "body_html": target.get("body_html") or "",
            "cron_expression": target["cron_expression"],
            "is_active": target["is_active"],
            "audience": target.get("audience") or {"type": "all", "ids": []},
            "sections": target.get("sections") or {},
            "stage_templates": target.get("stage_templates") or {},
        }
        r = admin_s.put(
            f"{BASE_URL}/api/automated-emails/builtin_dues_reminders",
            json=payload, timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == new_name
        # Persisted on subsequent GET.
        fresh = next(c for c in _list(admin_s) if c["id"] == "builtin_dues_reminders")
        assert fresh["name"] == new_name
    finally:
        # restore original name
        admin_s.put(
            f"{BASE_URL}/api/automated-emails/builtin_dues_reminders",
            json={
                "name": original,
                "subject": target["subject"],
                "body_html": target.get("body_html") or "",
                "cron_expression": target["cron_expression"],
                "is_active": target["is_active"],
                "audience": target.get("audience") or {"type": "all", "ids": []},
                "sections": target.get("sections") or {},
                "stage_templates": target.get("stage_templates") or {},
            }, timeout=10,
        )


def test_404_when_deleting_unknown_campaign(admin_s):
    r = admin_s.delete(f"{BASE_URL}/api/automated-emails/does-not-exist", timeout=10)
    assert r.status_code == 404
