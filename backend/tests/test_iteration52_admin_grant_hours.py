"""
Iteration 52 — Admin grant edit/remove + bulk grant + admin DELETE /hours.

Covers:
  - PUT  /api/awards/grants/{grant_id}  (edit reason / granted_at; 400 / 404; empty-body no-op)
  - POST /api/awards/{award_id}/grant-bulk (bulk grant w/ ordinals; 400 / 404; authz)
  - DELETE /api/hours/{id}  (admin can delete any user's APPROVED or PENDING entry;
    /me/hours summary decrements; non-admin can delete OWN but not other member's)
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PW = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PW = "Member123!"
DEMO_EMAILS = [
    "maya.patel@clubhaven.app",
    "jordan.reed@clubhaven.app",
    "harper.liu@clubhaven.app",
]
DEMO_PW = "Demo123!"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def member_session():
    return _login(MEMBER_EMAIL, MEMBER_PW)


@pytest.fixture(scope="module")
def demo_user_ids(admin_session):
    """Resolve demo user ids by email — search per name to avoid /members 200-row cap."""
    ids = []
    for em in DEMO_EMAILS:
        # use the search query (q) to filter; matches by name/bio/interests
        local = em.split("@")[0]  # "maya.patel"
        first = local.split(".")[0]
        r = admin_session.get(f"{API}/members", params={"q": first}, timeout=15)
        assert r.status_code == 200, r.text
        members = r.json()
        match = next((m for m in members if m.get("email", "").lower() == em.lower()), None)
        if not match:
            # fallback: scan full list
            r2 = admin_session.get(f"{API}/members", timeout=15)
            match = next((m for m in r2.json() if m.get("email", "").lower() == em.lower()), None)
        assert match, f"missing demo member {em}"
        ids.append(match["id"])
    return ids


@pytest.fixture(scope="module")
def member_user_id(member_session):
    """Resolve the test member's id via /auth/me — bulletproof, no search."""
    r = member_session.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def test_award(admin_session):
    """Create an award we can grant/edit/remove freely."""
    body = {
        "name": f"TEST_iter52_award_{uuid.uuid4().hex[:6]}",
        "description": "Iteration 52 test award",
        "icon": "trophy",
        "color": "#F9D466",
    }
    r = admin_session.post(f"{API}/awards", json=body, timeout=15)
    assert r.status_code in (200, 201), r.text
    aw = r.json()
    yield aw
    # teardown: best-effort delete
    try:
        admin_session.delete(f"{API}/awards/{aw['id']}", timeout=10)
    except Exception:
        pass


