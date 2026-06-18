"""Iteration 45: CSV dry-run preview + two-step confirm import tests.

Tests POST /api/hours/admin/csv?dry_run=true (validates only, no DB write)
followed by POST /api/hours/admin/csv (no dry_run) for the actual write.
"""
import os
import io
import uuid
import requests
import pytest

RUN_TAG = uuid.uuid4().hex[:8]

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

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
    pool = [u for u in r.json() if u.get("role") == "member"][:3]
    assert len(pool) >= 2, f"need >=2 members, got {len(pool)}"
    return pool


def _hours_count(sess):
    """Approximate count via GET /hours (admin view, capped at 500)."""
    r = sess.get(f"{API}/hours", timeout=15)
    assert r.status_code == 200, r.text
    return len(r.json())


# ----- Dry-run mixed CSV: 2 valid + 1 invalid -----

def test_dry_run_mixed_does_not_persist(admin_session, members):
    """dry_run=true with 2 valid + 1 invalid email row returns the right
    counts AND writes nothing to volunteer_hours."""
    activity_label = f"TEST_iter45 dryrun mixed {RUN_TAG}"
    rows = "member_email,hours,date,activity\n"
    rows += f"{members[0]['email']},2.0,2026-09-01,{activity_label}\n"
    rows += f"{members[1]['email']},3.5,2026-09-02,{activity_label}\n"
    rows += f"ghost+{RUN_TAG}@nowhere.invalid,1.0,2026-09-03,{activity_label}\n"

    files = {"file": ("mixed.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    before = _hours_count(admin_session)
    r = admin_session.post(f"{API}/hours/admin/csv?dry_run=true", files=files, timeout=20)
    after = _hours_count(admin_session)

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] is True
    assert d["created"] == 0
    assert d["ready"] == 2
    assert d["failed"] == 1
    assert d["total"] == 3

    preview = d["preview"]
    assert isinstance(preview, list) and len(preview) == 3
    ready = [p for p in preview if p["status"] == "ready"]
    errs = [p for p in preview if p["status"] == "error"]
    assert len(ready) == 2 and len(errs) == 1
    # ready entries have resolved member_name
    ready_emails = sorted(p["email"].lower() for p in ready)
    assert ready_emails == sorted([members[0]["email"].lower(), members[1]["email"].lower()])
    for p in ready:
        assert p["member_name"], "ready preview must include resolved member_name"
    # error entry has a message
    assert errs[0]["message"]
    # Crucially: nothing persisted. Also double-check by activity filter.
    assert after == before, f"dry-run inserted rows! before={before} after={after}"
    r2 = admin_session.get(f"{API}/hours?status_filter=approved", timeout=15)
    hits = [h for h in r2.json() if h.get("activity") == activity_label]
    assert hits == [], f"dry-run leaked rows into DB: {len(hits)}"


# ----- Real import (no dry_run) inserts -----

def test_confirm_import_writes_to_db(admin_session, members):
    activity_label = f"TEST_iter45 confirm {RUN_TAG}"
    rows = "member_email,hours,date,activity\n"
    rows += f"{members[0]['email']},2.0,2026-09-10,{activity_label}\n"
    rows += f"{members[1]['email']},3.5,2026-09-11,{activity_label}\n"
    rows += f"ghost2+{RUN_TAG}@nowhere.invalid,1.0,2026-09-12,bad\n"

    files = {"file": ("confirm.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    r = admin_session.post(f"{API}/hours/admin/csv", files=files, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] is False
    assert d["created"] == 2
    assert d["ready"] == 2
    assert d["failed"] == 1

    r2 = admin_session.get(f"{API}/hours?status_filter=approved", timeout=15)
    hits = [h for h in r2.json() if h.get("activity") == activity_label]
    assert len(hits) == 2, f"expected 2 inserted rows, got {len(hits)}"
    for h in hits:
        assert h["status"] == "approved"


# ----- Errors-only dry-run -----

def test_dry_run_all_errors(admin_session):
    rows = "member_email,hours,date,activity\n"
    rows += f"ghost_a+{RUN_TAG}@nowhere.invalid,2.0,2026-09-20,x\n"
    rows += f"ghost_b+{RUN_TAG}@nowhere.invalid,2.0,2026-09-21,x\n"
    rows += f"ghost_c+{RUN_TAG}@nowhere.invalid,2.0,2026-09-22,x\n"
    files = {"file": ("err.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    r = admin_session.post(f"{API}/hours/admin/csv?dry_run=true", files=files, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] is True
    assert d["ready"] == 0
    assert d["created"] == 0
    assert d["failed"] == 3
    assert d["total"] == 3
    assert all(p["status"] == "error" for p in d["preview"])
    assert all(p["message"] for p in d["preview"])


# ----- Preview truncation > 200 rows -----

def test_dry_run_preview_truncated_at_200(admin_session, members):
    """A 250-row valid CSV should report ready=250 but preview length <= 200
    with preview_truncated=true."""
    email = members[0]["email"]
    lines = ["member_email,hours,date,activity"]
    for i in range(250):
        lines.append(f"{email},0.25,2026-10-01,TEST_iter45 truncate {RUN_TAG} {i}")
    rows = "\n".join(lines) + "\n"
    files = {"file": ("big.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    r = admin_session.post(f"{API}/hours/admin/csv?dry_run=true", files=files, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] is True
    assert d["ready"] == 250
    assert d["total"] == 250
    assert d["created"] == 0
    assert d["preview_truncated"] is True
    assert len(d["preview"]) == 200


# ----- Authz: non-admin denied -----

def test_member_cannot_dry_run(member_session, members):
    rows = "member_email,hours,date,activity\n"
    rows += f"{members[0]['email']},2.0,2026-09-01,x\n"
    files = {"file": ("m.csv", io.BytesIO(rows.encode("utf-8")), "text/csv")}
    r = member_session.post(f"{API}/hours/admin/csv?dry_run=true", files=files, timeout=15)
    assert r.status_code in (401, 403)


# ----- Regression from iter42: GET /api/hours still works -----

def test_get_hours_still_works(admin_session):
    r = admin_session.get(f"{API}/hours", timeout=15)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
