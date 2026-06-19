"""Iteration 51 — Backend tests for:
  1. Hours CSV import: multi-format date parser
  2. Bulk RSVP CSV importer (template, dry-run, confirm, authz, edge cases)
"""
import io
import os
import csv
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"
HAPPY_EVENT_ID = "3a9ee2e9-7852-4586-9b3f-a94b3da8af84"  # Iter35 Test Event


# ---------------- helpers ----------------
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="session")
def member():
    return _login(MEMBER_EMAIL, MEMBER_PASS)


def _csv_bytes(rows, headers):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


# ---------------- 1) HOURS CSV DATE PARSER ----------------
class TestHoursCsvDateParser:
    HEADERS = ["member_email", "hours", "date", "activity"]

    def _post(self, admin, rows, dry_run=True):
        data = _csv_bytes(rows, self.HEADERS)
        files = {"file": ("hours.csv", data, "text/csv")}
        return admin.post(f"{API}/hours/admin/csv", params={"dry_run": str(dry_run).lower()}, files=files, timeout=20)

    def test_iso_date_parses(self, admin):
        r = self._post(admin, [[MEMBER_EMAIL, "1.5", "2026-06-15", "ISO"]])
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ready"] == 1 and j["failed"] == 0
        assert j["preview"][0]["status"] == "ready"

    def test_excel_default_mdy_parses(self, admin):
        r = self._post(admin, [[MEMBER_EMAIL, "1.5", "6/15/2026", "Excel default"]])
        assert r.status_code == 200, r.text
        assert r.json()["ready"] == 1

    def test_short_year_parses(self, admin):
        r = self._post(admin, [[MEMBER_EMAIL, "1.5", "6/15/26", "Short year"]])
        assert r.status_code == 200, r.text
        assert r.json()["ready"] == 1

    def test_dash_mdy_parses(self, admin):
        r = self._post(admin, [[MEMBER_EMAIL, "1.5", "06-15-2026", "Dash US"]])
        assert r.status_code == 200, r.text
        assert r.json()["ready"] == 1

    def test_day_month_year_parses(self, admin):
        r = self._post(admin, [[MEMBER_EMAIL, "1.5", "15-Jun-2026", "DDMmmYYYY"]])
        assert r.status_code == 200, r.text
        assert r.json()["ready"] == 1

    def test_unparseable_date_returns_error_with_format_list(self, admin):
        r = self._post(admin, [[MEMBER_EMAIL, "1.5", "bad-input", "Bad"]])
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["failed"] == 1
        msg = j["preview"][0]["message"]
        # Error message should list accepted formats
        for token in ("YYYY-MM-DD", "MM/DD/YYYY", "M/D/YY", "15-Jun-2026"):
            assert token in msg, f"missing '{token}' in error: {msg}"

    def test_empty_date_mentions_formats(self, admin):
        r = self._post(admin, [[MEMBER_EMAIL, "1.5", "", "Empty"]])
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["failed"] == 1
        msg = j["preview"][0]["message"]
        # Either "Missing date" path or _parse_csv_date path should include the formats line
        assert "YYYY-MM-DD" in msg and "MM/DD/YYYY" in msg, f"empty-date error missing formats: {msg}"


# ---------------- 2) ADMIN-RSVP CSV TEMPLATE ----------------
class TestAdminRsvpCsvTemplate:
    def test_template_returns_csv_with_headers(self, admin):
        r = admin.get(f"{API}/events/{HAPPY_EVENT_ID}/admin-rsvp/csv/template", timeout=20)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        body = r.text
        # Header
        first_line = body.splitlines()[0]
        assert first_line.strip() == "member_email,ticket_type,guests,guest_ticket_types"
        # 2 sample rows after header
        lines = [ln for ln in body.splitlines() if ln.strip()]
        assert len(lines) == 3, f"expected header + 2 sample rows, got {len(lines)} lines"

    def test_template_forbidden_for_non_admin(self, member):
        r = member.get(f"{API}/events/{HAPPY_EVENT_ID}/admin-rsvp/csv/template", timeout=20)
        assert r.status_code == 403


