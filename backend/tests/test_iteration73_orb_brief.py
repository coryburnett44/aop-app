"""Iteration 73 — RSVP ticket_type fallback, OTY chapter context, ORB redesign.

Covers:
  Bug A — /api/reports/rsvps fills ticket_type from RSVP doc when no checkin.
  Bug B — Personnel Brief OTY rows always have a chapter_name (waterfall).
  Enh C — PUT/POST /api/of-the-year accepts chapter_id for MEMBER categories.
  Enh D — Personnel Brief PDF is landscape & ORB-styled (SECTION I—XI in ALL CAPS).
"""
import io
import os
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
def chapters(admin_client):
    r = admin_client.get(f"{API}/chapters")
    assert r.status_code == 200
    return r.json()


# ---------------- Bug A: RSVP ticket_type fallback ----------------
class TestRsvpsTicketTypeFallback:
    def test_rsvps_report_includes_ticket_type_from_rsvp(self, admin_client, maya_id):
        # Create a future event so RSVP is allowed
        future_iso = "2099-12-31T18:00:00Z"
        ev_resp = admin_client.post(f"{API}/events", json={
            "title": "TEST_iter73_vip_event",
            "description": "test",
            "start_at": future_iso,
            "end_at": "2099-12-31T20:00:00Z",
            "location": "TEST",
            "category": "social",
        })
        assert ev_resp.status_code == 200, ev_resp.text
        ev = ev_resp.json()
        ev_id = ev["id"]

        # Directly insert a maya RSVP with ticket_type='vip' via mongo
        client = MongoClient(MONGO_URL)
        col = client[DB_NAME].rsvps
        rsvp_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        col.insert_one({
            "id": rsvp_id,
            "event_id": ev_id,
            "user_id": maya_id,
            "user_name": "Maya Patel",
            "guests": [],
            "ticket_type": "vip",
            "created_at": now,
        })
        try:
            r = admin_client.get(f"{API}/reports/rsvps", params={"event_id": ev_id})
            assert r.status_code == 200, r.text
            rows = r.json()
            target = [x for x in rows if x["rsvp_id"] == rsvp_id]
            assert len(target) == 1, f"RSVP not in report: {rows}"
            row = target[0]
            assert row["ticket_type"] == "vip", (
                f"Expected ticket_type='vip' from RSVP fallback, got {row['ticket_type']!r}"
            )
            assert row["checked_in_at"] is None
        finally:
            col.delete_one({"id": rsvp_id})
            admin_client.delete(f"{API}/events/{ev_id}")
            client.close()


# ---------------- Enh C: OTY chapter_id on member categories ----------------
class TestOtyChapterContextOnMember:
    def test_post_member_oty_with_chapter_id_succeeds(self, admin_client, maya_id, chapters):
        chap_id = chapters[0]["id"]
        body = {
            "category": "top_recruiter",
            "year": 2017,
            "user_id": maya_id,
            "chapter_id": chap_id,
            "note": "TEST_iter73",
        }
        r = admin_client.post(f"{API}/of-the-year", json=body)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["chapter_id"] == chap_id, (
            f"chapter_id not stored: {d}"
        )
        assert d["chapter_name"] == chapters[0]["name"]
        admin_client.delete(f"{API}/of-the-year/{d['id']}")

    def test_put_member_oty_sets_chapter_id(self, admin_client, maya_id, chapters):
        # Create one without chapter
        body = {
            "category": "top_fundraising_member",
            "year": 2016,
            "user_id": maya_id,
            "note": "TEST_iter73",
        }
        c = admin_client.post(f"{API}/of-the-year", json=body)
        assert c.status_code == 200, c.text
        aid = c.json()["id"]
        try:
            chap_id = chapters[0]["id"]
            u = admin_client.put(
                f"{API}/of-the-year/{aid}", json={"chapter_id": chap_id}
            )
            assert u.status_code == 200, (
                f"PUT should accept chapter_id for member cat; got {u.status_code} {u.text}"
            )
            assert u.json()["chapter_id"] == chap_id

            # Personnel Brief should reflect this chapter
            pb = admin_client.get(f"{API}/reports/personnel-brief/{maya_id}").json()
            row = next((r for r in pb["of_the_year"] if r["id"] == aid), None)
            assert row is not None
            assert row["chapter_name"] == chapters[0]["name"], (
                f"Brief OTY chapter_name {row['chapter_name']!r} != explicit set "
                f"{chapters[0]['name']!r}"
            )
        finally:
            admin_client.delete(f"{API}/of-the-year/{aid}")

    def test_put_member_oty_invalid_chapter_404(self, admin_client, maya_id):
        body = {
            "category": "top_recruiter",
            "year": 2015,
            "user_id": maya_id,
            "note": "TEST_iter73",
        }
        c = admin_client.post(f"{API}/of-the-year", json=body)
        aid = c.json()["id"]
        try:
            u = admin_client.put(
                f"{API}/of-the-year/{aid}",
                json={"chapter_id": "no-such-chapter-id"},
            )
            assert u.status_code == 404
        finally:
            admin_client.delete(f"{API}/of-the-year/{aid}")


