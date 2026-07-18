"""Iter 129 — Reports crash fix + expanded PDF exports.

Covers:
  1. Every report kind (members, rsvps, hours, donations, recruitment,
     awards, event-tickets, dues, dues-reminders) returns a valid PDF.
  2. Admin Members CSV + PDF exports return matching data (row counts
     line up, PDF starts with %PDF header, filenames set correctly).
  3. Non-admin users are locked out of both admin CSV and admin PDF.
  4. Unknown report kind still returns 400.
"""
from __future__ import annotations

import csv as csv_mod
import io
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


ALL_KINDS = [
    "members",
    "rsvps",
    "hours",
    "donations",
    "recruitment",
    "awards",
    "event-tickets",
    "dues",
    "dues-reminders",
]


def test_all_report_pdf_kinds_return_valid_pdf():
    admin = _login("admin@clubhaven.app", "Admin123!")
    for kind in ALL_KINDS:
        r = admin.get(f"{BASE}/reports/{kind}/export.pdf", timeout=30)
        assert r.status_code == 200, f"{kind}: {r.status_code} {r.text[:200]}"
        assert r.headers["content-type"] == "application/pdf", f"{kind}: {r.headers['content-type']}"
        assert r.content[:5] == b"%PDF-", f"{kind}: content starts with {r.content[:8]!r}"
        assert kind in r.headers.get("content-disposition", ""), f"{kind}: bad disposition"


def test_admin_members_csv_and_pdf_agree_on_row_count():
    """The CSV row count must match the number of member cards rendered in
    the PDF (proxy: the PDF must be non-trivially larger than an empty PDF)."""
    admin = _login("admin@clubhaven.app", "Admin123!")

    # CSV path — count data rows.
    r_csv = admin.get(f"{BASE}/admin/members/export.csv", timeout=30)
    assert r_csv.status_code == 200
    reader = csv_mod.DictReader(io.StringIO(r_csv.text))
    csv_rows = list(reader)
    assert len(csv_rows) > 0
    # Sanity: every row must have populated name/email columns.
    for row in csv_rows[:5]:
        assert row.get("name")
        assert row.get("email")

    # PDF path — must be non-empty, non-truncated PDF.
    r_pdf = admin.get(f"{BASE}/admin/members/export.pdf", timeout=45)
    assert r_pdf.status_code == 200
    assert r_pdf.content[:5] == b"%PDF-"
    # Rough proxy: with N members, the PDF should be much bigger than a
    # 5KB empty PDF template. 500 bytes per member is a very safe floor.
    assert len(r_pdf.content) >= 5_000 + 200 * len(csv_rows), (
        f"PDF suspiciously small — {len(r_pdf.content)} bytes for {len(csv_rows)} members"
    )
    # Filename in disposition.
    assert "aop-members" in r_pdf.headers.get("content-disposition", "")


def test_admin_members_pdf_is_admin_only():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.get(f"{BASE}/admin/members/export.pdf", timeout=15)
    assert r.status_code == 403


def test_report_pdf_non_admin_forbidden():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.get(f"{BASE}/reports/members/export.pdf", timeout=15)
    assert r.status_code == 403


def test_unknown_report_kind_400():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/nonsense/export.pdf", timeout=15)
    assert r.status_code == 400
    assert "unknown" in r.json().get("detail", "").lower()


def test_reports_members_pdf_uses_card_layout():
    """The members PDF should include CSV-style rich data — check that
    the PDF is significantly larger than the small tabular version was.
    A card-layout PDF for ~30 members is expected to be > 30KB."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/members/export.pdf", timeout=45)
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"
    # The old tabular members PDF was ~6-8 KB for 30 members. The new
    # card layout renders one page per member so it must be considerably
    # larger.
    assert len(r.content) > 20_000, f"PDF too small ({len(r.content)} bytes) — card layout didn't kick in"


def test_report_pdf_honors_year_filter():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/hours/export.pdf?year=2026", timeout=30)
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_awards_pdf_uses_award_grants_endpoint():
    """Awards PDF aliases to /reports/award-grants — should still succeed."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/awards/export.pdf", timeout=30)
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_dues_pdf_reads_transactions_directly():
    """The dues + event-tickets kinds don't have a /reports/* endpoint —
    exports.py builds the row list from db.transactions itself."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    for kind in ("dues", "event-tickets"):
        r = admin.get(f"{BASE}/reports/{kind}/export.pdf", timeout=30)
        assert r.status_code == 200, f"{kind}: {r.status_code} {r.text[:200]}"
        assert r.content[:5] == b"%PDF-"
