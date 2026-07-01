"""Iteration 97 — Personnel Data Brief download fixes.

User-reported bugs in this iteration:
  1. Downloaded detailed PDF was missing Personal Data + Organization sections
     (they showed up on-screen but were absent from the PDF).
  2. Assignment History was empty in the download because the code was reading
     `m.get("assignments")` instead of the real field `assignment_history`,
     and each entry was being read with the wrong sub-keys.
  3. The one-pager didn't fill the landscape letter page vertically.
  4. On-screen preview showed empty navy bars ("black lines") instead of
     section titles because the `OrbTile` component destructured a `title`
     prop but every caller passed `tileTitle`.

Bugs 1-3 are backend concerns and this file exercises them via PDF text
extraction. Bug 4 is frontend-only and was verified via screenshot.
"""
import os

import pytest
import requests
from pypdf import PdfReader
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PWD = "Member123!"
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PWD = "Admin123!"

_db = None


def _login(email, pwd):
    return requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}).json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _extract(pdf_bytes):
    from io import BytesIO
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf_bytes)).pages)


def _get_db():
    global _db
    if _db is None:
        _db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "clubhaven_db")]
    return _db


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def member_id():
    return _get_db().users.find_one({"email": MEMBER_EMAIL})["id"]


@pytest.fixture(scope="module", autouse=True)
def _seed_assignment_history(member_id):
    """Ensure the member has at least 3 assignment_history entries so bug #2
    (empty assignments in the download) is actually testable. Idempotent."""
    _get_db().users.update_one(
        {"id": member_id},
        {"$set": {"assignment_history": [
            {"duty_title": "Chapter President", "chapter_name": "Texas", "rank": "President",
             "state": "TX", "location": "Austin", "start_date": "2024-03-01",
             "end_date": None, "is_current": True},
            {"duty_title": "Vice President", "chapter_name": "Texas", "rank": "VP",
             "state": "TX", "location": "Austin", "start_date": "2023-01-15",
             "end_date": "2024-02-28", "is_current": False},
            {"duty_title": "Treasurer", "chapter_name": "Florida", "rank": "Officer",
             "state": "FL", "location": "Miami", "start_date": "2022-01-01",
             "end_date": "2022-12-31", "is_current": False},
        ]}},
    )


def test_bug1_detailed_pdf_includes_personal_data_and_organization(admin_token, member_id):
    """The detailed download must include §I Personal Data and §II Organization —
    they were showing on-screen but missing from the PDF prior to iter97."""
    r = requests.get(f"{BASE}/reports/personnel-brief/{member_id}/pdf?detailed=true", headers=_h(admin_token))
    assert r.status_code == 200
    text = _extract(r.content)
    # Must appear in the DETAIL section on page 2+, not just the one-pager tile.
    assert "SECTION I" in text and "PERSONAL DATA" in text
    assert "SECTION II" in text and "ORGANIZATION" in text
    # Signature fields that the on-screen preview shows but the download used
    # to omit.
    assert "Birthdate" in text
    assert "Country" in text
    assert "Chapter" in text
    assert "Tier" in text
    assert "Renewal" in text


def test_bug2_detailed_pdf_includes_assignment_history_rows(admin_token, member_id):
    """Assignment history section must contain the seeded rows. Prior code
    read `m.get("assignments")` (wrong key) and used wrong sub-fields
    (`title`, `date_started`, `duties`) so the section was always empty."""
    r = requests.get(f"{BASE}/reports/personnel-brief/{member_id}/pdf?detailed=true", headers=_h(admin_token))
    assert r.status_code == 200
    text = _extract(r.content)
    assert "SECTION XI" in text and "ASSIGNMENT HISTORY" in text
    # Every seeded duty must show up.
    assert "Chapter President" in text
    assert "Vice President" in text
    assert "Treasurer" in text
    # Their metadata should be present.
    assert "Texas" in text
    assert "Florida" in text
    assert "2024-03-01" in text  # start of current assignment
    assert "Present" in text     # current assignment marker


def test_bug3_one_pager_fits_exactly_one_page(admin_token, member_id):
    """The one-pager must still be one page after the vertical-fill changes."""
    r = requests.get(f"{BASE}/reports/personnel-brief/{member_id}/pdf?detailed=false", headers=_h(admin_token))
    assert r.status_code == 200
    from io import BytesIO
    pdf = PdfReader(BytesIO(r.content))
    assert len(pdf.pages) == 1, f"one-pager overflowed to {len(pdf.pages)} pages"
    p = pdf.pages[0]
    # Landscape letter: 11" wide x 8.5" tall.
    assert round(float(p.mediabox.width) / 72, 1) == 11.0
    assert round(float(p.mediabox.height) / 72, 1) == 8.5


def test_one_pager_titles_are_populated(admin_token, member_id):
    """Bug 4 is frontend-only, but the SAME data flows into the PDF via ORB
    tile titles — this asserts the section labels come through in the
    generated file, giving a cheap regression against future prop-rename
    accidents."""
    r = requests.get(f"{BASE}/reports/personnel-brief/{member_id}/pdf?detailed=false", headers=_h(admin_token))
    assert r.status_code == 200
    text = _extract(r.content)
    for section_label in [
        "PERSONAL DATA",
        "EDUCATION",
        "LANGUAGES",
        "AWARDS",
        "SERVICE STATISTICS",
    ]:
        assert section_label in text, f"missing tile title: {section_label}"
