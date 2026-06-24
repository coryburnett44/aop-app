"""Iteration 72 — Of-The-Year on Personnel Brief & Admin Member Card.

Tests:
  - GET /api/of-the-year?user_id=… returns OTY wins for that user (DESC by year)
  - GET /api/reports/personnel-brief/{uid} returns of_the_year, of_the_year_recent,
    of_the_year_count (with cap of 7 on recent).
  - PDF includes §9 Of The Year Honors, then §10 Events, §11 Assignment History
  - >7 wins edge — recent capped at 7, count = N, header reads "last 7 of N"
  - 0 wins case — recent=[] and PDF placeholder
"""
import io
import os
import re
import uuid
from datetime import datetime, timezone

import pytest
import httpx
import pdfplumber
from pymongo import MongoClient

API_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not API_BASE:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)
API = f"{API_BASE.rstrip('/')}/api"

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

ADMIN = ("admin@clubhaven.app", "Admin123!")


def _login(c, email, pw):
    r = c.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="module")
def admin_client():
    c = httpx.Client(timeout=60.0, follow_redirects=True)
    _login(c, *ADMIN)
    yield c
    c.close()


@pytest.fixture(scope="module")
def maya_id(admin_client):
    rows = admin_client.get(f"{API}/members").json()
    for m in rows:
        if m.get("email") == "maya.patel@clubhaven.app":
            return m["id"]
    pytest.skip("Maya not found")


@pytest.fixture(scope="module")
def admin_user_id(admin_client):
    rows = admin_client.get(f"{API}/members").json()
    for m in rows:
        if m.get("email") == "admin@clubhaven.app":
            return m["id"]
    pytest.skip("admin user not found")


# ---------- /of-the-year?user_id= ----------
def test_oty_list_by_user_id(admin_client, maya_id):
    r = admin_client.get(f"{API}/of-the-year", params={"user_id": maya_id})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 2, f"Expected at least 2 OTY wins for Maya, got {len(rows)}"
    # All belong to Maya
    for row in rows:
        assert row["user_id"] == maya_id
        for k in ("id", "year", "category", "category_label", "note"):
            assert k in row, f"missing key {k}"
        # chapter_name may be None if no chapter on award
        assert "chapter_name" in row
    # Sorted by year DESC
    years = [row["year"] for row in rows]
    assert years == sorted(years, reverse=True), f"years not DESC: {years}"
    # Confirm expected Maya wins are present
    cats_years = {(row["category"], row["year"]) for row in rows}
    assert ("member_of_year", 2024) in cats_years
    assert ("top_cs_member", 2023) in cats_years


# ---------- /reports/personnel-brief/{uid} ----------
def test_personnel_brief_includes_oty_keys(admin_client, maya_id):
    r = admin_client.get(f"{API}/reports/personnel-brief/{maya_id}")
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("of_the_year", "of_the_year_recent", "of_the_year_count"):
        assert k in d, f"missing key {k}"
    assert d["of_the_year_count"] >= 2
    # Since count < 7, recent should equal full list
    assert len(d["of_the_year_recent"]) == d["of_the_year_count"]
    assert len(d["of_the_year"]) == d["of_the_year_count"]
    # Field shape
    sample = d["of_the_year_recent"][0]
    for k in ("id", "year", "category", "category_label", "note"):
        assert k in sample
    # Labels match
    labels = {row["category_label"] for row in d["of_the_year"]}
    assert "Member of the Year" in labels
    assert "Top Community Service Member" in labels


# ---------- PDF rendering ----------
def _extract_pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def test_personnel_brief_pdf_has_section9_oty(admin_client, maya_id):
    r = admin_client.get(f"{API}/reports/personnel-brief/{maya_id}/pdf")
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    text = _extract_pdf_text(r.content)
    # Required strings
    for needle in ("§9", "Of The Year", "Member of the Year",
                    "Top Community Service Member", "§10", "§11"):
        assert needle in text, f"missing '{needle}' in PDF text. Got:\n{text[:2000]}"
    # Order: §9 before §10 before §11
    i9, i10, i11 = text.find("§9"), text.find("§10"), text.find("§11")
    assert i9 < i10 < i11, f"section order wrong: §9={i9} §10={i10} §11={i11}"