# ---------------- Bug B: Personnel Brief OTY chapter_name never empty ----------------
class TestPersonnelBriefOtyChapterResolution:
    def test_oty_chapter_name_auto_resolved_when_unset(self, admin_client, maya_id):
        body = {
            "category": "member_of_year",
            "year": 2022,
            "user_id": maya_id,
            "note": "TEST_iter73_autoresolve",
        }
        c = admin_client.post(f"{API}/of-the-year", json=body)
        if c.status_code == 400:
            # Already a winner for 2022 — pick another year
            for yr in (2021, 2020, 2019, 2014, 2013, 2012):
                body["year"] = yr
                c = admin_client.post(f"{API}/of-the-year", json=body)
                if c.status_code == 200:
                    break
        assert c.status_code == 200, c.text
        aid = c.json()["id"]
        assert c.json().get("chapter_id") in (None, "")
        try:
            pb = admin_client.get(f"{API}/reports/personnel-brief/{maya_id}").json()
            row = next((r for r in pb["of_the_year"] if r["id"] == aid), None)
            assert row is not None, "newly created OTY not in brief"
            assert row["chapter_name"], (
                f"chapter_name must be non-empty (auto resolved) — got "
                f"{row['chapter_name']!r}"
            )
        finally:
            admin_client.delete(f"{API}/of-the-year/{aid}")


# ---------------- Enh D: ORB landscape PDF ----------------
class TestPersonnelBriefOrbPdf:
    def test_pdf_page1_landscape_and_orb_sections(self, admin_client, maya_id):
        r = admin_client.get(f"{API}/reports/personnel-brief/{maya_id}/pdf")
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            assert len(pdf.pages) >= 2, "Expected ORB summary + detail pages"
            p1 = pdf.pages[0]
            # Landscape letter: 792 x 612
            assert round(p1.width) == 792 and round(p1.height) == 612, (
                f"Page 1 not landscape letter: {p1.width}x{p1.height}"
            )
            p1_text = (p1.extract_text() or "").upper()
            for needle in (
                "SECTION I",
                "PERSONAL DATA",
                "SECTION IV",
                "AWARDS",
                "SECTION VI",
                "ASSIGNMENT HISTORY",
                "SECTION VII",
                "SERVICE STATISTICS",
                "MAYA PATEL",
            ):
                assert needle in p1_text, f"missing {needle!r} on page 1"

            # Detail pages: combine all extra pages
            detail = "\n".join((p.extract_text() or "") for p in pdf.pages[1:]).upper()
            for needle in (
                "SECTION III",
                "CIVILIAN EDUCATION",
                "SECTION XI",
                "ASSIGNMENT HISTORY (FULL)",
            ):
                assert needle in detail, f"missing {needle!r} on detail pages"

    def test_pdf_includes_oty_section_v(self, admin_client, maya_id):
        r = admin_client.get(f"{API}/reports/personnel-brief/{maya_id}/pdf")
        assert r.status_code == 200
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages).upper()
        assert "SECTION V" in text and "OF THE YEAR" in text
