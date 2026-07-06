"""Iter 113 regression: donations CSV import name/amount robustness.

The user reported two production issues with Admin → Causes → CSV donation
imports:

  1. A member's donations were not tracked at all despite a "success" toast
     (name in the CSV didn't exactly match the account name — the account
     has a middle initial the CSV omitted, or vice versa).
  2. Amounts formatted with currency symbols or thousands separators
     ("$1,234.00") silently failed to parse — the row was skipped without
     a prominent warning.

This test file guards against both regressions and locks the relaxed
name-matching + tolerant amount parsing behavior in place.
"""
from __future__ import annotations

import io
import os
import uuid

import pytest
import requests


BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin() -> requests.Session:
    return _login("admin@clubhaven.app", "Admin123!")


@pytest.fixture()
def brandy(admin: requests.Session):
    """A member whose stored `name` includes a middle initial ("Brandy L.
    Brodie") — mirrors the exact scenario the user described."""
    email = f"brandy-{uuid.uuid4().hex[:8]}@example.com"
    r = admin.post(f"{BASE}/admin/members", json={
        "email": email, "password": "Test1234!",
        "name": "Brandy L. Brodie",
        "first_name": "Brandy L.", "last_name": "Brodie",
    })
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    yield {"id": uid, "email": email}
    admin.delete(f"{BASE}/members/{uid}")


@pytest.fixture()
def cause(admin: requests.Session):
    r = admin.post(f"{BASE}/causes", json={
        "title": f"Iter113 cause {uuid.uuid4().hex[:6]}",
        "description": "test cause",
        "goal_amount": 5000,
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    yield cid
    admin.delete(f"{BASE}/causes/{cid}")


def _csv_upload(sess: requests.Session, csv_text: str, dry_run: bool = False):
    files = {"file": ("donations.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
    r = sess.post(f"{BASE}/donations/admin/csv", params={"dry_run": str(dry_run).lower()}, files=files, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def test_name_missing_middle_initial_matches_via_relaxed_lookup(admin, brandy, cause):
    """The DB has "Brandy L. Brodie" — the CSV just says "Brandy Brodie".
    Before the fix the row failed with "no member named 'Brandy Brodie'".
    """
    csv = (
        "full_name,amount,date,cause_id\n"
        f"Brandy Brodie,50.00,2026-01-15,{cause}\n"
    )
    result = _csv_upload(admin, csv, dry_run=True)
    assert result["total"] == 1
    assert result["failed"] == 0, f"expected relaxed name match: {result['rows']}"
    assert result["rows"][0]["status"] == "READY"


def test_first_last_missing_middle_initial_matches(admin, brandy, cause):
    """Same relaxation with the split first/last columns.

    Note the DB has first_name='Brandy L.' — the CSV supplies just 'Brandy'.
    Relaxed matching should accept this."""
    csv = (
        "first_name,last_name,amount,date,cause_id\n"
        f"Brandy,Brodie,25.00,2026-01-15,{cause}\n"
    )
    result = _csv_upload(admin, csv, dry_run=True)
    assert result["total"] == 1
    assert result["failed"] == 0, f"expected relaxed first/last match: {result['rows']}"


def test_amount_with_currency_symbol_and_comma_parses(admin, brandy, cause):
    """Excel-exported CSVs often quote amounts like "$1,234.00". Before the
    fix these blew up with ValueError → row silently skipped."""
    csv = (
        'full_name,amount,date,cause_id\n'
        f'"Brandy L. Brodie","$1,234.56",2026-01-15,{cause}\n'
    )
    result = _csv_upload(admin, csv, dry_run=True)
    assert result["failed"] == 0, f"amount parse failed: {result['rows']}"
    assert result["rows"][0]["status"] == "READY"


def test_amount_with_negative_parens_parses(admin, brandy, cause):
    """Accounting-style "(50.00)" for negatives: still errors (amount must
    be > 0) but with a *specific* error message, not a cryptic ValueError."""
    csv = (
        "full_name,amount,date,cause_id\n"
        f"Brandy L. Brodie,(50.00),2026-01-15,{cause}\n"
    )
    result = _csv_upload(admin, csv, dry_run=True)
    assert result["total"] == 1
    # -50 is not > 0 so it's still rejected — but with a clear reason.
    errors = result["rows"][0].get("errors", [])
    assert any("amount must be > 0" in e for e in errors), errors


def test_end_to_end_dry_run_and_commit(admin, brandy, cause):
    """Full import path: dry-run then real import creates the transaction
    and it shows up in the member's donation history."""
    csv = (
        'full_name,amount,date,cause_id\n'
        f'"Brandy Brodie","$100.00",2026-01-15,{cause}\n'
    )
    dry = _csv_upload(admin, csv, dry_run=True)
    assert dry["failed"] == 0

    real = _csv_upload(admin, csv, dry_run=False)
    assert real["created"] == 1
    assert real["failed"] == 0

    # Confirm it landed on Brandy's ledger via /api/transactions?user_id=…
    r = admin.get(f"{BASE}/transactions", params={"user_id": brandy["id"], "type_filter": "donation"})
    assert r.status_code == 200, r.text
    donations = r.json()
    assert any(abs(t["amount"] - 100.0) < 0.01 for t in donations), donations