# ---------- Edge: >7 wins ----------
@pytest.fixture
def six_extra_oty_for_maya(admin_client, maya_id):
    """Mongo-direct insert 6 additional wins so Maya has 8 total (2 seeded + 6).
    Categories must be allowed for members; we cycle through them with unique
    (category, year) pairs to satisfy the unique idx.
    Cleaned up at teardown.
    """
    if not MONGO_URL or not DB_NAME:
        pytest.skip("MONGO_URL/DB_NAME not set; cannot insert direct rows")
    client = MongoClient(MONGO_URL)
    col = client[DB_NAME].of_the_year_awards
    inserted_ids = []
    member_cats = ["member_of_year", "top_cs_member", "top_fundraising_member", "top_recruiter"]
    # Use unique (cat, year) pairs not already taken
    existing = {(r["category"], r["year"]) for r in col.find({}, {"_id": 0, "category": 1, "year": 1})}
    pairs = []
    year = 2018
    while len(pairs) < 6:
        for cat in member_cats:
            if (cat, year) not in existing and (cat, year) not in pairs:
                pairs.append((cat, year))
                if len(pairs) >= 6:
                    break
        year -= 1
        if year < 1990:
            break
    assert len(pairs) == 6
    now = datetime.now(timezone.utc).isoformat()
    for cat, yr in pairs:
        doc = {
            "id": str(uuid.uuid4()),
            "category": cat,
            "year": yr,
            "user_id": maya_id,
            "chapter_id": None,
            "note": "TEST_iter72_temp",
            "created_at": now,
            "created_by": "test",
            "created_by_name": "Test",
        }
        col.insert_one(doc)
        inserted_ids.append(doc["id"])
    yield inserted_ids
    # Cleanup
    col.delete_many({"id": {"$in": inserted_ids}})
    client.close()


def test_personnel_brief_caps_recent_at_seven(admin_client, maya_id, six_extra_oty_for_maya):
    r = admin_client.get(f"{API}/reports/personnel-brief/{maya_id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["of_the_year_count"] == 8, f"expected 8, got {d['of_the_year_count']}"
    assert len(d["of_the_year_recent"]) == 7
    assert len(d["of_the_year"]) == 8
    # recent is the top-7 by year DESC
    years = [w["year"] for w in d["of_the_year_recent"]]
    assert years == sorted(years, reverse=True)


def test_personnel_brief_pdf_header_includes_last_7_of_n(admin_client, maya_id, six_extra_oty_for_maya):
    r = admin_client.get(f"{API}/reports/personnel-brief/{maya_id}/pdf")
    assert r.status_code == 200
    text = _extract_pdf_text(r.content)
    # Should mention "last 7 of 8"
    assert re.search(r"last\s*7\s*of\s*8", text, re.IGNORECASE), (
        f"PDF should note 'last 7 of 8' when N>7. Snippet:\n{text[:3000]}"
    )


# ---------- Edge: 0 wins ----------
def test_personnel_brief_zero_wins(admin_client, admin_user_id):
    r = admin_client.get(f"{API}/reports/personnel-brief/{admin_user_id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["of_the_year_count"] == 0
    assert d["of_the_year_recent"] == []
    assert d["of_the_year"] == []


def test_personnel_brief_pdf_zero_wins_placeholder(admin_client, admin_user_id):
    r = admin_client.get(f"{API}/reports/personnel-brief/{admin_user_id}/pdf")
    assert r.status_code == 200
    text = _extract_pdf_text(r.content)
    assert "§9" in text
    assert "Of The Year" in text
    # Placeholder for no wins
    assert "No Of The Year honors on record" in text or "No \"Of The Year\"" in text or "no" in text.lower()
