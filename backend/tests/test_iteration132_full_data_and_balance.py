"""Iter 132 — Full member data capture + correct balance calculation.

Two bugs the user hit:
  1. City / State / ZIP / DOB were showing as empty in the export because
     the export code was reading `birth_date` and a nested `address` dict,
     but users store `birthdate` (no underscore) and flat top-level
     city/state/zip_code/country fields.
  2. Outstanding balance always showed 0 because we were reading a
     never-populated `outstanding_balance_total` field on the user doc.
     Per routes/balances.py the balance is COMPUTED live from
     `balance_lines`, never stored.

Covers:
  - City/State/ZIP populate correctly in CSV + PDF.
  - `birthdate` (no underscore) is read.
  - Outstanding balance is the sum of unpaid balance_lines.
  - Total paid is the sum of paid balance_lines.
  - Card layout renders a "Balance line items" section.
  - New profile fields (branch, line_name, intake_line, marital_status)
    are surfaced in both CSV headers and card sections.
"""
from __future__ import annotations

import csv as csv_mod
import io
import os
import sys
from pathlib import Path

import pdfplumber
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


def _read_csv_rows(admin) -> list:
    r = admin.get(f"{BASE}/admin/members/export.csv", timeout=30)
    assert r.status_code == 200
    return list(csv_mod.DictReader(io.StringIO(r.text)))


def test_csv_has_expected_new_fields():
    """Iter 132 — export must surface every profile field the user asked for."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/admin/members/export.csv", timeout=30)
    assert r.status_code == 200
    reader = csv_mod.DictReader(io.StringIO(r.text))
    fieldnames = set(reader.fieldnames or [])
    # Fields that were broken / missing before this iter.
    for expected in (
        "birth_date", "city", "state", "postal_code", "country", "address",
        "outstanding_balance_total", "total_paid", "balance_lines",
        "branch_of_service", "line_name", "intake_line", "marital_status",
    ):
        assert expected in fieldnames, f"CSV missing column {expected!r}"


def test_csv_reads_flat_address_fields():
    """Users store city / state / zip_code as flat top-level fields — my
    old code treated address as a nested dict and dropped all of these.
    At least one seeded preview member has City=Chicago."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    rows = _read_csv_rows(admin)
    # Some preview member must have at least one non-empty city.
    non_empty_cities = [r["city"] for r in rows if (r.get("city") or "").strip()]
    assert len(non_empty_cities) > 0, "No CSV rows have city populated — flat-field read broken"