# -------------- PUT /awards/grants/{grant_id} ---------------------------
class TestUpdateAwardGrant:
    def test_update_reason_and_date(self, admin_session, test_award, demo_user_ids):
        uid = demo_user_ids[0]
        r = admin_session.post(
            f"{API}/awards/{test_award['id']}/grant",
            json={"user_id": uid, "reason": "Original reason"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        grant = r.json()
        gid = grant["id"]
        # update with date-only string
        r2 = admin_session.put(
            f"{API}/awards/grants/{gid}",
            json={"reason": "Updated reason", "granted_at": "2025-06-15"},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        updated = r2.json()
        assert updated["reason"] == "Updated reason"
        assert updated["granted_at"].startswith("2025-06-15T00:00:00"), updated["granted_at"]
        # cleanup
        admin_session.delete(f"{API}/awards/grants/{gid}")

    def test_empty_body_no_change(self, admin_session, test_award, demo_user_ids):
        uid = demo_user_ids[0]
        r = admin_session.post(
            f"{API}/awards/{test_award['id']}/grant",
            json={"user_id": uid, "reason": "x"},
            timeout=15,
        )
        gid = r.json()["id"]
        r2 = admin_session.put(f"{API}/awards/grants/{gid}", json={}, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json() == {"ok": True, "no_change": True}
        admin_session.delete(f"{API}/awards/grants/{gid}")

    def test_invalid_granted_at_400(self, admin_session, test_award, demo_user_ids):
        uid = demo_user_ids[0]
        r = admin_session.post(
            f"{API}/awards/{test_award['id']}/grant",
            json={"user_id": uid, "reason": "x"},
            timeout=15,
        )
        gid = r.json()["id"]
        r2 = admin_session.put(
            f"{API}/awards/grants/{gid}", json={"granted_at": "not-a-date"}, timeout=15
        )
        assert r2.status_code == 400, r2.text
        admin_session.delete(f"{API}/awards/grants/{gid}")

    def test_nonexistent_grant_404(self, admin_session):
        r = admin_session.put(
            f"{API}/awards/grants/does-not-exist-{uuid.uuid4().hex[:6]}",
            json={"reason": "x"},
            timeout=15,
        )
        assert r.status_code == 404, r.text

    def test_authz_non_admin_blocked(self, member_session, admin_session, test_award, demo_user_ids):
        uid = demo_user_ids[0]
        r = admin_session.post(
            f"{API}/awards/{test_award['id']}/grant",
            json={"user_id": uid, "reason": "x"},
            timeout=15,
        )
        gid = r.json()["id"]
        r2 = member_session.put(
            f"{API}/awards/grants/{gid}", json={"reason": "hax"}, timeout=15
        )
        assert r2.status_code in (401, 403), r2.text
        admin_session.delete(f"{API}/awards/grants/{gid}")


# -------------- POST /awards/{award_id}/grant-bulk ----------------------
class TestGrantBulk:
    def test_bulk_grant_creates_ordinal_1_for_each(self, admin_session, test_award, demo_user_ids):
        body = {"user_ids": demo_user_ids, "reason": "Bulk iter52"}
        r = admin_session.post(
            f"{API}/awards/{test_award['id']}/grant-bulk", json=body, timeout=20
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 3
        assert data["failed"] == 0
        assert data["total"] == 3
        # Each fresh user should be ordinal=1
        for row in data["results"]:
            assert row["ok"] is True
            assert row["ordinal"] == 1
            assert row["user_id"] in demo_user_ids
            assert "name" in row

    def test_bulk_repeat_grant_increments_ordinal(self, admin_session, test_award, demo_user_ids):
        """A second bulk-grant for the same user(s) should bump ordinal to 2."""
        uid = demo_user_ids[0]
        body = {"user_ids": [uid], "reason": "Second grant"}
        r = admin_session.post(
            f"{API}/awards/{test_award['id']}/grant-bulk", json=body, timeout=15
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 1
        assert data["results"][0]["ordinal"] == 2, data["results"]
        # Verify via /reports/award-grants
        r2 = admin_session.get(
            f"{API}/reports/award-grants?user_id={uid}", timeout=15
        )
        assert r2.status_code == 200, r2.text
        grants = r2.json()
        matching = [g for g in grants if g["award_id"] == test_award["id"]]
        ordinals = sorted(g["ordinal"] for g in matching)
        assert 1 in ordinals and 2 in ordinals, f"got ordinals {ordinals}"

    def test_award_not_found(self, admin_session, demo_user_ids):
        r = admin_session.post(
            f"{API}/awards/does-not-exist/grant-bulk",
            json={"user_ids": demo_user_ids, "reason": ""},
            timeout=10,
        )
        assert r.status_code == 404

    def test_empty_user_ids_400(self, admin_session, test_award):
        r = admin_session.post(
            f"{API}/awards/{test_award['id']}/grant-bulk",
            json={"user_ids": [], "reason": ""},
            timeout=10,
        )
        assert r.status_code == 400

    def test_too_many_user_ids_400(self, admin_session, test_award):
        ids = [str(uuid.uuid4()) for _ in range(201)]
        r = admin_session.post(
            f"{API}/awards/{test_award['id']}/grant-bulk",
            json={"user_ids": ids, "reason": ""},
            timeout=15,
        )
        assert r.status_code == 400

    def test_authz_non_admin_blocked(self, member_session, test_award, demo_user_ids):
        r = member_session.post(
            f"{API}/awards/{test_award['id']}/grant-bulk",
            json={"user_ids": demo_user_ids, "reason": ""},
            timeout=10,
        )
        assert r.status_code in (401, 403)


# -------------- DELETE /hours/{id} (admin scope) ------------------------
class TestAdminDeleteHours:
    def _create_hours(self, session, user_id, hours, status="approved", is_admin=True):
        if is_admin:
            body = {
                "user_id": user_id,
                "hours": hours,
                "date": "2026-01-15",
                "description": f"TEST_iter52_{uuid.uuid4().hex[:5]}",
                "activity": f"TEST_iter52_{uuid.uuid4().hex[:5]}",
                "event_type": "other",
            }
            r = session.post(f"{API}/hours/admin", json=body, timeout=15)
        else:
            body = {
                "hours": hours,
                "date": "2026-01-15",
                "description": f"TEST_iter52_{uuid.uuid4().hex[:5]}",
                "activity": f"TEST_iter52_{uuid.uuid4().hex[:5]}",
                "event_type": "other",
                "agency_name": "TEST Agency",
                "host_name": "TEST Host",
                "host_email": "host@example.com",
                "host_phone": "555-1234",
            }
            r = session.post(f"{API}/hours", json=body, timeout=15)
        assert r.status_code in (200, 201), r.text
        h = r.json()
        return h

    def _member_summary_total(self, session):
        r = session.get(f"{API}/me/hours/summary", timeout=15)
        assert r.status_code == 200, r.text
        return r.json().get("total_approved", 0)

    def test_admin_delete_approved_hours_for_member_decrements_total(
        self, admin_session, member_session, member_user_id
    ):
        before = self._member_summary_total(member_session)
        h = self._create_hours(admin_session, member_user_id, 4.5, status="approved")
        after_add = self._member_summary_total(member_session)
        assert round(after_add - before, 2) == 4.5, (before, after_add)
        # admin deletes
        r = admin_session.delete(f"{API}/hours/{h['id']}", timeout=15)
        assert r.status_code == 200, r.text
        after_del = self._member_summary_total(member_session)
        assert round(after_del - before, 2) == 0.0, (before, after_del)

    def test_admin_delete_pending_hours_works(self, admin_session, member_session, member_user_id):
        # Member submits pending hours
        body = {
            "hours": 2,
            "date": "2026-01-16",
            "description": f"TEST_iter52_pending_{uuid.uuid4().hex[:5]}",
            "activity": f"TEST_iter52_pending_{uuid.uuid4().hex[:5]}",
            "event_type": "other",
            "agency_name": "TEST Agency",
            "host_name": "TEST Host",
            "host_email": "host@example.com",
            "host_phone": "555-1234",
        }
        r = member_session.post(f"{API}/hours", json=body, timeout=15)
        assert r.status_code in (200, 201), r.text
        h = r.json()
        assert h.get("status") == "pending"
        # admin deletes
        r2 = admin_session.delete(f"{API}/hours/{h['id']}", timeout=15)
        assert r2.status_code == 200, r2.text

    def test_member_cannot_delete_other_members_hours(
        self, admin_session, member_session, demo_user_ids
    ):
        # admin creates approved hours for demo user
        h = self._create_hours(admin_session, demo_user_ids[0], 1.0, status="approved")
        r = member_session.delete(f"{API}/hours/{h['id']}", timeout=10)
        assert r.status_code in (401, 403), r.text
        # cleanup as admin
        admin_session.delete(f"{API}/hours/{h['id']}", timeout=10)

    def test_member_can_delete_own_hours(self, member_session):
        body = {
            "hours": 1,
            "date": "2026-01-17",
            "description": f"TEST_iter52_own_{uuid.uuid4().hex[:5]}",
            "activity": f"TEST_iter52_own_{uuid.uuid4().hex[:5]}",
            "event_type": "other",
            "agency_name": "TEST Agency",
            "host_name": "TEST Host",
            "host_email": "host@example.com",
            "host_phone": "555-1234",
        }
        r = member_session.post(f"{API}/hours", json=body, timeout=15)
        assert r.status_code in (200, 201), r.text
        h = r.json()
        assert "id" in h, h
        r2 = member_session.delete(f"{API}/hours/{h['id']}", timeout=10)
        assert r2.status_code == 200, r2.text
