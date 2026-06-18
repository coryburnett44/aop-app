"""Iteration 42: admin bulk hours + CSV import tests."""
import os
import io
import uuid
import requests
import pytest

RUN_TAG = uuid.uuid4().hex[:8]

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def member_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=MEMBER, timeout=15)
    assert r.status_code == 200, f"member login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def members(admin_session):
    r = admin_session.get(f"{API}/members", timeout=15)
    assert r.status_code == 200
    data = r.json()
    # Take 3 active member users (not admin)
    pool = [u for u in data if u.get("role") == "member"][:3]
    assert len(pool) >= 3, f"need at least 3 members, got {len(pool)}"
    return pool


# ----- /hours/admin/bulk -----

def test_bulk_log_three_members(admin_session, members):
    ids = [m["id"] for m in members[:3]]
    activity_label = f"TEST_iter42 bulk park cleanup {RUN_TAG}"
    body = {
        "user_ids": ids,
        "hours": 1.5,
        "date": "2026-06-15T00:00:00",
        "activity": activity_label,
        "event_type": "aop_related",
        "agency_name": "TEST_Bulk Agency",
    }
    r = admin_session.post(f"{API}/hours/admin/bulk", json=body, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created"] == 3
    assert d["failed"] == 0
    assert d["total"] == 3
    # Verify persisted as approved (note: hours_out serializer does not expose
    # logged_by_admin/approved_by fields — that's tracked separately as a
    # minor issue)
    r2 = admin_session.get(f"{API}/hours?status_filter=approved", timeout=15)
    assert r2.status_code == 200, r2.text
    hits = [h for h in r2.json() if h.get("activity") == activity_label]
    assert len(hits) == 3
    for h in hits:
        assert h.get("status") == "approved"


def test_bulk_validation_empty_ids(admin_session):
    r = admin_session.post(f"{API}/hours/admin/bulk", json={
        "user_ids": [], "hours": 1, "date": "2026-06-15T00:00:00"}, timeout=15)
    assert r.status_code == 422


def test_bulk_validation_zero_hours(admin_session, members):
    r = admin_session.post(f"{API}/hours/admin/bulk", json={
        "user_ids": [members[0]["id"]], "hours": 0, "date": "2026-06-15T00:00:00"}, timeout=15)
    assert r.status_code == 422


def test_bulk_validation_missing_date(admin_session, members):
    r = admin_session.post(f"{API}/hours/admin/bulk", json={
        "user_ids": [members[0]["id"]], "hours": 1}, timeout=15)
    assert r.status_code == 422


def test_bulk_dedupes_repeated_ids(admin_session, members):
    uid = members[0]["id"]
    activity_label = f"TEST_iter42 dedupe check {RUN_TAG}"
    body = {
        "user_ids": [uid, uid, uid],
        "hours": 0.5,
        "date": "2026-07-01T00:00:00",
        "activity": activity_label,
    }
    r = admin_session.post(f"{API}/hours/admin/bulk", json=body, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created"] == 1
    assert d["total"] == 1
    # Verify only one row inserted in DB
    r2 = admin_session.get(f"{API}/hours?status_filter=approved", timeout=15)
    hits = [h for h in r2.json() if h.get("activity") == activity_label]
    assert len(hits) == 1


def test_bulk_partial_failure(admin_session, members):
    body = {
        "user_ids": [members[0]["id"], "nonexistent-id-xyz"],
        "hours": 1,
        "date": "2026-07-02T00:00:00",
        "activity": "TEST_iter42 partial",
    }
    r = admin_session.post(f"{API}/hours/admin/bulk", json=body, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created"] == 1
    assert d["failed"] == 1
    results = d["results"]
    ok = [x for x in results if x["ok"]]
    bad = [x for x in results if not x["ok"]]
    assert len(ok) == 1 and len(bad) == 1
    assert "not found" in bad[0]["error"].lower()


# ----- CSV template -----

def test_csv_template(admin_session):
    r = admin_session.get(f"{API}/hours/admin/csv/template", timeout=15)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("Content-Type", "")
    text = r.text
    first_line = text.splitlines()[0].lower()
    for col in ["member_email", "hours", "date", "activity", "event_type",
                "agency_name", "host_name", "host_email", "host_phone"]:
        assert col in first_line, f"missing {col} in template header: {first_line}"


# ----- /hours/admin/csv -----

def test_csv_import_valid(admin_session, members):
    rows = "member_email,hours,date,activity,event_type,agency_name,host_name,host_email,host_phone\n"
    for m in members[:3]:
        rows += f"{m['email']},2.0,2026-08-01,TEST_iter42 csv ok,aop_related,TEST_Agency,Jane Host,jane@example.org,555-1234\n"
    files = {"file": ("test.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    r = admin_session.post(f"{API}/hours/admin/csv", files=files, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created"] == 3
    assert d["failed"] == 0


def test_csv_import_mixed_errors(admin_session, members):
    rows = "member_email,hours,date,activity\n"
    rows += f"{members[0]['email']},2.0,2026-08-02,TEST_iter42 csv mix ok\n"
    rows += "ghost@nowhere.invalid,2.0,2026-08-02,bad email row\n"
    rows += f"{members[1]['email']},-3.0,2026-08-02,bad hours row\n"
    rows += f"{members[2]['email']},2.0,not-a-date,bad date row\n"
    files = {"file": ("mix.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    r = admin_session.post(f"{API}/hours/admin/csv", files=files, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created"] == 1
    assert d["failed"] == 3
    assert len(d["errors"]) == 3
    msgs = " ".join(e["message"].lower() for e in d["errors"])
    assert "email" in msgs or "no member" in msgs
    assert "hours" in msgs
    assert "date" in msgs


def test_csv_rejects_non_csv_filename(admin_session):
    files = {"file": ("bad.txt", io.BytesIO(b"member_email,hours,date\n"), "text/plain")}
    r = admin_session.post(f"{API}/hours/admin/csv", files=files, timeout=15)
    assert r.status_code == 400


def test_csv_missing_required_column(admin_session, members):
    rows = "member_email,date\n" + f"{members[0]['email']},2026-08-03\n"
    files = {"file": ("bad.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    r = admin_session.post(f"{API}/hours/admin/csv", files=files, timeout=15)
    assert r.status_code == 400
    assert "hours" in r.text.lower()


def test_csv_empty_data_section(admin_session):
    rows = "member_email,hours,date\n"
    files = {"file": ("empty.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    r = admin_session.post(f"{API}/hours/admin/csv", files=files, timeout=15)
    assert r.status_code == 400


# ----- Authz -----

def test_member_cannot_bulk(member_session, members):
    body = {"user_ids": [members[0]["id"]], "hours": 1, "date": "2026-07-01T00:00:00"}
    r = member_session.post(f"{API}/hours/admin/bulk", json=body, timeout=15)
    assert r.status_code in (401, 403)


def test_member_cannot_csv(member_session):
    files = {"file": ("x.csv", io.BytesIO(b"member_email,hours,date\n"), "text/csv")}
    r = member_session.post(f"{API}/hours/admin/csv", files=files, timeout=15)
    assert r.status_code in (401, 403)


def test_member_cannot_template(member_session):
    r = member_session.get(f"{API}/hours/admin/csv/template", timeout=15)
    assert r.status_code in (401, 403)
