"""Iteration 88 — Modularization smoke for the new routes/automated_emails.py.

The dues-reminder cadence, broadcast renderer, and admin dues-summary digest
were extracted from server.py into routes/automated_emails.py in this iteration.

This test ensures:
  - the new module is importable and exports the expected helpers
  - server.py no longer carries the extracted helpers
  - all admin endpoints are still served (200/401 status checks)
"""
import os
import sys
import importlib

import pytest
import requests


sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/")

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


def test_routes_automated_emails_exposes_helpers():
    ae = importlib.import_module("routes.automated_emails")
    # Constants
    assert ae.AUTOMATED_SECTIONS, "AUTOMATED_SECTIONS must be exported"
    assert len(ae.DUES_REMINDER_STAGES) == 4
    assert set(ae.DUES_REMINDER_DEFAULT_TEMPLATES.keys()) == {
        "before_30", "before_15", "before_5", "grace_1",
    }
    # Helpers
    for name in [
        "_send_admin_dues_summary",
        "_send_dues_reminders",
        "_send_automated_email",
        "_render_automated_body",
        "_render_subject",
        "_audience_recipients",
        "_dues_reminder_email_html",
        "_apply_dues_placeholders",
        "_next_cron_run",
        "_automated_email_out",
        "_automated_email_loop",
        "seed_builtin_automated_emails",
        "seed_builtin_dues_reminders",
    ]:
        assert hasattr(ae, name), f"routes.automated_emails missing {name}"


def test_server_py_no_longer_owns_automated_email_helpers():
    """Sanity check that the helpers were truly extracted and the original
    definitions no longer exist in server.py — guards against accidental
    duplication via merge conflict."""
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    # Helper definitions should be gone (only the import + call sites stay)
    forbidden = [
        "async def _send_admin_dues_summary(",
        "async def _send_dues_reminders(",
        "async def _send_automated_email(",
        "async def _render_automated_body(",
        "def _apply_dues_placeholders(",
        "def _dues_reminder_email_html(",
        "DUES_REMINDER_STAGES = [",
        "DUES_REMINDER_DEFAULT_TEMPLATES = {",
        "MERGE_TAGS = [",
        "class AutomatedEmailIn(BaseModel):",
    ]
    for token in forbidden:
        assert token not in src, f"server.py still owns extracted symbol: {token!r}"


def test_endpoints_still_served(admin_session):
    """The admin endpoints must remain mounted on /api after the extraction."""
    r1 = admin_session.get(f"{BASE_URL}/api/automated-emails", timeout=15)
    assert r1.status_code == 200
    campaigns = r1.json()
    assert isinstance(campaigns, list)
    kinds = {c.get("kind") or "broadcast" for c in campaigns}
    assert {"broadcast", "dues_reminders"}.issubset(kinds), (
        f"expected both built-in kinds, got {kinds}"
    )

    r2 = admin_session.get(f"{BASE_URL}/api/automated-emails/merge-tags", timeout=15)
    assert r2.status_code == 200
    body = r2.json()
    assert "tags" in body and "sections" in body
    assert len(body["sections"]) == 7

    r3 = admin_session.get(f"{BASE_URL}/api/automated-emails/dues-reminder-defaults", timeout=15)
    assert r3.status_code == 200
    body = r3.json()
    assert len(body["stages"]) == 4
    assert len(body["placeholders"]) == 7


def test_preview_endpoint_renders_both_kinds(admin_session):
    """Broadcast campaigns render via merge tags. Dues-reminder campaigns
    render a stacked preview of all four stages."""
    # Broadcast (built-in weekly digest)
    rb = admin_session.post(
        f"{BASE_URL}/api/automated-emails/builtin_weekly_digest/preview", timeout=15,
    )
    assert rb.status_code == 200, rb.text
    body_b = rb.json()
    assert "subject" in body_b and "body_html" in body_b
    assert "Your AOP weekly digest" in body_b["subject"]
    assert len(body_b["body_html"]) > 500

    # Dues-reminder built-in
    rd = admin_session.post(
        f"{BASE_URL}/api/automated-emails/builtin_dues_reminders/preview", timeout=15,
    )
    assert rd.status_code == 200, rd.text
    body_d = rd.json()
    assert "preview of all four stages" in body_d["subject"]
    # All four stage labels must appear in the stacked preview body
    for label in ["30 days", "15 days", "5 days", "Grace period"]:
        assert label in body_d["body_html"], f"missing stage label {label!r} in dues preview"


def test_unauthenticated_endpoints_blocked():
    r = requests.get(f"{BASE_URL}/api/automated-emails", timeout=15)
    assert r.status_code == 401
    r = requests.get(f"{BASE_URL}/api/automated-emails/merge-tags", timeout=15)
    assert r.status_code == 401