# ---------------- 3) ADMIN-RSVP CSV DRY-RUN ----------------
class TestAdminRsvpCsvDryRun:
    HEADERS = ["member_email", "ticket_type", "guests", "guest_ticket_types"]

    def _post(self, admin, rows, dry_run=True, send_email=True, filename="rsvps.csv"):
        data = _csv_bytes(rows, self.HEADERS)
        files = {"file": (filename, data, "text/csv")}
        params = {"dry_run": str(dry_run).lower(), "send_email": str(send_email).lower()}
        return admin.post(f"{API}/events/{HAPPY_EVENT_ID}/admin-rsvp/csv", params=params, files=files, timeout=30)

    def test_dry_run_valid_plus_invalid_email(self, admin):
        # Pick an unused member email so it doesn't collide with prior runs
        rows = [
            ["jordan.reed@clubhaven.app", "general", "Alex Plus-one; Pat Friend", "general; general"],
            ["nonexistent_user_xyz@example.com", "general", "", ""],
        ]
        r = self._post(admin, rows, dry_run=True)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["dry_run"] is True
        assert j["total"] == 2
        # ready + failed may flip if jordan already has an RSVP from previous run; allow either
        # but the nonexistent email must be an error
        assert j["failed"] >= 1
        # Find the ready row (if any) and the error row for nonexistent
        ready_rows = [p for p in j["preview"] if p["status"] == "ready"]
        error_rows = [p for p in j["preview"] if p["status"] == "error"]
        assert any("nonexistent" in (p.get("email") or "").lower() and "No member" in p["message"] for p in error_rows), j
        # If jordan was ready, verify guest_names + seats
        for p in ready_rows:
            if p.get("email", "").startswith("jordan"):
                assert p["guest_names"] == ["Alex Plus-one", "Pat Friend"]
                assert p["seats"] == 3
                break

    def test_dry_run_does_not_persist(self, admin):
        # Count current RSVPs by listing event
        before = admin.get(f"{API}/events/{HAPPY_EVENT_ID}", timeout=20).json()
        before_count = before.get("rsvp_count", 0)
        rows = [["sam.okafor@clubhaven.app", "general", "Guest A", ""]]
        r = self._post(admin, rows, dry_run=True)
        assert r.status_code == 200
        assert r.json()["created"] == 0
        after = admin.get(f"{API}/events/{HAPPY_EVENT_ID}", timeout=20).json()
        assert after.get("rsvp_count", 0) == before_count

    def test_duplicate_email_in_same_file(self, admin):
        rows = [
            ["harper.liu@clubhaven.app", "general", "G1", ""],
            ["harper.liu@clubhaven.app", "general", "G2", ""],
        ]
        r = self._post(admin, rows, dry_run=True)
        assert r.status_code == 200, r.text
        j = r.json()
        err_msgs = [p["message"] for p in j["preview"] if p["status"] == "error"]
        # If harper already has an RSVP, first error will be "already has an RSVP"; second is "appears more than once".
        # If harper does NOT have an RSVP, first is ready and second is "appears more than once".
        assert any("appears more than once" in m for m in err_msgs), err_msgs

    def test_capacity_overflow(self, admin):
        """Create a fresh event with capacity=2, then dry-run with a member+2 guests (seats=3)."""
        ev_payload = {
            "title": f"TEST_cap_event_{uuid.uuid4().hex[:6]}",
            "description": "capacity test",
            "start_at": "2030-01-01T12:00:00Z",
            "end_at": "2030-01-01T14:00:00Z",
            "location": "Test",
            "capacity": 2,
            "is_paid": False,
        }
        cr = admin.post(f"{API}/events", json=ev_payload, timeout=20)
        assert cr.status_code in (200, 201), cr.text
        ev = cr.json()
        ev_id = ev["id"]
        try:
            data = _csv_bytes([["maya.patel@clubhaven.app", "general", "G1; G2", ""]], self.HEADERS)
            files = {"file": ("c.csv", data, "text/csv")}
            r = admin.post(f"{API}/events/{ev_id}/admin-rsvp/csv", params={"dry_run": "true"}, files=files, timeout=20)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["failed"] == 1
            msg = j["preview"][0]["message"]
            assert "Not enough seats" in msg and "needs 3" in msg and "only 2 left" in msg, msg
        finally:
            admin.delete(f"{API}/events/{ev_id}", timeout=20)


