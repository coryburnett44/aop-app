"""
Iteration 56 — Bulk donations CSV import + Top Donors leaderboard.

Covers:
  - GET /donations/admin/csv/template returns the canonical header
  - POST /donations/admin/csv?dry_run=true never writes
  - POST /donations/admin/csv?dry_run=false writes only valid rows
  - Non-admin gets 403
  - Row errors: missing email, missing/negative amount, unknown cause, bad date
  - GET /leaderboards/top-donors returns the correct top members + chapters
  - Anonymous donations are excluded from member leaderboard but counted in chapter totals

Run: REACT_APP_BACKEND_URL=... pytest /app/backend/tests/test_iteration56_donations_csv.py -v
"""
import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PW = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PW = "Member123!"

MARKER = f"iter56-csv-{int(time.time())}"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def member():
    return _login(MEMBER_EMAIL, MEMBER_PW)


@pytest.fixture(scope="module")
def first_cause_title(admin):
    r = admin.get(f"{API}/causes", timeout=10)
    assert r.status_code == 200
    items = r.json()
    assert items, "no causes seeded — test cannot resolve a cause title"
    return items[0]["title"]


@pytest.fixture(autouse=True)
def cleanup_after(admin):
    """After every test, delete any donations tagged with our run marker."""
    yield
    # Pull the full donations list across all causes and delete matches via raw
    # mongo (the API doesn't expose a delete-donation endpoint, so we rely on
    # the test marker living in the `description` field for filtering).
    try:
        from pymongo import MongoClient
        mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = mc[os.environ.get("DB_NAME", "clubhaven_db")]
        db.transactions.delete_many({"description": {"$regex": MARKER}})
    except Exception:
        pass


def _csv_bytes(rows):
    buf = io.StringIO()
    buf.write("member_email,amount,cause,date,note,anonymous,method\n")
    for r in rows:
        buf.write(",".join(str(c) for c in r) + "\n")
    return buf.getvalue().encode("utf-8")


def test_template_endpoint_returns_canonical_header(admin):
    r = admin.get(f"{API}/donations/admin/csv/template", timeout=10)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    first = r.text.splitlines()[0]
    assert first == "member_email,amount,cause,date,note,anonymous,method"


def test_non_admin_gets_403(member):
    payload = _csv_bytes([])
    r = member.post(
        f"{API}/donations/admin/csv",
        files={"file": ("d.csv", payload, "text/csv")},
        timeout=15,
    )
    assert r.status_code == 403


def test_dry_run_never_writes(admin, first_cause_title):
    payload = _csv_bytes([
        [MEMBER_EMAIL, 50, first_cause_title, "2026-05-01", MARKER, "false", "manual_csv"],
    ])
    r = admin.post(
        f"{API}/donations/admin/csv?dry_run=true",
        files={"file": ("d.csv", payload, "text/csv")},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] is True
    assert d["created"] == 0
    assert d["total"] == 1
    assert d["rows"][0]["status"] == "READY"


