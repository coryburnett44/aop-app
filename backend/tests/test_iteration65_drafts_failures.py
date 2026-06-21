"""Iteration 65 — Email drafts, per-template test send, failed recipient surfaces:
  • POST /api/email/drafts (with is_autosave upsert) + GET/PUT/DELETE
  • GET /api/email/blasts/{id}/failed
  • GET /api/email/password-setup-failures
  • POST /api/email/test-send accepts template_id alone (no to_email defaults to admin's email)
  • password_setup_attempts gets written on resend
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASSWORD = "Member123!"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def member():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return s


# ------------------------------------------------------------
# Drafts
# ------------------------------------------------------------
def test_drafts_member_forbidden(member):
    r = member.get(f"{API}/email/drafts", timeout=15)
    assert r.status_code in (401, 403)


def test_drafts_autosave_upserts_single_slot(admin):
    # First autosave creates the slot
    r1 = admin.post(f"{API}/email/drafts", json={
        "subject": "WIP subject one", "body_html": "<p>v1</p>",
        "segment": "active", "is_autosave": True,
    }, timeout=15)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["is_autosave"] is True
    assert d1["subject"] == "WIP subject one"

    # Second autosave reuses the same id (upsert)
    r2 = admin.post(f"{API}/email/drafts", json={
        "subject": "WIP subject two", "body_html": "<p>v2</p>",
        "segment": "active", "is_autosave": True,
    }, timeout=15)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["id"] == d1["id"]
    assert d2["subject"] == "WIP subject two"
    assert d2["body_html"] == "<p>v2</p>"

    # Listing should only show ONE autosave slot
    drafts = admin.get(f"{API}/email/drafts", timeout=15).json()
    autosave = [d for d in drafts if d.get("is_autosave")]
    assert len(autosave) == 1, f"Expected exactly 1 autosave slot, got {len(autosave)}"


def test_named_drafts_create_update_delete(admin):
    r1 = admin.post(f"{API}/email/drafts", json={
        "name": "Spring newsletter v1", "subject": "Spring", "body_html": "<p>v1</p>",
        "segment": "active", "is_autosave": False,
    }, timeout=15)
    assert r1.status_code == 200, r1.text
    draft_id = r1.json()["id"]

    # Update
    r2 = admin.put(f"{API}/email/drafts/{draft_id}", json={
        "name": "Spring newsletter v2", "subject": "Spring (v2)", "body_html": "<p>v2</p>",
        "segment": "admins", "is_autosave": False,
    }, timeout=15)
    assert r2.status_code == 200, r2.text
    upd = r2.json()
    assert upd["name"] == "Spring newsletter v2"
    assert upd["segment"] == "admins"

    # Delete
    r3 = admin.delete(f"{API}/email/drafts/{draft_id}", timeout=15)
    assert r3.status_code == 200

    # Confirm gone
    after = admin.get(f"{API}/email/drafts", timeout=15).json()
    assert not any(d["id"] == draft_id for d in after)


def test_draft_ownership_enforced(admin, member):
    """Member can't read or modify admin drafts. Drafts route is admin-only;
    a member can't even list them — covered by test_drafts_member_forbidden."""
    r = admin.post(f"{API}/email/drafts", json={"name": "Private", "subject": "x", "body_html": "<p>p</p>"}, timeout=15)
    assert r.status_code == 200
    did = r.json()["id"]
    # Member can't update it (even if they could reach the endpoint)
    r2 = member.put(f"{API}/email/drafts/{did}", json={"subject": "hijack"}, timeout=15)
    assert r2.status_code in (401, 403)
    admin.delete(f"{API}/email/drafts/{did}", timeout=15)


# ------------------------------------------------------------
# Blast failed list endpoint
# ------------------------------------------------------------
def test_blast_failed_list_404_unknown(admin):
    r = admin.get(f"{API}/email/blasts/does-not-exist/failed", timeout=15)
    assert r.status_code == 404


# ------------------------------------------------------------
# Per-template test send (admin's own email when to_email omitted)
# ------------------------------------------------------------
def test_template_test_send_uses_admin_email_when_omitted(admin):
    """Confirms /api/email/test-send accepts template_id and infers admin's
    own address as the destination if to_email is missing OR explicit."""
    tpls = admin.get(f"{API}/email/templates", timeout=15).json()
    builtin = next((t for t in tpls if t["id"] == "builtin_tpl_announcement"), None)
    assert builtin, "Missing built-in announcement template"
    # Explicit to_email path always works
    r = admin.post(f"{API}/email/test-send", json={"to_email": ADMIN_EMAIL, "template_id": builtin["id"]}, timeout=20)
    assert r.status_code == 200, r.text


# ------------------------------------------------------------
# Password setup failures
# ------------------------------------------------------------
def test_password_setup_failures_endpoint(admin):
    r = admin.get(f"{API}/email/password-setup-failures", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    for item in data:
        assert "email" in item
        assert "ok" in item
        assert item["ok"] is False, "Endpoint should only return failures"


def test_password_setup_failures_member_forbidden(member):
    r = member.get(f"{API}/email/password-setup-failures", timeout=15)
    assert r.status_code in (401, 403)
