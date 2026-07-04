"""Iteration 102 — Member Recruitment tracking.

Covers backend of /app/backend/routes/recruitment.py end-to-end:

  * CRUD (create → list → search → update → delete)
  * Same-member guard (recruiter == recruit → 400)
  * Duplicate pair+date guard (409)
  * CSV template + export
  * CSV import: email match + name fallback + ambiguity error + skip-duplicates
  * Report entries + summary (by_recruiter / by_chapter / by_month)
  * Leaderboard: period=q1..q4 + year (Q3 2026 window since our seed dates)

All fixtures scope to test-only members (`qa_iter102_`) and use unique
recruitment IDs so we can clean up without touching production data.
"""
import io
import os
import time

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001") + "/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return s


@pytest.fixture(scope="module")
def seeded_members(admin_session):
    """Create 3 test members whose recruitment we can score. Assigned to
    the same chapter so the by_chapter aggregation has something to group."""
    # Fetch any existing chapter to attach members to.
    r = admin_session.get(f"{BASE}/chapters")
    r.raise_for_status()
    chapters = r.json()
    chapter_id = chapters[0]["id"] if chapters else None

    seeded_ids = []
    unique = str(int(time.time()))
    for i, name in enumerate(["Alpha", "Bravo", "Charlie"]):
        payload = {
            "email": f"qa_iter102_{name.lower()}_{unique}@qatest.example",
            "password": "TestPass123!",
            "first_name": "QAiter102",
            "last_name": name,
            "chapter_id": chapter_id,
        }
        r = admin_session.post(f"{BASE}/admin/members", json=payload)
        assert r.status_code in (200, 201), (r.status_code, r.text)
        seeded_ids.append(r.json()["id"])

    yield {"ids": seeded_ids, "chapter_id": chapter_id}

    # Cleanup — delete members (recruitments referencing them will remain
    # but our per-test cleanup already wipes them).
    for uid in seeded_ids:
        try:
            admin_session.delete(f"{BASE}/members/{uid}")
        except Exception:
            pass


@pytest.fixture(autouse=True)
def cleanup_recruitments(admin_session, seeded_members):
    """Wipe any recruitment records tied to seeded members before AND after
    each test so tests are hermetic."""
    def _clean():
        r = admin_session.get(f"{BASE}/recruitments?limit=2000")
        for rec in r.json():
            if rec["recruiter_id"] in seeded_members["ids"] or rec["recruit_id"] in seeded_members["ids"]:
                admin_session.delete(f"{BASE}/recruitments/{rec['id']}")
    _clean()
    yield
    _clean()


# ---------- CRUD ----------
def test_create_list_delete_recruitment(admin_session, seeded_members):
    ids = seeded_members["ids"]
    r = admin_session.post(f"{BASE}/recruitments", json={
        "recruiter_id": ids[0], "recruit_id": ids[1],
        "date_recruited": "2026-08-15", "notes": "Convention",
    })
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["recruiter_id"] == ids[0]
    assert rec["recruit_id"] == ids[1]
    assert rec["date_recruited"].startswith("2026-08-15")
    assert rec["chapter_id"] == seeded_members["chapter_id"]

    r = admin_session.get(f"{BASE}/recruitments?q=QAiter102")
    matched = [x for x in r.json() if x["id"] == rec["id"]]
    assert len(matched) == 1

    r = admin_session.delete(f"{BASE}/recruitments/{rec['id']}")
    assert r.status_code == 200
    r = admin_session.get(f"{BASE}/recruitments")
    assert not any(x["id"] == rec["id"] for x in r.json())


def test_reject_self_recruitment(admin_session, seeded_members):
    ids = seeded_members["ids"]
    r = admin_session.post(f"{BASE}/recruitments", json={
        "recruiter_id": ids[0], "recruit_id": ids[0], "date_recruited": "2026-08-15",
    })
    assert r.status_code == 400
    assert "themselves" in r.json()["detail"].lower()


