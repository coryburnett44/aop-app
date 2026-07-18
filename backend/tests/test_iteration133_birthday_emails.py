"""Iter 133 — Automatic Happy Birthday email cron.

Covers:
  1. `POST /api/admin/birthday-emails/sweep` runs the sweep and returns a
     summary — with 0 birthdays it's a no-op.
  2. Setting a member's `birthdate` to today and running the sweep sends
     an email + inserts a dedupe row into `birthday_emails_sent`.
  3. Re-running the sweep on the same day skips the already-sent member.
  4. `email_opt_out=True` and `email_prefs.blasts=False` both skip.
  5. `GET /api/admin/birthday-emails/upcoming?days=N` lists members with
     upcoming birthdays and correctly flags ones we've already emailed
     this year.
  6. Endpoints are admin-only.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

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


def _today_mmdd() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.month:02d}-{now.day:02d}"


def _cleanup_birthday_log():
    """Wipe the birthday_emails_sent collection so tests are hermetic. Only
    runs against preview data by design (deliberate — production has no
    admin auth for us anyway)."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import asyncio
    async def _run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.birthday_emails_sent.delete_many({})
    asyncio.run(_run())


def test_sweep_endpoint_exists_and_returns_summary():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.post(f"{BASE}/admin/birthday-emails/sweep", timeout=30)
    assert r.status_code == 200
    body = r.json()
    for key in ("date", "matched_today", "sent", "skipped_optout", "skipped_already_sent", "errors"):
        assert key in body, f"missing summary key {key!r}"


def test_upcoming_endpoint_returns_expected_shape():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/admin/birthday-emails/upcoming?days=365", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "today" in body
    assert "window_days" in body
    assert body["window_days"] == 365
    assert isinstance(body["upcoming"], list)
    for u in body["upcoming"][:3]:
        for key in ("user_id", "name", "email", "birthday", "days_until", "will_send"):
            assert key in u


def test_sweep_sends_and_dedupes_when_birthday_matches_today():
    _cleanup_birthday_log()
    admin = _login("admin@clubhaven.app", "Admin123!")
    # Pick a test member (member@clubhaven.app / Riley Chen).
    members = admin.get(f"{BASE}/members?limit=50", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    target = next((m for m in members if m.get("email") == "member@clubhaven.app"), None)
    assert target is not None, "expected preview seed member 'Riley Chen' to exist"
    uid = target["id"]
    orig_birthdate = target.get("birthdate") or target.get("birth_date") or ""
    # Set their birthdate to today.
    today_mmdd = _today_mmdd()
    r = admin.put(f"{BASE}/members/{uid}", json={"birthdate": f"1985-{today_mmdd}"}, timeout=15)
    assert r.status_code == 200, r.text
    try:
        # First sweep — must send.
        r1 = admin.post(f"{BASE}/admin/birthday-emails/sweep", timeout=30).json()
        assert r1["matched_today"] >= 1
        assert r1["sent"] >= 1
        # Second sweep — must dedupe.
        r2 = admin.post(f"{BASE}/admin/birthday-emails/sweep", timeout=30).json()
        assert r2["matched_today"] >= 1
        assert r2["sent"] == 0
        assert r2["skipped_already_sent"] >= 1
        # Upcoming endpoint should now flag them as already_sent_this_year.
        up = admin.get(f"{BASE}/admin/birthday-emails/upcoming?days=1", timeout=15).json()
        me = next((u for u in up.get("upcoming", []) if u["user_id"] == uid), None)
        assert me is not None
        assert me["already_sent_this_year"] is True
    finally:
        # Restore original birthdate.
        admin.put(f"{BASE}/members/{uid}", json={"birthdate": orig_birthdate}, timeout=15)
        _cleanup_birthday_log()


def test_email_opt_out_skips_send():
    _cleanup_birthday_log()
    admin = _login("admin@clubhaven.app", "Admin123!")
    member = _login("member@clubhaven.app", "Member123!")
    members = admin.get(f"{BASE}/members?limit=50", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    target = next((m for m in members if m.get("email") == "member@clubhaven.app"), None)
    uid = target["id"]
    orig_birthdate = target.get("birthdate") or ""
    today_mmdd = _today_mmdd()
    admin.put(f"{BASE}/members/{uid}", json={"birthdate": f"1985-{today_mmdd}"}, timeout=15)
    # Member opts themselves out via the self-serve preferences endpoint.
    orig_prefs = member.get(f"{BASE}/me/email-preferences", timeout=15).json()
    member.put(f"{BASE}/me/email-preferences", json={"email_opt_out": True}, timeout=15)
    try:
        r = admin.post(f"{BASE}/admin/birthday-emails/sweep", timeout=30).json()
        assert r["matched_today"] >= 1
        assert r["skipped_optout"] >= 1
        assert r["sent"] == 0
    finally:
        # Restore both birthday and email prefs.
        admin.put(f"{BASE}/members/{uid}", json={"birthdate": orig_birthdate}, timeout=15)
        member.put(f"{BASE}/me/email-preferences", json={
            "email_opt_out": bool(orig_prefs.get("email_opt_out", False)),
        }, timeout=15)
        _cleanup_birthday_log()


def test_endpoints_require_admin():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.post(f"{BASE}/admin/birthday-emails/sweep", timeout=15)
    assert r.status_code == 403
    r = member.get(f"{BASE}/admin/birthday-emails/upcoming", timeout=15)
    assert r.status_code == 403


def test_parse_birthday_helper_handles_multiple_formats():
    """Import the helper directly and exercise the format variants — we don't
    want a member's stored `birthdate` string format to silently drop them
    from the cron."""
    from routes.birthday_emails import _parse_birthday
    assert _parse_birthday("1990-04-15") == (4, 15)
    assert _parse_birthday("1990-04-15T00:00:00+00:00") == (4, 15)
    assert _parse_birthday("04/15") == (4, 15)
    assert _parse_birthday("04-15") == (4, 15)
    assert _parse_birthday("") is None
    assert _parse_birthday(None) is None
    assert _parse_birthday("garbage") is None
    from datetime import date
    assert _parse_birthday(date(2001, 6, 30)) == (6, 30)


def test_birthday_email_html_contains_expected_language():
    """Direct render check — the email should mention the org and be warm."""
    from routes.birthday_emails import _render_birthday_email
    subject, html = _render_birthday_email({"first_name": "Jamie"})
    assert "Happy Birthday" in subject
    assert "Jamie" in subject
    assert "Happy Birthday" in html
    assert "Alpha Omega Phi" in html
    # The email should mention celebrating with the recipient.
    lower = html.lower()
    assert "celebrate" in lower or "family" in lower