# ---------------- 4) ADMIN-RSVP CSV CONFIRM ----------------
class TestAdminRsvpCsvConfirm:
    HEADERS = ["member_email", "ticket_type", "guests", "guest_ticket_types"]

    def test_confirm_no_email_persists_with_attribution(self, admin):
        """Create fresh event so we have a clean slate, then confirm import w/ send_email=false."""
        ev = admin.post(f"{API}/events", json={
            "title": f"TEST_confirm_{uuid.uuid4().hex[:6]}",
            "description": "confirm test",
            "start_at": "2030-02-01T12:00:00Z",
            "end_at": "2030-02-01T14:00:00Z",
            "location": "Test",
            "capacity": 50,
            "is_paid": False,
        }, timeout=20).json()
        ev_id = ev["id"]
        filename = "import-noemail.csv"
        try:
            rows = [
                ["maya.patel@clubhaven.app", "general", "Alex Plus-one; Pat Friend", "general; vip"],
                ["jordan.reed@clubhaven.app", "vip", "", ""],
            ]
            data = _csv_bytes(rows, self.HEADERS)
            files = {"file": (filename, data, "text/csv")}
            r = admin.post(f"{API}/events/{ev_id}/admin-rsvp/csv",
                           params={"dry_run": "false", "send_email": "false"},
                           files=files, timeout=30)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["dry_run"] is False
            assert j["ready"] == 2
            assert j["created"] == 2
            assert j["failed"] == 0
            # Event counters
            ev_after = admin.get(f"{API}/events/{ev_id}", timeout=20).json()
            # 2 RSVPs + 2 guests for maya = 2 rsvp_count, 2 guest_count
            assert ev_after.get("rsvp_count") == 2, ev_after
            assert ev_after.get("guest_count") == 2, ev_after
            # Re-running same file should now produce "already has an RSVP" for both
            files2 = {"file": (filename, data, "text/csv")}
            r2 = admin.post(f"{API}/events/{ev_id}/admin-rsvp/csv",
                            params={"dry_run": "true", "send_email": "false"},
                            files=files2, timeout=20)
            j2 = r2.json()
            assert j2["failed"] == 2
            assert all("already has an RSVP" in p["message"] for p in j2["preview"])
        finally:
            admin.delete(f"{API}/events/{ev_id}", timeout=20)


