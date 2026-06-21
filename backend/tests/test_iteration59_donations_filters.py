"""
Iteration 59 — Donations filter parity with hours + member year filter on
/me/transactions + cause column resolver on the admin Donations report.

Covers:
  - /reports/donations gains user_id, chapter_id, year, quarter, month,
    from_date, to_date filters with the same semantics as /reports/hours.
  - /me/transactions accepts year={YYYY} (or omitted = all years).
  - Cause label preservation continues to work end-to-end.

Run: REACT_APP_BACKEND_URL=... pytest /app/backend/tests/test_iteration59_donations_filters.py -v
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

MARKER = f"iter59-{int(time.time())}"


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
def member_info(member):
    r = member.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def first_cause_title(admin):
    r = admin.get(f"{API}/causes", timeout=10)
    assert r.status_code == 200
    return r.json()[0]["title"]


def _csv_bytes(rows):
    buf = io.StringIO()
    buf.write("member_email,amount,cause,date,note,anonymous,method\n")
    for r in rows:
        buf.write(",".join(str(c) for c in r) + "\n")
    return buf.getvalue().encode("utf-8")


@pytest.fixture(autouse=True)
def cleanup_after():
    yield
    try:
        from pymongo import MongoClient
        mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = mc[os.environ.get("DB_NAME", "clubhaven_db")]
        db.transactions.delete_many({"description": {"$regex": MARKER}})
    except Exception:
        pass


def test_donations_filter_by_user_id(admin, member_info, first_cause_title):
    payload = _csv_bytes([[MEMBER_EMAIL, 50, first_cause_title, "2026-07-01", f"{MARKER} user-only", "false", "manual_csv"]])
    assert admin.post(f"{API}/donations/admin/csv?dry_run=false", files={"file": ("d.csv", payload, "text/csv")}, timeout=15).json()["created"] == 1

    r = admin.get(f"{API}/reports/donations", params={"user_id": member_info["id"]}, timeout=10)
    assert r.status_code == 200
    rows = r.json()
    # All rows must belong to that user
    assert all(t["user_id"] == member_info["id"] for t in rows)
    # Marker row must be present
    assert any(MARKER in (t.get("description") or "") for t in rows)


def test_donations_filter_by_chapter_id(admin, member_info, first_cause_title):
    payload = _csv_bytes([[MEMBER_EMAIL, 60, first_cause_title, "2026-07-02", f"{MARKER} chapter-test", "false", "manual_csv"]])
    admin.post(f"{API}/donations/admin/csv?dry_run=false", files={"file": ("d.csv", payload, "text/csv")}, timeout=15)
    cid = member_info.get("chapter_id")
    assert cid, "test member must have a chapter_id"
    r = admin.get(f"{API}/reports/donations", params={"chapter_id": cid}, timeout=10)
    assert r.status_code == 200
    rows = r.json()
    # Member's marker row should be in the result
    assert any(MARKER in (t.get("description") or "") for t in rows)


def test_donations_filter_by_year(admin, first_cause_title):
    payload = _csv_bytes([[MEMBER_EMAIL, 70, first_cause_title, "2026-07-03", f"{MARKER} year-2026", "false", "manual_csv"]])
    admin.post(f"{API}/donations/admin/csv?dry_run=false", files={"file": ("d.csv", payload, "text/csv")}, timeout=15)

    r_2026 = admin.get(f"{API}/reports/donations", params={"year": 2026}, timeout=10)
    assert r_2026.status_code == 200
    rows_2026 = r_2026.json()
    assert all(t.get("created_at", "").startswith("2026") for t in rows_2026)
    assert any(MARKER in (t.get("description") or "") for t in rows_2026)

    r_2024 = admin.get(f"{API}/reports/donations", params={"year": 2024}, timeout=10)
    assert r_2024.status_code == 200
    # No marker row should be in 2024 (we wrote it in 2026)
    assert not any(MARKER in (t.get("description") or "") for t in r_2024.json())


def test_donations_filter_by_quarter_and_month(admin, first_cause_title):
    # write a row dated 2026-08-15
    payload = _csv_bytes([[MEMBER_EMAIL, 80, first_cause_title, "2026-08-15", f"{MARKER} q3-aug", "false", "manual_csv"]])
    admin.post(f"{API}/donations/admin/csv?dry_run=false", files={"file": ("d.csv", payload, "text/csv")}, timeout=15)

    r_q3 = admin.get(f"{API}/reports/donations", params={"year": 2026, "quarter": 3}, timeout=10)
    assert r_q3.status_code == 200
    assert any(MARKER in (t.get("description") or "") for t in r_q3.json())

    r_q1 = admin.get(f"{API}/reports/donations", params={"year": 2026, "quarter": 1}, timeout=10)
    assert r_q1.status_code == 200
    assert not any(MARKER in (t.get("description") or "") for t in r_q1.json())

    r_month = admin.get(f"{API}/reports/donations", params={"year": 2026, "month": 8}, timeout=10)
    assert r_month.status_code == 200
    assert any(MARKER in (t.get("description") or "") for t in r_month.json())

    r_month_other = admin.get(f"{API}/reports/donations", params={"year": 2026, "month": 9}, timeout=10)
    assert r_month_other.status_code == 200
    assert not any(MARKER in (t.get("description") or "") for t in r_month_other.json())


def test_me_transactions_year_filter(admin, member, first_cause_title):
    payload = _csv_bytes([[MEMBER_EMAIL, 90, first_cause_title, "2026-09-01", f"{MARKER} me-2026", "false", "manual_csv"]])
    admin.post(f"{API}/donations/admin/csv?dry_run=false", files={"file": ("d.csv", payload, "text/csv")}, timeout=15)

    r_all = member.get(f"{API}/me/transactions", timeout=10)
    assert r_all.status_code == 200
    all_rows = r_all.json()

    r_2026 = member.get(f"{API}/me/transactions", params={"year": 2026}, timeout=10)
    assert r_2026.status_code == 200
    r_2026_rows = r_2026.json()
    assert all(t.get("created_at", "").startswith("2026") for t in r_2026_rows)
    assert len(r_2026_rows) <= len(all_rows)

    r_old = member.get(f"{API}/me/transactions", params={"year": 2017}, timeout=10)
    assert r_old.status_code == 200
    # No marker rows in 2017
    assert not any(MARKER in (t.get("description") or "") for t in r_old.json())


def test_cause_label_field_returned_on_unmatched(admin, first_cause_title):
    payload = _csv_bytes([[MEMBER_EMAIL, 55, "Iter59 Made-Up Fund", "2026-09-02", f"{MARKER} cause-label", "false", "manual_csv"]])
    admin.post(f"{API}/donations/admin/csv?dry_run=false", files={"file": ("d.csv", payload, "text/csv")}, timeout=15)
    r = admin.get(f"{API}/reports/donations", params={"year": 2026, "month": 9}, timeout=10)
    assert r.status_code == 200
    match = next((t for t in r.json() if "cause-label" in (t.get("description") or "")), None)
    assert match is not None, "imported donation not found in report"
    assert match.get("cause_id") in (None, "")
    assert match.get("cause_label") == "Iter59 Made-Up Fund"
