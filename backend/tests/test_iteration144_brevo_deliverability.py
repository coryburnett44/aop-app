"""Iter 144 — Deliverability tab reflects Brevo (the actual sender),
not Resend. Also live DNS-check endpoint.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"


def _login() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "admin@clubhaven.app", "password": "Admin123!"}, timeout=15)
    assert r.status_code == 200
    return s


def test_deliverability_reports_brevo_provider():
    admin = _login()
    r = admin.get(f"{BASE}/email/deliverability", timeout=10).json()
    assert r["provider"] == "brevo"
    assert r["provider_label"] == "Brevo"


def test_deliverability_checklist_contains_brevo_values_not_resend():
    admin = _login()
    r = admin.get(f"{BASE}/email/deliverability", timeout=10).json()
    checklist = r["dns_checklist"]
    all_values = " ".join(str(row.get("value", "")).lower() + " " + str(row.get("host", "")).lower() for row in checklist)
    assert "spf.brevo.com" in all_values, "SPF row must reference spf.brevo.com"
    assert "brevo" in all_values.lower(), "checklist must reference Brevo"
    assert "resend" not in all_values.lower(), "checklist must NOT still reference Resend"
    assert "bounces.brevo.com" in all_values, "must include Return-Path/bounces CNAME row"
    # DKIM row must point at mail._domainkey (Brevo default), not resend._domainkey.
    dkim_hosts = " ".join(row.get("host", "").lower() for row in checklist if "dkim" in str(row.get("record", "")).lower())
    assert "mail._domainkey" in dkim_hosts
    assert "resend._domainkey" not in dkim_hosts


def test_dns_check_endpoint_returns_records_with_pass_fail():
    admin = _login()
    r = admin.get(f"{BASE}/email/deliverability/check-dns", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    # Domain resolves — should have at least SPF/DKIM/DMARC records reported.
    if data.get("records"):
        names = {rec.get("name") for rec in data["records"]}
        assert "SPF" in names
        assert "DKIM" in names
        assert "DMARC" in names
    # `all_pass` is a boolean.
    if "all_pass" in data:
        assert isinstance(data["all_pass"], bool)


def test_dns_check_requires_admin():
    anon = requests.Session()
    r = anon.get(f"{BASE}/email/deliverability/check-dns", timeout=10)
    assert r.status_code == 401