# ---------------- 5) REJECT CASES ----------------
class TestAdminRsvpCsvRejects:
    HEADERS = ["member_email", "ticket_type", "guests", "guest_ticket_types"]

    def _post(self, admin, event_id, rows, headers=None, filename="r.csv"):
        h = headers if headers is not None else self.HEADERS
        data = _csv_bytes(rows, h)
        files = {"file": (filename, data, "text/csv")}
        return admin.post(f"{API}/events/{event_id}/admin-rsvp/csv", params={"dry_run": "true"}, files=files, timeout=20)

    def test_non_csv_filename(self, admin):
        data = _csv_bytes([["x@x.com", "general", "", ""]], self.HEADERS)
        files = {"file": ("foo.txt", data, "text/csv")}
        r = admin.post(f"{API}/events/{HAPPY_EVENT_ID}/admin-rsvp/csv", params={"dry_run": "true"}, files=files, timeout=20)
        assert r.status_code == 400
        assert ".csv" in r.text.lower()

    def test_missing_member_email_column(self, admin):
        r = self._post(admin, HAPPY_EVENT_ID, [["general", "", ""]], headers=["ticket_type", "guests", "guest_ticket_types"])
        assert r.status_code == 400
        assert "member_email" in r.text

    def test_zero_data_rows(self, admin):
        data = b"member_email,ticket_type,guests,guest_ticket_types\n"
        files = {"file": ("empty.csv", data, "text/csv")}
        r = admin.post(f"{API}/events/{HAPPY_EVENT_ID}/admin-rsvp/csv", params={"dry_run": "true"}, files=files, timeout=20)
        assert r.status_code == 400
        assert "no data rows" in r.text.lower() or "data" in r.text.lower()

    def test_more_than_500_rows(self, admin):
        rows = [["x@x.com", "general", "", ""] for _ in range(501)]
        data = _csv_bytes(rows, self.HEADERS)
        files = {"file": ("big.csv", data, "text/csv")}
        r = admin.post(f"{API}/events/{HAPPY_EVENT_ID}/admin-rsvp/csv", params={"dry_run": "true"}, files=files, timeout=30)
        assert r.status_code == 400
        assert "500" in r.text or "too large" in r.text.lower()

    def test_umbrella_parent_event_rejected(self, admin):
        """Find the Alpha Omega Phi 10-Year Anniversary umbrella per the context hint."""
        evs = admin.get(f"{API}/events", timeout=20).json()
        umbrella = next((e for e in evs if "Anniversary" in e.get("title", "") or "10-Year" in e.get("title", "")), None)
        if not umbrella:
            pytest.skip("No umbrella event found to test")
        data = _csv_bytes([["x@x.com", "general", "", ""]], self.HEADERS)
        files = {"file": ("r.csv", data, "text/csv")}
        r = admin.post(f"{API}/events/{umbrella['id']}/admin-rsvp/csv", params={"dry_run": "true"}, files=files, timeout=20)
        assert r.status_code == 400, r.text
        assert "umbrella" in r.text.lower()

    def test_cancelled_event_rejected(self, admin):
        ev = admin.post(f"{API}/events", json={
            "title": f"TEST_cancel_{uuid.uuid4().hex[:6]}",
            "description": "cancel test",
            "start_at": "2030-03-01T12:00:00Z",
            "end_at": "2030-03-01T14:00:00Z",
            "location": "x", "capacity": 10, "is_paid": False,
        }, timeout=20).json()
        ev_id = ev["id"]
        try:
            # cancel via PUT (try common endpoints)
            cancel = admin.put(f"{API}/events/{ev_id}", json={"cancelled": True}, timeout=20)
            if cancel.status_code not in (200, 204):
                cancel = admin.put(f"{API}/events/{ev_id}/cancel", timeout=20)
            assert cancel.status_code in (200, 204), cancel.text
            r = self._post(admin, ev_id, [["x@x.com", "general", "", ""]])
            assert r.status_code == 400
            assert "cancel" in r.text.lower()
        finally:
            admin.delete(f"{API}/events/{ev_id}", timeout=20)

    def test_paid_event_rejected(self, admin):
        ev = admin.post(f"{API}/events", json={
            "title": f"TEST_paid_{uuid.uuid4().hex[:6]}",
            "description": "paid test",
            "start_at": "2030-04-01T12:00:00Z",
            "end_at": "2030-04-01T14:00:00Z",
            "location": "x", "capacity": 10, "is_paid": True,
            "payment_amount": 25, "payment_url": "https://zeffy.example",
        }, timeout=20).json()
        ev_id = ev["id"]
        try:
            r = self._post(admin, ev_id, [["x@x.com", "general", "", ""]])
            assert r.status_code == 400
            assert "paid" in r.text.lower()
        finally:
            admin.delete(f"{API}/events/{ev_id}", timeout=20)


# ---------------- 6) AUTHZ ----------------
class TestAdminRsvpCsvAuthz:
    def test_non_admin_post_forbidden(self, member):
        data = _csv_bytes([["x@x.com", "general", "", ""]], ["member_email", "ticket_type", "guests", "guest_ticket_types"])
        files = {"file": ("r.csv", data, "text/csv")}
        r = member.post(f"{API}/events/{HAPPY_EVENT_ID}/admin-rsvp/csv", params={"dry_run": "true"}, files=files, timeout=20)
        assert r.status_code == 403
