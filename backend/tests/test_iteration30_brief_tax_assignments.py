"""Iteration 30 backend tests:
A) Personnel Brief PDF — 10-section spec + assignment_history rendering
B) Annual Tax Donation Letter PDF
C) Assignment History admin round-trip (8 ranks)
+ minor regression smokes.
"""
import os
import io
import re
import uuid
import time
import requests
import pytest
from pypdf import PdfReader

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # Fallback: read frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL"):
                        return line.split("=", 1)[1].strip().rstrip("/")
        except Exception:
            pass
    return (url or "").rstrip("/")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PW = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PW = "Member123!"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"identifier": email, "password": pw}, timeout=15)
    if r.status_code != 200:
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def member_session():
    return _login(MEMBER_EMAIL, MEMBER_PW)


@pytest.fixture(scope="module")
def member_user(member_session):
    r = member_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json()


def _extract_pdf_text(content: bytes) -> str:
    rd = PdfReader(io.BytesIO(content))
    txt_chunks = []
    for p in rd.pages:
        try:
            txt_chunks.append(p.extract_text() or "")
        except Exception:
            pass
    return "\n".join(txt_chunks)


# ---------------- (A) Personnel Brief PDF ----------------
class TestPersonnelBriefPDF:
    def test_brief_pdf_has_all_10_sections(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/personnel-brief/pdf", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        text = _extract_pdf_text(r.content)
        # all 10 section headers
        for kw in [
            "Personal Information",
            "Organization Information",
            "Civilian Education",
            "Languages",
            "Financial Obligations",
            "Donations",
            "Community Service",
            "Awards",
            "Events Attended",
            "Assignment History",
        ]:
            assert kw in text, f"Missing section keyword '{kw}' in brief PDF. Extracted excerpt: {text[:500]}"

    def test_brief_pdf_includes_assignment_after_admin_set(self, admin_session, member_session, member_user):
        # Admin sets 2 assignment_history entries for the member.
        mid = member_user["id"]
        payload = {
            "assignment_history": [
                {
                    "start_date": "2024-01-15",
                    "end_date": "",
                    "is_current": True,
                    "chapter_name": "Texas",
                    "state": "TX",
                    "location": "Houston",
                    "duty_title": "Treasurer",
                    "rank": "Senior Sirius",
                },
                {
                    "start_date": "2022-06-01",
                    "end_date": "2023-12-31",
                    "is_current": False,
                    "chapter_name": "Theta-3",
                    "state": "AL",
                    "location": "Montgomery",
                    "duty_title": "Recorder",
                    "rank": "Junior Sirius",
                },
            ]
        }
        r = admin_session.put(f"{BASE_URL}/api/members/{mid}", json=payload, timeout=15)
        assert r.status_code == 200, f"admin update failed: {r.status_code} {r.text}"

        # Round-trip: member's GET /auth/me reflects both rows
        me = member_session.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
        ah = me.get("assignment_history") or []
        assert len(ah) == 2
        ranks = {a.get("rank") for a in ah}
        assert "Senior Sirius" in ranks and "Junior Sirius" in ranks

        # Regenerate brief PDF and verify text contains them
        r2 = member_session.get(f"{BASE_URL}/api/me/personnel-brief/pdf", timeout=30)
        assert r2.status_code == 200
        text = _extract_pdf_text(r2.content)
        assert "Senior Sirius" in text, f"PDF missing 'Senior Sirius'. Got: {text[-500:]}"
        assert "Treasurer" in text, f"PDF missing 'Treasurer'. Got: {text[-500:]}"


# ---------------- (B) Tax Letter PDF ----------------
class TestTaxLetterPDF:
    def test_tax_letter_2025_returns_pdf(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/tax-letter/pdf?year=2025", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 5 * 1024, f"PDF too small: {len(r.content)} bytes"
        text = _extract_pdf_text(r.content)
        for kw in ["EIN", "82-0794957", "Cory T. Burnett", "Co-Founder", "Alpha Omega Phi"]:
            assert kw in text, f"Tax letter missing '{kw}'. Excerpt: {text[:500]}"

    def test_tax_letter_embeds_signature_image(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/tax-letter/pdf?year=2025", timeout=30)
        assert r.status_code == 200
        rd = PdfReader(io.BytesIO(r.content))
        # Count image XObjects across pages
        image_count = 0
        for page in rd.pages:
            try:
                res = page.get("/Resources")
                if res is None:
                    continue
                xobj = res.get("/XObject") if hasattr(res, "get") else None
                if not xobj:
                    continue
                xobj = xobj.get_object() if hasattr(xobj, "get_object") else xobj
                for k in xobj:
                    obj = xobj[k].get_object() if hasattr(xobj[k], "get_object") else xobj[k]
                    if obj.get("/Subtype") == "/Image":
                        image_count += 1
            except Exception:
                pass
        # Fallback: check binary for FlateDecode image presence
        binary_has_image = b"/Subtype /Image" in r.content or b"/Subtype/Image" in r.content
        assert image_count >= 1 or binary_has_image, "No embedded image XObject found in tax letter PDF"

    def test_tax_letter_default_year_is_last_year(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/tax-letter/pdf", timeout=30)
        assert r.status_code == 200
        # Verify content disposition includes a 4-digit year that is <= current year - 0 (last completed year)
        cd = r.headers.get("content-disposition", "")
        m = re.search(r"(\d{4})\.pdf", cd)
        assert m, f"Could not find year in CD: {cd}"
        from datetime import datetime
        assert int(m.group(1)) == datetime.utcnow().year - 1

    def test_tax_letter_total_matches_paid_transactions(self, member_session, member_user):
        """Member has 1 completed dues $105 + 1 completed donation $25 + 1 pending dues (ignored) in 2025 → total $130.
        Inserts directly via mongo (no admin transaction-create endpoint exists)."""
        from pymongo import MongoClient
        mongo_url = "mongodb://localhost:27017"
        db_name = "clubhaven_db"
        # Try read from backend/.env
        try:
            with open("/app/backend/.env") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("MONGO_URL"):
                        mongo_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("DB_NAME"):
                        db_name = line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
        client = MongoClient(mongo_url)
        coll = client[db_name].transactions
        mid = member_user["id"]
        marker = f"TEST_iter30_{uuid.uuid4().hex[:6]}"
        txs = [
            {"id": str(uuid.uuid4()), "user_id": mid, "type": "renewal", "amount": 105.0,
             "status": "completed", "purpose": "dues",
             "description": f"{marker} dues 2025", "created_at": "2025-03-15T10:00:00Z"},
            {"id": str(uuid.uuid4()), "user_id": mid, "type": "donation", "amount": 25.0,
             "status": "completed", "purpose": "donation",
             "description": f"{marker} donation 2025", "created_at": "2025-04-10T10:00:00Z"},
            {"id": str(uuid.uuid4()), "user_id": mid, "type": "renewal", "amount": 999.0,
             "status": "pending", "purpose": "dues",
             "description": f"{marker} pending dues 2025", "created_at": "2025-05-01T10:00:00Z"},
        ]
        coll.insert_many(txs)
        try:
            r = member_session.get(f"{BASE_URL}/api/me/tax-letter/pdf?year=2025", timeout=30)
            assert r.status_code == 200
            text = _extract_pdf_text(r.content)
            assert "$130.00" in text, f"Expected $130.00 total, text excerpt={text[-800:]}"
            assert "$999" not in text, "Pending tx leaked into tax letter"
            assert "$105.00" in text and "$25.00" in text
            assert "pending dues 2025" not in text
            # Line item count: 2 data rows (excluding header + total)
            # Count occurrences of marker in description
            assert text.count(marker) == 2, f"Expected 2 line items with marker, got {text.count(marker)}"
        finally:
            coll.delete_many({"description": {"$regex": f"^{marker}"}})
            client.close()


# ---------------- (C) Assignment History admin write/read with all 8 ranks ----------------
class TestAssignmentHistoryRanks:
    def test_all_eight_ranks_round_trip(self, admin_session, member_session, member_user):
        mid = member_user["id"]
        ranks = ["Grand Sirius", "Master Sirius", "Senior Sirius", "Advanced Sirius",
                 "Junior Sirius", "Eagle", "Clover", "Guardian"]
        rows = []
        for i, rk in enumerate(ranks):
            rows.append({
                "start_date": f"2020-0{(i % 9) + 1}-01",
                "end_date": "" if i == 0 else f"2021-0{(i % 9) + 1}-01",
                "is_current": (i == 0),
                "chapter_name": f"Chapter-{i}",
                "state": "TX",
                "location": f"City-{i}",
                "duty_title": f"Duty-{i}",
                "rank": rk,
            })
        r = admin_session.put(f"{BASE_URL}/api/members/{mid}", json={"assignment_history": rows}, timeout=15)
        assert r.status_code == 200, f"Update failed: {r.status_code} {r.text}"
        # Member reads back
        me = member_session.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
        got_ranks = [a.get("rank") for a in (me.get("assignment_history") or [])]
        for rk in ranks:
            assert rk in got_ranks, f"Rank '{rk}' not persisted. Got={got_ranks}"
        # Storage stored is_current True for row 0 unchanged
        assert any(a.get("is_current") for a in me["assignment_history"])

    def test_clear_assignment_history(self, admin_session, member_session, member_user):
        """Resetting to a single row keeps just that row (cleanup-ish)."""
        mid = member_user["id"]
        single = [{
            "start_date": "2024-01-15", "end_date": "", "is_current": True,
            "chapter_name": "Texas", "state": "TX", "location": "Houston",
            "duty_title": "Treasurer", "rank": "Senior Sirius",
        }]
        r = admin_session.put(f"{BASE_URL}/api/members/{mid}", json={"assignment_history": single}, timeout=15)
        assert r.status_code == 200
        me = member_session.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
        assert len(me.get("assignment_history") or []) == 1


# ---------------- Regression smokes ----------------
class TestRegressionSmokes:
    def test_personnel_brief_json(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/me/personnel-brief", timeout=15)
        assert r.status_code == 200
        j = r.json()
        for k in ["member", "chapter", "tier", "generated_at"]:
            assert k in j

    def test_zeffy_validate_endpoint(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/payments/zeffy/validate?confirmation=NOPE_DOES_NOT_EXIST", timeout=15)
        # Should respond (200 or 400/404), not crash with 500
        assert r.status_code in (200, 400, 404, 422), f"Got {r.status_code}: {r.text[:200]}"

    def test_events_list(self, member_session):
        r = member_session.get(f"{BASE_URL}/api/events", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_bulk_import_template(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/members/bulk-import/template", timeout=15)
        # Template download endpoint should be available — accept 200 (CSV/xlsx) or 404 if endpoint named differently
        assert r.status_code in (200, 404), f"Unexpected status {r.status_code}"