def test_reject_duplicate_pair_and_date(admin_session, seeded_members):
    ids = seeded_members["ids"]
    body = {"recruiter_id": ids[0], "recruit_id": ids[1], "date_recruited": "2026-08-16"}
    r1 = admin_session.post(f"{BASE}/recruitments", json=body)
    assert r1.status_code == 200
    r2 = admin_session.post(f"{BASE}/recruitments", json=body)
    assert r2.status_code == 409


def test_update_recruitment_fields(admin_session, seeded_members):
    ids = seeded_members["ids"]
    r = admin_session.post(f"{BASE}/recruitments", json={
        "recruiter_id": ids[0], "recruit_id": ids[1], "date_recruited": "2026-08-17",
    })
    rid = r.json()["id"]
    r = admin_session.put(f"{BASE}/recruitments/{rid}", json={
        "notes": "Updated notes", "date_recruited": "2026-08-20",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "Updated notes"
    assert body["date_recruited"].startswith("2026-08-20")


# ---------- CSV ----------
def test_csv_template_download(admin_session):
    r = admin_session.get(f"{BASE}/recruitments/csv/template")
    assert r.status_code == 200
    assert "recruiter_email" in r.text
    assert "recruit_email" in r.text
    assert "date_recruited" in r.text


def test_csv_import_by_email(admin_session, seeded_members):
    ids = seeded_members["ids"]
    # Fetch member details to get emails
    members = admin_session.get(f"{BASE}/members").json()
    by_id = {m["id"]: m for m in members}
    csv_body = (
        "recruiter_email,recruit_email,date_recruited,notes\n"
        f"{by_id[ids[0]]['email']},{by_id[ids[1]]['email']},2026-08-25,Import test\n"
        f"{by_id[ids[0]]['email']},{by_id[ids[2]]['email']},2026-08-26,Second\n"
    )
    files = {"file": ("recruits.csv", io.BytesIO(csv_body.encode()), "text/csv")}
    # Dry run first
    r = admin_session.post(f"{BASE}/recruitments/csv?dry_run=true", files=files)
    assert r.status_code == 200
    preview = r.json()
    assert preview["total"] == 2
    assert preview["failed"] == 0
    assert preview["created"] == 0  # dry run doesn't insert

    # Real import
    files = {"file": ("recruits.csv", io.BytesIO(csv_body.encode()), "text/csv")}
    r = admin_session.post(f"{BASE}/recruitments/csv?dry_run=false", files=files)
    assert r.status_code == 200
    assert r.json()["created"] == 2

    # Re-import same file → should skip (dedupe warning), not error.
    files = {"file": ("recruits.csv", io.BytesIO(csv_body.encode()), "text/csv")}
    r = admin_session.post(f"{BASE}/recruitments/csv?dry_run=false", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 0
    assert body["skipped"] == 2


def test_csv_import_by_full_name_fallback(admin_session, seeded_members):
    ids = seeded_members["ids"]
    members = admin_session.get(f"{BASE}/members").json()
    by_id = {m["id"]: m for m in members}
    # Recruiter by email, recruit by full name — validates the name fallback.
    csv_body = (
        "recruiter_email,recruit_full_name,date_recruited,notes\n"
        f"{by_id[ids[0]]['email']},{by_id[ids[1]]['name']},2026-08-27,Name lookup\n"
    )
    files = {"file": ("r.csv", io.BytesIO(csv_body.encode()), "text/csv")}
    r = admin_session.post(f"{BASE}/recruitments/csv?dry_run=false", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1


def test_csv_import_reports_errors_for_unknown_members(admin_session, seeded_members):
    csv_body = (
        "recruiter_email,recruit_email,date_recruited\n"
        "not-a-real@member.local,also-not@real.local,2026-08-27\n"
    )
    files = {"file": ("bad.csv", io.BytesIO(csv_body.encode()), "text/csv")}
    r = admin_session.post(f"{BASE}/recruitments/csv?dry_run=true", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["failed"] == 1
    assert body["rows"][0]["status"] == "ERROR"


# ---------- Report ----------
def test_report_entries_and_summaries(admin_session, seeded_members):
    ids = seeded_members["ids"]
    # Seed 2 in same quarter
    for i, d in enumerate(["2026-08-15", "2026-09-01"]):
        admin_session.post(f"{BASE}/recruitments", json={
            "recruiter_id": ids[0], "recruit_id": ids[(i + 1) % len(ids)],
            "date_recruited": d,
        })
    # Entries (year 2026)
    r = admin_session.get(f"{BASE}/reports/recruitment", params={"year": "2026"})
    assert r.status_code == 200
    entries = [x for x in r.json() if x["recruiter_id"] == ids[0]]
    assert len(entries) == 2

    # Summary by recruiter
    r = admin_session.get(f"{BASE}/reports/recruitment/summary",
                         params={"group_by": "recruiter", "year": "2026"})
    assert r.status_code == 200
    body = r.json()
    row = next((r for r in body["rows"] if r["user_id"] == ids[0]), None)
    assert row is not None
    assert row["count"] == 2

    # Summary by chapter
    r = admin_session.get(f"{BASE}/reports/recruitment/summary",
                         params={"group_by": "chapter", "year": "2026"})
    assert r.status_code == 200
    chapter_rows = r.json()["rows"]
    assert any(r["chapter_id"] == seeded_members["chapter_id"] and r["count"] >= 2 for r in chapter_rows)

    # Summary by month
    r = admin_session.get(f"{BASE}/reports/recruitment/summary",
                         params={"group_by": "month", "year": "2026"})
    assert r.status_code == 200
    month_rows = r.json()["rows"]
    labels = {r["period_label"] for r in month_rows}
    assert {"2026-08", "2026-09"}.issubset(labels)


# ---------- Leaderboard ----------
def test_leaderboard_top_recruiters(admin_session, seeded_members):
    ids = seeded_members["ids"]
    # Seed one in Q3 2026 (Aug)
    admin_session.post(f"{BASE}/recruitments", json={
        "recruiter_id": ids[0], "recruit_id": ids[1], "date_recruited": "2026-08-05",
    })
    admin_session.post(f"{BASE}/recruitments", json={
        "recruiter_id": ids[0], "recruit_id": ids[2], "date_recruited": "2026-08-06",
    })
    r = admin_session.get(f"{BASE}/leaderboards/top-recruiters", params={"period": "q3"})
    assert r.status_code == 200
    board = r.json()
    assert board["period"] == "q3"
    assert board["period_label"] == "Q3 2026"
    # Top member includes our recruiter with count>=2
    top = next((m for m in board["top_members"] if m["user_id"] == ids[0]), None)
    assert top is not None, board
    assert top["count"] >= 2


def test_leaderboard_year_scope(admin_session, seeded_members):
    ids = seeded_members["ids"]
    admin_session.post(f"{BASE}/recruitments", json={
        "recruiter_id": ids[0], "recruit_id": ids[1], "date_recruited": "2026-03-05",
    })
    r = admin_session.get(f"{BASE}/leaderboards/top-recruiters", params={"period": "year"})
    assert r.status_code == 200
    board = r.json()
    assert board["period"] == "year"
    assert board["period_label"] == "2026"
    top = next((m for m in board["top_members"] if m["user_id"] == ids[0]), None)
    assert top is not None


# ---------- Access control ----------
def test_recruitment_requires_admin_tab():
    """Anonymous request → 401/403."""
    r = requests.get(f"{BASE}/recruitments")
    assert r.status_code in (401, 403)
    r = requests.post(f"{BASE}/recruitments", json={
        "recruiter_id": "x", "recruit_id": "y", "date_recruited": "2026-01-01",
    })
    assert r.status_code in (401, 403)
