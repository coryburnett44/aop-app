"""Iteration 34 regression tests.

Covers:
  - FEATURE: POST /api/admin/members/bulk-resend-set-password
  - REFACTOR: routes/applications.py (POST /auth/apply, GET /admin/applications, POST /admin/applications/{id}/review)
  - REFACTOR: routes/hours.py (POST/GET /hours, PUT /hours/{id}/review, DELETE /hours/{id}, GET /me/hours, GET /me/hours/summary)
  - REGRESSION: back-compat _send_set_password_email shim (per-user resend still works)
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback to frontend .env file (the system prompt requires REACT_APP_BACKEND_URL)
    import re
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                m = re.match(r"REACT_APP_BACKEND_URL=(.+)", line.strip())
                if m:
                    BASE_URL = m.group(1).strip().strip('"')
                    break
    except Exception:
        pass
BASE_URL = (BASE_URL or "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASSWORD = "Member123!"
GOVERNOR_EMAIL = "governor.tx@clubhaven.app"
GOVERNOR_PASSWORD = "Governor123!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def member():
    return _login(MEMBER_EMAIL, MEMBER_PASSWORD)


@pytest.fixture(scope="module")
def governor():
    return _login(GOVERNOR_EMAIL, GOVERNOR_PASSWORD)


# ---------------------------------------------------------------------------
# FEATURE — POST /admin/members/bulk-resend-set-password
# ---------------------------------------------------------------------------

class TestBulkResendSetPassword:
    def test_member_forbidden(self, member):
        r = member.post(f"{API}/admin/members/bulk-resend-set-password")
        assert r.status_code == 403, r.text

    def test_unauth_forbidden(self):
        r = requests.post(f"{API}/admin/members/bulk-resend-set-password")
        assert r.status_code in (401, 403)

    def test_admin_seed_then_bulk(self, admin):
        # Make sure at least 1 user has pending_set_password=true.
        # Strategy: pick a non-admin member from /members and call per-user resend on it.
        # That guarantees pending_set_password=True is set.
        r_list = admin.get(f"{API}/members")
        assert r_list.status_code == 200, r_list.text
        members = r_list.json()
        # Pick first non-deceased member
        target = None
        for m in members:
            if m.get("email") and m["email"] not in (ADMIN_EMAIL, GOVERNOR_EMAIL):
                target = m
                break
        assert target, "no test member found in /members"
        r_pre = admin.post(f"{API}/admin/members/{target['id']}/resend-set-password")
        assert r_pre.status_code == 200, r_pre.text
        # Now run bulk
        r = admin.post(f"{API}/admin/members/bulk-resend-set-password")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "total" in data and "sent" in data and "failed" in data and "skipped_no_email" in data
        assert isinstance(data.get("members"), list)
        assert data["total"] >= 1
        # Each member item has id+email+sent
        for it in data["members"]:
            assert "id" in it and "email" in it and "sent" in it
        # Confirm the previously-pending user is in the bulk response
        ids = {it["id"] for it in data["members"]}
        assert target["id"] in ids

    def test_admin_bulk_invalidates_older_tokens(self, admin):
        # After bulk-resend ran, any previous token created by per-user resend should be marked used=true.
        # We can't query token collection via REST, but we can call bulk twice and confirm idempotency / consistency.
        r1 = admin.post(f"{API}/admin/members/bulk-resend-set-password")
        assert r1.status_code == 200
        d1 = r1.json()
        r2 = admin.post(f"{API}/admin/members/bulk-resend-set-password")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["total"] == d1["total"]  # set of pending users unchanged


# ---------------------------------------------------------------------------
# REGRESSION — per-user resend shim still wired
# ---------------------------------------------------------------------------

class TestPerUserResend:
    def test_member_forbidden(self, member):
        r = member.post(f"{API}/admin/members/some-id/resend-set-password")
        assert r.status_code == 403

    def test_unknown_user_404(self, admin):
        r = admin.post(f"{API}/admin/members/does-not-exist/resend-set-password")
        assert r.status_code == 404

    def test_admin_success(self, admin):
        r_list = admin.get(f"{API}/members")
        target = next(m for m in r_list.json() if m.get("email") and m["email"] != ADMIN_EMAIL)
        r = admin.post(f"{API}/admin/members/{target['id']}/resend-set-password")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert "sent" in data
        assert data["email"] == target["email"]


# ---------------------------------------------------------------------------
# REFACTOR — routes/applications.py end-to-end
# ---------------------------------------------------------------------------

class TestApplicationsFlow:
    def test_apply_listed_approved_and_login(self, admin):
        # Submit application (public)
        unique = uuid.uuid4().hex[:8]
        email = f"test_applicant_{unique}@clubhaven.app"
        password = "AppPass123!"
        payload = {
            "first_name": "TEST",
            "last_name": f"Applicant{unique}",
            "email": email,
            "password": password,
            "line_name": "TEST Line",
            "intake_line": "Spring 2024",
            "intake_completed_at": "2024-04-15",
            "address": "1 Test St",
            "city": "Austin",
            "state": "Texas",
            "zip_code": "78701",
            "country": "USA",
        }
        r_submit = requests.post(f"{API}/auth/apply", json=payload)
        assert r_submit.status_code == 200, r_submit.text
        body = r_submit.json()
        assert body.get("ok") is True
        app_id = body["application_id"]

        # Admin sees it under pending
        r_list = admin.get(f"{API}/admin/applications", params={"status_filter": "pending"})
        assert r_list.status_code == 200, r_list.text
        ids = {a["id"] for a in r_list.json()}
        assert app_id in ids
        # Confirm the structure of one item
        matching = next(a for a in r_list.json() if a["id"] == app_id)
        assert matching["email"] == email
        assert matching["status"] == "pending"

        # Duplicate submission should fail
        r_dup = requests.post(f"{API}/auth/apply", json=payload)
        assert r_dup.status_code == 400

        # Approve
        r_approve = admin.post(f"{API}/admin/applications/{app_id}/review", json={"action": "approve", "note": "ok"})
        assert r_approve.status_code == 200, r_approve.text
        data = r_approve.json()
        assert data["ok"] is True
        assert "user_id" in data

        # Re-review (already-reviewed) -> 400
        r_again = admin.post(f"{API}/admin/applications/{app_id}/review", json={"action": "approve"})
        assert r_again.status_code == 400

        # Created user can log in with the applicant-chosen password
        r_login = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
        assert r_login.status_code == 200, r_login.text

        # Cleanup: delete the user
        admin.delete(f"{API}/members/{data['user_id']}") if False else None
        # We don't have a delete-member route guaranteed; leave TEST_ prefixed user behind (acceptable per fixture convention).

    def test_review_unknown_app_404(self, admin):
        r = admin.post(f"{API}/admin/applications/does-not-exist/review", json={"action": "reject", "note": "n/a"})
        assert r.status_code == 404

    def test_admin_applications_member_forbidden(self, member):
        r = member.get(f"{API}/admin/applications")
        assert r.status_code == 403

    def test_reject_flow(self, admin):
        unique = uuid.uuid4().hex[:8]
        email = f"test_reject_{unique}@clubhaven.app"
        payload = {
            "first_name": "TESTReject",
            "last_name": f"User{unique}",
            "email": email,
            "password": "RejectPass123!",
            "line_name": "L",
            "intake_line": "Fall 2023",
            "intake_completed_at": "2023-11-01",
            "address": "x", "city": "x", "state": "Texas", "zip_code": "00000", "country": "USA",
        }
        r_submit = requests.post(f"{API}/auth/apply", json=payload)
        assert r_submit.status_code == 200
        app_id = r_submit.json()["application_id"]
        r_rej = admin.post(f"{API}/admin/applications/{app_id}/review", json={"action": "reject", "note": "incomplete"})
        assert r_rej.status_code == 200
        assert r_rej.json().get("ok") is True
        # User must NOT exist
        r_login = requests.post(f"{API}/auth/login", json={"email": email, "password": "RejectPass123!"})
        assert r_login.status_code in (400, 401)


# ---------------------------------------------------------------------------
# REFACTOR — routes/hours.py end-to-end
# ---------------------------------------------------------------------------

class TestHoursFlow:
    def test_log_list_review_delete(self, member, admin):
        # Member logs hours
        payload = {
            "hours": 3.0,
            "activity": "TEST iter34 community cleanup",
            "event_type": "aop_related",
            "agency_name": "TEST Agency",
            "host_name": "Host",
            "host_email": "host@example.com",
            "host_phone": "555-0100",
            "date": "2025-06-15",
        }
        r_log = member.post(f"{API}/hours", json=payload)
        assert r_log.status_code == 200, r_log.text
        h = r_log.json()
        assert h["hours"] == 3.0
        assert h["status"] == "pending"
        hours_id = h["id"]

        # Admin sees it in the queue
        r_q = admin.get(f"{API}/hours", params={"status_filter": "pending"})
        assert r_q.status_code == 200
        ids = {x["id"] for x in r_q.json()}
        assert hours_id in ids

        # Member forbidden from /hours admin queue
        r_mq = member.get(f"{API}/hours")
        assert r_mq.status_code == 403

        # Admin approves AND adjusts hours
        r_rev = admin.put(f"{API}/hours/{hours_id}/review", json={
            "status": "approved",
            "hours": 2.5,
            "note": "Adjusted",
            "activity": "TEST iter34 adjusted",
        })
        assert r_rev.status_code == 200, r_rev.text
        rev = r_rev.json()
        assert rev["status"] == "approved"
        assert rev["hours"] == 2.5
        assert rev.get("hours_adjusted_by") or rev.get("hours_adjusted_by_name")

        # Admin can re-review AFTER approval (flip to rejected)
        r_rev2 = admin.put(f"{API}/hours/{hours_id}/review", json={"status": "rejected", "note": "second look"})
        assert r_rev2.status_code == 200
        assert r_rev2.json()["status"] == "rejected"

        # Member can delete own
        r_del = member.delete(f"{API}/hours/{hours_id}")
        assert r_del.status_code == 200

        # 404 on re-review
        r_404 = admin.put(f"{API}/hours/{hours_id}/review", json={"status": "approved"})
        assert r_404.status_code == 404

    def test_me_hours_filters(self, member):
        # Log a couple of hours in different months/years
        for date, hrs in [("2025-01-10", 1.0), ("2025-04-12", 2.0), ("2025-07-20", 3.0)]:
            r = member.post(f"{API}/hours", json={
                "hours": hrs, "activity": f"TEST iter34 filter {date}",
                "event_type": "other", "agency_name": "X",
                "host_name": "Host", "host_email": "h@example.com", "host_phone": "555-0100",
                "date": date,
            })
            assert r.status_code == 200

        # Filter by year
        r_y = member.get(f"{API}/me/hours", params={"year": 2025})
        assert r_y.status_code == 200
        items = r_y.json()
        assert all((it.get("date") or "").startswith("2025") for it in items)

        # Filter by quarter (Q1 = Jan-Mar) — only the Jan entry should match
        r_q = member.get(f"{API}/me/hours", params={"year": 2025, "quarter": 1})
        assert r_q.status_code == 200
        q_items = r_q.json()
        for it in q_items:
            d = (it.get("date") or "")[:10]
            assert d[:7] in ("2025-01", "2025-02", "2025-03"), d

        # Filter by month
        r_m = member.get(f"{API}/me/hours", params={"year": 2025, "month": 7})
        assert r_m.status_code == 200
        for it in r_m.json():
            assert (it.get("date") or "")[:7] == "2025-07"

        # Cleanup the test hours
        for it in items:
            if "TEST iter34 filter" in (it.get("activity") or it.get("description") or ""):
                member.delete(f"{API}/hours/{it['id']}")

    def test_me_hours_summary(self, member):
        # Add one approved + one pending entry for current year
        # Member logs hours (pending)
        r_log = member.post(f"{API}/hours", json={
            "hours": 4.0, "activity": "TEST iter34 summary",
            "event_type": "other", "agency_name": "X",
            "host_name": "Host", "host_email": "h@example.com", "host_phone": "555-0100",
            "date": "2025-05-10",
        })
        assert r_log.status_code == 200
        hid = r_log.json()["id"]

        r = member.get(f"{API}/me/hours/summary", params={"year": 2025})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["year"] == 2025
        assert isinstance(data["by_month"], list) and len(data["by_month"]) == 12
        assert isinstance(data["by_quarter"], list) and len(data["by_quarter"]) == 4
        assert "total_approved" in data and "total_pending" in data
        # May entry should be in by_month index 4
        assert data["by_month"][4]["hours"] >= 4.0

        # cleanup
        member.delete(f"{API}/hours/{hid}")

    def test_delete_other_user_forbidden(self, admin, member):
        # Admin creates an hours entry FOR admin's own user
        r = admin.post(f"{API}/hours", json={
            "hours": 1.0, "activity": "TEST iter34 admin own",
            "event_type": "other", "agency_name": "X",
            "host_name": "Host", "host_email": "h@example.com", "host_phone": "555-0100",
            "date": "2025-02-01",
        })
        assert r.status_code == 200
        hid = r.json()["id"]
        # Member tries to delete
        r_del = member.delete(f"{API}/hours/{hid}")
        assert r_del.status_code == 403
        # Admin can delete
        r_a = admin.delete(f"{API}/hours/{hid}")
        assert r_a.status_code == 200

    def test_governor_chapter_scoped_hours_queue(self, governor):
        # Governor must get 200 and ONLY see chapter-scoped users
        r = governor.get(f"{API}/hours")
        assert r.status_code == 200, r.text
        # We can't assert what they should see without more data,
        # but the call must succeed (chapter_scope_user_ids logic works).
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# REGRESSION — prior route modules still wired
# ---------------------------------------------------------------------------

class TestRegression:
    def test_events_list(self):
        r = requests.get(f"{API}/events")
        assert r.status_code == 200

    def test_members_list(self, admin):
        r = admin.get(f"{API}/members")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_auth_me(self, admin):
        r = admin.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json().get("email") == ADMIN_EMAIL