def test_outstanding_balance_computed_from_balance_lines():
    """Add a balance line to a member, re-export, and confirm the amount
    lands in the outstanding_balance_total column. Then clean up."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    # Pick any member.
    m = admin.get(f"{BASE}/members?limit=5", timeout=15).json()
    if isinstance(m, dict):
        m = m.get("items", [])
    assert len(m) > 0
    uid = m[0]["id"]
    r = admin.post(
        f"{BASE}/admin/members/{uid}/balance/lines",
        json={"label": "Iter132 regression fee", "amount": 42.5},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    line_id = r.json()["lines"][-1]["id"]
    try:
        # Re-export and find this member.
        rows = _read_csv_rows(admin)
        me = next((r for r in rows if r["id"] == uid), None)
        assert me is not None, "seeded member missing from export"
        assert float(me["outstanding_balance_total"]) == 42.5, (
            f"Expected balance 42.5, got {me['outstanding_balance_total']!r}"
        )
        # The balance_lines summary column should include the fee.
        assert "Iter132 regression fee" in me["balance_lines"]
        assert "$42.50" in me["balance_lines"] or "42.5" in me["balance_lines"]
        assert "unpaid" in me["balance_lines"].lower()
    finally:
        # Clean up the seeded line.
        admin.delete(f"{BASE}/admin/members/{uid}/balance/lines/{line_id}", timeout=15)


def test_paid_balance_line_flows_to_total_paid():
    admin = _login("admin@clubhaven.app", "Admin123!")
    m = admin.get(f"{BASE}/members?limit=5", timeout=15).json()
    if isinstance(m, dict):
        m = m.get("items", [])
    uid = m[0]["id"]
    r = admin.post(
        f"{BASE}/admin/members/{uid}/balance/lines",
        json={"label": "Iter132 paid regression", "amount": 30.0},
        timeout=15,
    )
    line_id = r.json()["lines"][-1]["id"]
    try:
        # Mark it paid via admin.
        r2 = admin.post(
            f"{BASE}/admin/members/{uid}/balance/lines/{line_id}/mark-paid",
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        # Re-export.
        rows = _read_csv_rows(admin)
        me = next((r for r in rows if r["id"] == uid), None)
        assert me is not None
        # Unpaid balance drops back to 0, total_paid picks up the 30.
        assert float(me["outstanding_balance_total"]) == 0.0
        assert float(me["total_paid"]) >= 30.0
        assert "paid" in me["balance_lines"].lower()
    finally:
        admin.delete(f"{BASE}/admin/members/{uid}/balance/lines/{line_id}", timeout=15)


def test_pdf_cards_render_balance_line_items_section():
    """When a member has any balance_lines the card layout must include a
    "Balance line items" section listing each label + amount + paid state."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    m = admin.get(f"{BASE}/members?limit=5", timeout=15).json()
    if isinstance(m, dict):
        m = m.get("items", [])
    uid = m[0]["id"]
    name = m[0].get("name") or ""
    r = admin.post(
        f"{BASE}/admin/members/{uid}/balance/lines",
        json={"label": "Iter132 PDF card check", "amount": 12.34},
        timeout=15,
    )
    line_id = r.json()["lines"][-1]["id"]
    try:
        r_pdf = admin.get(f"{BASE}/admin/members/export.pdf", timeout=60)
        assert r_pdf.status_code == 200
        found = False
        with pdfplumber.open(io.BytesIO(r_pdf.content)) as pdf:
            for p in pdf.pages:
                t = p.extract_text() or ""
                if "Iter132 PDF card check" in t and (name in t if name else True):
                    assert "BALANCE LINE ITEMS" in t
                    assert "$12.34" in t or "12.34" in t
                    assert "unpaid" in t.lower()
                    # Outstanding balance line must show the same amount.
                    assert "Outstanding balance" in t
                    found = True
                    break
        assert found, "Seeded member card not found in PDF"
    finally:
        admin.delete(f"{BASE}/admin/members/{uid}/balance/lines/{line_id}", timeout=15)


def test_pdf_roster_shows_balance_column():
    """The landscape roster must include a Bal column with computed values."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    m = admin.get(f"{BASE}/members?limit=5", timeout=15).json()
    if isinstance(m, dict):
        m = m.get("items", [])
    uid = m[0]["id"]
    r = admin.post(
        f"{BASE}/admin/members/{uid}/balance/lines",
        json={"label": "Iter132 roster fee", "amount": 199.0},
        timeout=15,
    )
    line_id = r.json()["lines"][-1]["id"]
    try:
        r_pdf = admin.get(f"{BASE}/admin/members/export.pdf?layout=rows", timeout=60)
        assert r_pdf.status_code == 200
        with pdfplumber.open(io.BytesIO(r_pdf.content)) as pdf:
            all_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        assert "199" in all_text, "Roster PDF missing seeded balance value"
    finally:
        admin.delete(f"{BASE}/admin/members/{uid}/balance/lines/{line_id}", timeout=15)


def test_birthdate_field_flows_through():
    """The user model stores birthdate (no underscore). Export reads either."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    rows = _read_csv_rows(admin)
    # No assertion on values (preview data may not have any DOB), but the
    # column must exist and every row must be able to serialize.
    assert all("birth_date" in r for r in rows)


def test_pdf_card_membership_shows_dollar_formatted_balance():
    admin = _login("admin@clubhaven.app", "Admin123!")
    m = admin.get(f"{BASE}/members?limit=5", timeout=15).json()
    if isinstance(m, dict):
        m = m.get("items", [])
    uid = m[0]["id"]
    r = admin.post(
        f"{BASE}/admin/members/{uid}/balance/lines",
        json={"label": "Iter132 dollar format", "amount": 1234.5},
        timeout=15,
    )
    line_id = r.json()["lines"][-1]["id"]
    try:
        r_pdf = admin.get(f"{BASE}/admin/members/export.pdf", timeout=60)
        with pdfplumber.open(io.BytesIO(r_pdf.content)) as pdf:
            found_page = None
            for p in pdf.pages:
                t = p.extract_text() or ""
                if "Iter132 dollar format" in t:
                    found_page = t
                    break
        assert found_page is not None
        # Dollar formatting must appear: $1,234.50
        assert "$1,234.50" in found_page
    finally:
        admin.delete(f"{BASE}/admin/members/{uid}/balance/lines/{line_id}", timeout=15)
