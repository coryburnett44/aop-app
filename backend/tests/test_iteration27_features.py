"""Iteration 27 backend tests:
1. Event cancellation (admin toggle + RSVP block)
2. Bulk CSV member import (template + dry-run + actual import)
3. Member 'Title' field on profile / admin create / admin update
Plus quick smoke regression of unchanged endpoints.
"""
import os
import io
import csv
import time
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=", 1)[1].splitlines()[0]
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def member_session():
    return _login(MEMBER)


# ----------------------------- 1. EVENT CANCELLATION -----------------------------
class TestEventCancellation:
    EVENT_ID = None
    EVENT_DATE = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()

    def test_create_event_default_not_cancelled(self, admin_session):
        start = (datetime.now(timezone.utc) + timedelta(days=14)).replace(hour=18, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        payload = {
            "title": "TEST_Cancel Event",
            "description": "iter27",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "location": "Online",
            "capacity": 50,
        }
        r = admin_session.post(f"{API}/events", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        ev = r.json()
        assert ev.get("cancelled") is False
        assert ev.get("cancellation_note") in (None, "")
        assert ev.get("cancelled_at") in (None, "")
        TestEventCancellation.EVENT_ID = ev["id"]

    def test_admin_cancels_event(self, admin_session, member_session):
        eid = TestEventCancellation.EVENT_ID
        # Member RSVPs first so we can later test guest-edit lock path
        rs = member_session.post(f"{API}/events/{eid}/rsvp", json={"status": "going"}, timeout=20)
        assert rs.status_code in (200, 201), rs.text
        r = admin_session.put(
            f"{API}/events/{eid}",
            json={"cancelled": True, "cancellation_note": "Weather"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        ev = r.json()
        assert ev["cancelled"] is True
        assert ev["cancellation_note"] == "Weather"
        assert ev["cancelled_at"], "cancelled_at must be stamped on flip-on"

    def test_member_rsvp_blocked_on_cancelled(self, member_session):
        eid = TestEventCancellation.EVENT_ID
        r = member_session.post(f"{API}/events/{eid}/rsvp", json={"status": "going"}, timeout=20)
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "cancelled" in detail and "rsvp" in detail

    def test_guest_edit_blocked_on_cancelled(self, member_session):
        eid = TestEventCancellation.EVENT_ID
        r = member_session.put(
            f"{API}/events/{eid}/rsvp/guests", json={"guests": [{"name": "X"}]}, timeout=20
        )
        assert r.status_code == 400, r.text
        assert "lock" in (r.json().get("detail") or "").lower() or "cancelled" in (
            r.json().get("detail") or ""
        ).lower()

    def test_uncancel_clears_cancelled_at_and_allows_rsvp(self, admin_session, member_session):
        eid = TestEventCancellation.EVENT_ID
        r = admin_session.put(
            f"{API}/events/{eid}", json={"cancelled": False}, timeout=20
        )
        assert r.status_code == 200, r.text
        ev = r.json()
        assert ev["cancelled"] is False
        assert ev.get("cancelled_at") in (None, "")
        # Now RSVP should succeed
        r2 = member_session.post(f"{API}/events/{eid}/rsvp", json={"status": "going"}, timeout=20)
        assert r2.status_code in (200, 201), r2.text

    def test_cleanup_event(self, admin_session):
        eid = TestEventCancellation.EVENT_ID
        if eid:
            admin_session.delete(f"{API}/events/{eid}", timeout=20)


# ----------------------------- 2. BULK CSV IMPORT -----------------------------
class TestBulkImport:
    CREATED_IDS = []

    def test_template_csv(self, admin_session):
        r = admin_session.get(f"{API}/admin/members/bulk-import/template", timeout=20)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("text/csv")
        text = r.text
        # Headers contain expected fields
        first_line = text.splitlines()[0]
        for col in ["Email", "Title", "First Name", "Renewal Date"]:
            assert col in first_line, f"Missing column {col} in template"
        # Has at least 1 data row
        assert len(text.splitlines()) >= 2

    @staticmethod
    def _build_csv():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "Email",
                "Title",
                "First Name",
                "Last Name",
                "Renewal Date",
                "Chapter",
            ]
        )
        # 1 valid with chapter Texas (chapter exists in seed)
        w.writerow(
            [
                "test_iter27_a@example.com",
                "mr",  # alias normalization
                "Alice",
                "Anderson",
                "2026-03-15",  # ISO
                "Texas",
            ]
        )
        # 1 valid no chapter, American date
        w.writerow(
            [
                "test_iter27_b@example.com",
                "Dr.",
                "Bob",
                "Brown",
                "3/15/2026",
                "",
            ]
        )
        # 1 missing email -> error
        w.writerow(["", "Ms.", "NoEmail", "Person", "2026-03-15", ""])
        # 1 dup of admin -> skipped
        w.writerow(
            [
                "admin@clubhaven.app",
                "Mr.",
                "Dup",
                "Admin",
                "2026-03-15",
                "",
            ]
        )
        return buf.getvalue().encode("utf-8")

    def test_dry_run_does_not_create(self, admin_session):
        csv_bytes = self._build_csv()
        files = {"file": ("members.csv", csv_bytes, "text/csv")}
        data = {"dry_run": "true"}
        r = admin_session.post(
            f"{API}/admin/members/bulk-import", files=files, data=data, timeout=30
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is True
        assert body["total"] == 4
        assert body["created_count"] == 2, body
        assert body["skipped_count"] == 1, body
        assert body["error_count"] == 1, body
        # Verify users are NOT actually created
        r2 = admin_session.get(f"{API}/members?q=test_iter27", timeout=20)
        # endpoint may or may not support q; either way check existing user fetch
        check = admin_session.get(f"{API}/members?limit=500", timeout=20)
        if check.status_code == 200:
            ms = check.json() if isinstance(check.json(), list) else check.json().get("members", [])
            emails = {(m.get("email") or "").lower() for m in ms}
            assert "test_iter27_a@example.com" not in emails
            assert "test_iter27_b@example.com" not in emails

    def test_actual_import_persists_and_sets_expires(self, admin_session):
        csv_bytes = self._build_csv()
        files = {"file": ("members.csv", csv_bytes, "text/csv")}
        data = {"dry_run": "false"}
        r = admin_session.post(
            f"{API}/admin/members/bulk-import", files=files, data=data, timeout=30
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is False
        assert body["created_count"] == 2
        assert body["skipped_count"] == 1
        assert body["error_count"] == 1

        # Find inserted users and validate membership_expires_at
        check = admin_session.get(f"{API}/members?limit=500", timeout=20)
        assert check.status_code == 200, check.text
        payload = check.json()
        members = payload if isinstance(payload, list) else payload.get("members", [])
        by_email = {(m.get("email") or "").lower(): m for m in members}
        a = by_email.get("test_iter27_a@example.com")
        b = by_email.get("test_iter27_b@example.com")
        assert a and b, f"both created users should be findable: a={bool(a)} b={bool(b)}"
        TestBulkImport.CREATED_IDS = [a["id"], b["id"]]

        # Title normalization 'mr' -> 'Mr.'
        assert a.get("title") == "Mr.", f"expected Mr. got {a.get('title')}"
        assert b.get("title") == "Dr.", f"expected Dr. got {b.get('title')}"

        # membership_expires_at = 2026-03-15 + 365 days = 2027-03-15
        expected = (datetime(2026, 3, 15, tzinfo=timezone.utc) + timedelta(days=365)).date()
        for u in (a, b):
            exp = u.get("membership_expires_at") or ""
            assert exp, f"missing membership_expires_at on {u.get('email')}"
            # parse ISO
            try:
                got = datetime.fromisoformat(exp.replace("Z", "+00:00")).date()
            except Exception:
                got = datetime.strptime(exp[:10], "%Y-%m-%d").date()
            # Allow ±1 day for timezone fuzz
            delta = abs((got - expected).days)
            assert delta <= 1, f"expires_at={got} expected={expected} (user {u.get('email')})"

    def test_reject_non_csv(self, admin_session):
        files = {"file": ("notes.txt", b"hello", "text/plain")}
        r = admin_session.post(
            f"{API}/admin/members/bulk-import", files=files, data={"dry_run": "true"}, timeout=20
        )
        assert r.status_code == 400
        assert ".csv" in (r.json().get("detail") or "").lower()

    def test_cleanup_created_users(self, admin_session):
        for uid in TestBulkImport.CREATED_IDS:
            admin_session.delete(f"{API}/members/{uid}", timeout=20)


# ----------------------------- 3. TITLE FIELD -----------------------------
class TestTitleField:
    def test_member_self_update_title(self, member_session):
        # set Dr.
        r = member_session.put(f"{API}/members/me", json={"title": "Dr."}, timeout=20)
        assert r.status_code == 200, r.text
        # Verify via /auth/me
        me = member_session.get(f"{API}/auth/me", timeout=20).json()
        assert me.get("title") == "Dr.", me
        # Clear
        r2 = member_session.put(f"{API}/members/me", json={"title": ""}, timeout=20)
        assert r2.status_code == 200, r2.text
        me2 = member_session.get(f"{API}/auth/me", timeout=20).json()
        assert me2.get("title") in (None, ""), me2

    def test_admin_create_and_update_member_title(self, admin_session):
        # Create
        payload = {
            "email": "test_iter27_title@example.com",
            "name": "Title Test",
            "first_name": "Title",
            "last_name": "Test",
            "title": "Mrs.",
            "password": "Pw12345!",
        }
        r = admin_session.post(f"{API}/admin/members", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        u = r.json()
        uid = u.get("id")
        assert uid
        assert u.get("title") == "Mrs.", u
        try:
            # Update
            r2 = admin_session.put(f"{API}/members/{uid}", json={"title": "Prof."}, timeout=20)
            assert r2.status_code == 200, r2.text
            assert r2.json().get("title") == "Prof.", r2.json()
        finally:
            admin_session.delete(f"{API}/members/{uid}", timeout=20)


# ----------------------------- 4. SMOKE REGRESSION -----------------------------
class TestSmoke:
    def test_login_admin(self, admin_session):
        r = admin_session.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 200
        assert r.json().get("email") == "admin@clubhaven.app"

    def test_chapters_list(self, admin_session):
        r = admin_session.get(f"{API}/chapters", timeout=20)
        assert r.status_code == 200

    def test_events_list(self, admin_session):
        r = admin_session.get(f"{API}/events", timeout=20)
        assert r.status_code == 200

    def test_members_list(self, admin_session):
        r = admin_session.get(f"{API}/members?limit=10", timeout=20)
        assert r.status_code == 200
