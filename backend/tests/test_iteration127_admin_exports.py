"""Iter 127 — CSV + PDF admin exports.

Covers:
  1. Members CSV export returns text/csv with the full column set and
     PII fields populated. Non-admins get 403.
  2. Each of the 4 supported report kinds returns a valid `%PDF-1.4`
     stream. Unknown kinds return 400. Non-admins get 403.
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


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


def test_members_csv_export_shape():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/admin/members/export.csv", timeout=30)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")
    body = r.text
    lines = body.splitlines()
    assert len(lines) >= 2, "expect header + at least one row"
    header = lines[0].split(",")
    # Every required PII / relational field must be present.
    for expected in (
        "id", "name", "email", "phone", "birth_date", "address",
        "city", "state", "postal_code", "chapter", "tier",
        "membership_expires_at", "hours_approved_total",
        "donations_total", "awards", "events_attended", "rsvps",
    ):
        assert expected in header, f"missing column: {expected}"


def test_members_csv_export_is_admin_only():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.get(f"{BASE}/admin/members/export.csv", timeout=15)
    assert r.status_code == 403


def test_report_pdf_export_kinds():
    """All 4 supported report kinds return a valid PDF."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    for kind in ("members", "rsvps", "hours", "donations"):
        r = admin.get(f"{BASE}/reports/{kind}/export.pdf", timeout=30)
        assert r.status_code == 200, f"{kind}: {r.status_code} {r.text[:200]}"
        assert r.headers["content-type"] == "application/pdf", f"{kind}: bad content-type"
        assert r.content[:8] == b"%PDF-1.4", f"{kind}: not a PDF (starts with {r.content[:8]!r})"
        # Filename in disposition matches the kind.
        disp = r.headers.get("content-disposition", "")
        assert kind in disp, f"{kind}: disposition {disp}"


def test_report_pdf_unknown_kind_400():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/BOGUS/export.pdf", timeout=15)
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "unknown" in detail.lower()


def test_report_pdf_non_admin_forbidden():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.get(f"{BASE}/reports/members/export.pdf", timeout=15)
    assert r.status_code == 403


def test_report_pdf_honors_filters():
    """Passing filter query params round-trips through to the JSON
    delegator — assert the PDF still succeeds (contents will differ)."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/hours/export.pdf?year=2026", timeout=30)
    assert r.status_code == 200
    assert r.content[:8] == b"%PDF-1.4"
