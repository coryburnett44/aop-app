"""Iteration 145 — Ensure the app is Brevo-only.

Removes any lingering Resend brand text and validates:
  - `/api/email/test-send` returns "Test email accepted by Brevo." (message_id
    ends in `@smtp-relay.mailin.fr` proving Brevo is the transport).
  - `/api/email/deliverability` reports provider_label == "Brevo" and the
    DNS checklist references `spf.brevo.com` (not `_spf.resend.com`).
  - Frontend Admin.jsx has no user-facing "Resend accepted"/"Resend rejected"
    strings.
  - backend/.env no longer contains RESEND_API_KEY or RESEND_FROM.
"""

import os
import re
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "https://club-express-lite.preview.emergentagent.com"
API = BASE.rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@clubhaven.app")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")


def _login():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=10)
    r.raise_for_status()
    j = r.json()
    return j.get("access_token") or j.get("token")


def test_test_send_uses_brevo():
    token = _login()
    r = requests.post(
        f"{API}/email/test-send",
        headers={"Authorization": f"Bearer {token}"},
        json={"to_email": "delivery-check@example.com"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("ok") is True
    assert "Brevo" in j.get("detail", "")
    # Brevo message ids come from smtp-relay.mailin.fr — proves the transport
    mid = j.get("message_id", "")
    assert "mailin.fr" in mid, f"message_id should be a Brevo id, got {mid!r}"


def test_deliverability_is_brevo():
    token = _login()
    r = requests.get(f"{API}/email/deliverability", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j.get("provider_label") == "Brevo"
    # No resend.com references in the DNS checklist
    text = str(j.get("dns_checklist", []))
    assert "_spf.resend.com" not in text
    assert "resend._domainkey" not in text
    assert "spf.brevo.com" in text


def test_admin_jsx_no_resend_brand_labels():
    path = "/app/frontend/src/pages/Admin.jsx"
    with open(path) as f:
        src = f.read()
    # The offending user-visible strings from the prior version.
    forbidden = [
        "Resend accepted the test",
        "Resend rejected the test",
        "accepted by Resend",
        "Resend rejected:",
        "Validate that Resend",
        "Check Resend domain config",
        "Check Resend logs",
    ]
    for s in forbidden:
        assert s not in src, f"Admin.jsx still contains {s!r}"


def test_env_has_no_resend_vars():
    path = "/app/backend/.env"
    with open(path) as f:
        env = f.read()
    assert "RESEND_API_KEY" not in env
    assert "RESEND_FROM" not in env
    assert 'BREVO_API_KEY="' in env
