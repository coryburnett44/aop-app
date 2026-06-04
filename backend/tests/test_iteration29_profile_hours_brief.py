"""Iteration 29 backend tests.

Coverage:
 1. Profile extras: marital_status, languages[], civilian_degrees[] via PUT /members/me.
 2. Hours review: status flip + hours adjustment + re-edit + audit fields + status='pending' revert.
 3. /me/personnel-brief returns the same shape as admin /reports/personnel-brief/{user_id} for the caller.
 4. /me/personnel-brief/pdf returns application/pdf attachment > 1 KB.
 5. Member cannot call /reports/personnel-brief/{other_user_id}.
 6. Regression smoke: /auth/login (email & username), /events list, /payments/zeffy/validate.
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"


# ---------- session fixtures ----------

def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="session")
def member_session():
    return _login(MEMBER_EMAIL, MEMBER_PASS)


@pytest.fixture(scope="session")
def member_id(member_session):
    r = member_session.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 200
    return r.json()["id"]


# ---------- 1. Profile extras ----------

class TestProfileExtras:
    def test_put_members_me_persists_marital_languages_degrees(self, member_session):
        payload = {
            "marital_status": "Married",
            "languages": [
                {"language": "English", "speaking": "Native", "reading": "Native", "writing": "Native", "year_accomplished": 1990},
                {"language": "Spanish", "speaking": "Conversational", "reading": "Conversational", "writing": "Limited", "year_accomplished": 2010},
            ],
            "civilian_degrees": [
                {"degree_level": "Bachelors", "degree_type": "BS", "field_of_study": "Computer Science",
                 "institution": "State U", "graduation_month": 5, "graduation_year": 2014},
            ],
        }
        r = member_session.put(f"{API}/members/me", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["marital_status"] == "Married"
        assert len(out["languages"]) == 2
        assert out["languages"][0]["language"] == "English"
        assert out["languages"][0]["speaking"] == "Native"
        assert out["languages"][0]["year_accomplished"] == 1990
        assert len(out["civilian_degrees"]) == 1
        d0 = out["civilian_degrees"][0]
        assert d0["degree_level"] == "Bachelors"
        assert d0["degree_type"] == "BS"
        assert d0["field_of_study"] == "Computer Science"
        assert d0["institution"] == "State U"
        assert d0["graduation_month"] == 5
        assert d0["graduation_year"] == 2014

        # Verify auth/me round-trip
        me = member_session.get(f"{API}/auth/me", timeout=15).json()
        assert me["marital_status"] == "Married"
        assert len(me["languages"]) == 2
        assert len(me["civilian_degrees"]) == 1

    def test_server_does_not_cap_languages_or_degrees(self, member_session):
        """Server should NOT enforce 3-langs / 5-degrees caps (UI-only)."""
        payload = {
            "languages": [{"language": f"Lang{i}", "speaking": "Limited", "reading": "Limited", "writing": "Limited"} for i in range(5)],
            "civilian_degrees": [{"degree_level": "Bachelors", "degree_type": "BS", "field_of_study": f"F{i}", "institution": "U", "graduation_month": 1, "graduation_year": 2000+i} for i in range(7)],
        }
        r = member_session.put(f"{API}/members/me", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        out = r.json()
        assert len(out["languages"]) == 5
        assert len(out["civilian_degrees"]) == 7

    def test_clear_extras(self, member_session):
        r = member_session.put(f"{API}/members/me",
                               json={"marital_status": "", "languages": [], "civilian_degrees": []},
                               timeout=15)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out.get("marital_status", "") == ""
        assert out.get("languages") in ([], None) or out["languages"] == []
        assert out.get("civilian_degrees") in ([], None) or out["civilian_degrees"] == []


# ---------- 2. Hours adjust + audit ----------

class TestHoursAdjustAndRevert:
    @pytest.fixture(scope="class")
    def hours_id(self, member_session):
        """Create a fresh hours entry to review."""
        body = {
            "date": "2025-12-01",
            "hours": 5.0,
            "activity": "TEST_iter29 cleanup",
            "agency_name": "TEST_iter29 agency",
            "event_type": "other",
            "host_name": "TEST Host",
            "host_email": "test_host@example.com",
            "host_phone": "5555550100",
        }
        r = member_session.post(f"{API}/hours", json=body, timeout=15)
        assert r.status_code == 200, r.text
        hid = r.json()["id"]
        yield hid
        # Teardown
        try:
            member_session.delete(f"{API}/hours/{hid}", timeout=15)
        except Exception:
            pass

    def test_approve_with_hours_adjustment_stamps_audit(self, admin_session, hours_id):
        r = admin_session.put(
            f"{API}/hours/{hours_id}/review",
            json={"status": "approved", "hours": 4.5, "note": "Trimmed by 0.5"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["status"] == "approved"
        assert out["hours"] == 4.5
        assert out.get("hours_adjusted_by_name")
        assert out.get("hours_adjusted_at")

    def test_re_edit_hours_post_approval(self, admin_session, hours_id):
        r = admin_session.put(
            f"{API}/hours/{hours_id}/review",
            json={"status": "approved", "hours": 6.0},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["status"] == "approved"
        assert out["hours"] == 6.0
        assert out.get("hours_adjusted_by_name")

    def test_revert_to_pending(self, admin_session, hours_id):
        r = admin_session.put(
            f"{API}/hours/{hours_id}/review",
            json={"status": "pending"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["status"] == "pending"


# ---------- 3 & 4. Personnel brief ----------

class TestMyPersonnelBrief:
    def test_me_personnel_brief_shape(self, member_session, admin_session, member_id):
        r_member = member_session.get(f"{API}/me/personnel-brief", timeout=20)
        assert r_member.status_code == 200, r_member.text
        data = r_member.json()
        # Required keys
        for k in ["member", "hours", "events", "checkins", "rsvps", "transactions",
                  "awards", "awards_count", "approved_hours", "pending_hours",
                  "events_count", "total_paid", "generated_at"]:
            assert k in data, f"Missing key '{k}' in /me/personnel-brief response"
        assert data["member"]["id"] == member_id

        # Compare shape with admin endpoint for same user
        r_admin = admin_session.get(f"{API}/reports/personnel-brief/{member_id}", timeout=20)
        assert r_admin.status_code == 200
        assert set(data.keys()) == set(r_admin.json().keys()), \
            f"Shape mismatch. member: {set(data.keys())} admin: {set(r_admin.json().keys())}"

    def test_me_personnel_brief_pdf(self, member_session):
        r = member_session.get(f"{API}/me/personnel-brief/pdf", timeout=30)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"Expected PDF, got {ct}"
        assert len(r.content) > 1024, f"PDF too small: {len(r.content)} bytes"
        assert r.content[:4] == b"%PDF", "PDF header missing"
        cd = r.headers.get("content-disposition", "").lower()
        assert "attachment" in cd or "inline" in cd or "filename" in cd

    def test_member_cannot_access_other_users_brief(self, member_session, admin_session):
        # Get admin id
        me_admin = admin_session.get(f"{API}/auth/me", timeout=15).json()
        admin_id = me_admin["id"]
        r = member_session.get(f"{API}/reports/personnel-brief/{admin_id}", timeout=15)
        assert r.status_code in (401, 403), f"Member should not access other user's brief; got {r.status_code}"


# ---------- 6. Regression smokes ----------

class TestRegressionSmokes:
    def test_login_with_email(self):
        r = requests.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASS}, timeout=15)
        assert r.status_code == 200

    def test_login_with_username(self):
        # use admin's known username if available, fall back to email
        s = _login(ADMIN_EMAIL, ADMIN_PASS)
        me = s.get(f"{API}/auth/me", timeout=15).json()
        uname = me.get("username")
        if not uname:
            pytest.skip("admin has no username configured")
        r = requests.post(f"{API}/auth/login", json={"email": uname, "password": ADMIN_PASS}, timeout=15)
        assert r.status_code == 200, r.text

    def test_events_list_smoke(self, member_session):
        r = member_session.get(f"{API}/events", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_zeffy_validate_smoke(self, member_session):
        r = member_session.get(
            f"{API}/payments/zeffy/validate",
            params={"confirmation": "RCT-1234-5678"},
            timeout=15,
        )
        # Endpoint exists; accepts either valid (200) or 4xx for unknown receipt.
        assert r.status_code in (200, 400, 404, 409, 422), r.text