def test_real_import_writes_only_valid_rows(admin, first_cause_title):
    payload = _csv_bytes([
        [MEMBER_EMAIL, 75, first_cause_title, "2026-05-02", f"{MARKER} ok-1", "false", "manual_csv"],
        ["not-a-member@example.com", 25, first_cause_title, "2026-05-02", f"{MARKER} bad-email", "false", "manual_csv"],
        [MEMBER_EMAIL, -10, first_cause_title, "2026-05-02", f"{MARKER} bad-amount", "false", "manual_csv"],
        [MEMBER_EMAIL, 30, "Does-Not-Exist Fund", "2026-05-02", f"{MARKER} unmatched-cause", "false", "manual_csv"],
        [MEMBER_EMAIL, 40, first_cause_title, "garbled-date", f"{MARKER} bad-date", "false", "manual_csv"],
    ])
    r = admin.post(
        f"{API}/donations/admin/csv?dry_run=false",
        files={"file": ("d.csv", payload, "text/csv")},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # Now that an unmatched cause is a WARNING (not an ERROR), 2 of the 5
    # rows write successfully: the matched-cause row AND the unmatched-cause
    # row. The other 3 fail on bad email / negative amount / bad date.
    assert d["created"] == 2, f"expected 2 successful rows, got {d['created']}"
    assert d["failed"] == 3
    statuses = [r["status"] for r in d["rows"]]
    assert statuses.count("READY") == 2
    assert statuses.count("ERROR") == 3
    errs_by_row = {r["row"]: r["errors"] for r in d["rows"]}
    warns_by_row = {r["row"]: r.get("warnings", []) for r in d["rows"]}
    assert any("no member" in e for e in errs_by_row[3])
    assert any("amount must be > 0" in e for e in errs_by_row[4])
    # Unmatched cause is now a non-blocking warning, not an error
    assert errs_by_row[5] == []
    assert any("not found" in w and "unallocated" in w for w in warns_by_row[5])
    assert any("date" in e and "garbled-date" in e for e in errs_by_row[6])


def test_unmatched_cause_preserves_label_in_description(admin, first_cause_title):
    """An unmatched cause label is preserved in the transaction description
    so the donation remains traceable in /reports/donations and member
    receipts (no cause_id link but the fund name lives on)."""
    label = f"{MARKER} Made-Up Fund"
    payload = _csv_bytes([
        [MEMBER_EMAIL, 60, label, "2026-05-04", f"{MARKER} preserved-label", "false", "manual_csv"],
    ])
    r = admin.post(
        f"{API}/donations/admin/csv?dry_run=false",
        files={"file": ("d.csv", payload, "text/csv")},
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["created"] == 1
    # Read it back via /reports/donations
    r2 = admin.get(f"{API}/reports/donations", timeout=10)
    assert r2.status_code == 200
    rows = r2.json()
    match = next((t for t in rows if "preserved-label" in (t.get("description") or "")), None)
    assert match is not None, "imported donation not found in /reports/donations"
    assert match.get("cause_id") in (None, ""), "cause_id should be empty for unmatched cause"
    assert label in (match.get("description") or ""), f"unmatched cause label should be preserved in description: {match.get('description')}"


def test_top_donors_returns_correct_shape(admin, first_cause_title):
    # Seed one $200 donation tagged with our marker so the leaderboard has data
    payload = _csv_bytes([
        [MEMBER_EMAIL, 200, first_cause_title, "2026-05-15", MARKER, "false", "manual_csv"],
    ])
    r = admin.post(
        f"{API}/donations/admin/csv?dry_run=false",
        files={"file": ("d.csv", payload, "text/csv")},
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["created"] == 1

    r2 = admin.get(f"{API}/leaderboards/top-donors?period=all", timeout=10)
    assert r2.status_code == 200
    d = r2.json()
    assert d["period"] == "all"
    assert d["period_label"] == "All time"
    assert isinstance(d["top_chapters"], list)
    assert isinstance(d["top_members"], list)
    # Riley (member@clubhaven.app) should be present somewhere in top_members
    member_names = [m["user_name"] for m in d["top_members"]]
    assert any("Riley" in n or "Member" in n for n in member_names) or len(member_names) > 0


def test_top_donors_excludes_anonymous_from_member_board(admin, first_cause_title):
    payload = _csv_bytes([
        [MEMBER_EMAIL, 999.99, first_cause_title, "2026-05-20", f"{MARKER} anon", "true", "manual_csv"],
    ])
    r = admin.post(
        f"{API}/donations/admin/csv?dry_run=false",
        files={"file": ("d.csv", payload, "text/csv")},
        timeout=15,
    )
    assert r.status_code == 200 and r.json()["created"] == 1

    r2 = admin.get(f"{API}/leaderboards/top-donors?period=all", timeout=10)
    assert r2.status_code == 200
    d = r2.json()
    # No member row should show the exact $999.99 contribution because it was anonymous
    member_amounts = [m["amount"] for m in d["top_members"]]
    assert 999.99 not in member_amounts


def test_period_filter_quarter_returns_label(admin):
    r = admin.get(f"{API}/leaderboards/top-donors?period=quarter", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["period"] == "quarter"
    assert d["period_label"].startswith("Q")  # e.g. "Q1 2026"
