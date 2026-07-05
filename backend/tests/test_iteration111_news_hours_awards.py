"""Iteration 111 tests:
- News: template + images + search (?q=)
- Governor Manager: cannot auto-approve hours; cannot approve via review or edit
- /awards/eligibility: Full admin returns 7 keys; Governor and Membership Manager 403
- Regression: trendsetters_spirits event_type accepted
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PW = "Admin123!"
GOV_EMAIL = "governor.tx@clubhaven.app"
GOV_PW = "Governor123!"
MM_EMAIL = "mm.tx@clubhaven.app"
MM_PW = "MemMgr123!"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def gov_sess():
    return _login(GOV_EMAIL, GOV_PW)


@pytest.fixture(scope="module")
def mm_sess():
    return _login(MM_EMAIL, MM_PW)


# ================= News =================
class TestNews:
    _created_id = None

    def test_create_with_template_and_images(self, admin_sess):
        payload = {
            "title": "TEST_iter111 two-col article",
            "summary": "Iteration 111 test article",
            "body": "Body content with unique tag XYZZY_ITER111.",
            "cover_image": "",
            "images": [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            ],
            "template": "two_col",
            "tags": ["iter111", "test"],
        }
        r = admin_sess.post(f"{API}/news", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["template"] == "two_col"
        assert data["images"] == payload["images"]
        assert data["title"] == payload["title"]
        assert "id" in data
        TestNews._created_id = data["id"]

    def test_get_returns_template_and_images(self, admin_sess):
        assert TestNews._created_id, "Prev create failed"
        r = admin_sess.get(f"{API}/news/{TestNews._created_id}", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["template"] == "two_col"
        assert len(d["images"]) == 2

    def test_search_matches(self, admin_sess):
        r = admin_sess.get(f"{API}/news", params={"q": "XYZZY_ITER111"}, timeout=10)
        assert r.status_code == 200
        arr = r.json()
        assert any(x["id"] == TestNews._created_id for x in arr), "search by body failed"

    def test_search_by_tag(self, admin_sess):
        r = admin_sess.get(f"{API}/news", params={"q": "iter111"}, timeout=10)
        assert r.status_code == 200
        arr = r.json()
        assert any(x["id"] == TestNews._created_id for x in arr), "search by tag failed"

    def test_search_no_match(self, admin_sess):
        r = admin_sess.get(f"{API}/news", params={"q": "nonexistent12345_UNIQ_ITER111"}, timeout=10)
        assert r.status_code == 200
        assert r.json() == []

    def test_cleanup(self, admin_sess):
        if TestNews._created_id:
            r = admin_sess.delete(f"{API}/news/{TestNews._created_id}", timeout=10)
            assert r.status_code == 200


# ================= Hours: Governor cannot auto-approve =================
class TestGovernorHoursApproval:
    _pending_id = None
    _target_uid = None

    def test_find_tx_member(self, admin_sess, gov_sess):
        # Look up governor's chapter_id via /auth/me
        r = gov_sess.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        gov = r.json()
        gov_chapter = gov.get("chapter_id")
        assert gov_chapter, f"Governor has no chapter_id: {gov}"
        # Find a member in the same chapter via admin's full listing
        r = admin_sess.get(f"{API}/members", timeout=10)
        assert r.status_code == 200
        members = r.json()
        candidate = next(
            (m for m in members if m.get("chapter_id") == gov_chapter and m.get("role") != "admin"),
            None,
        )
        assert candidate, "No non-admin member found in governor's chapter"
        TestGovernorHoursApproval._target_uid = candidate["id"]

    def test_governor_admin_log_pending(self, gov_sess):
        uid = TestGovernorHoursApproval._target_uid
        assert uid
        payload = {
            "user_id": uid,
            "hours": 2.5,
            "activity": "TEST_iter111 governor pending",
            "event_type": "aop_related",
            "date": "2026-01-15T10:00:00",
        }
        r = gov_sess.post(f"{API}/hours/admin", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending", f"expected pending got {d.get('status')}"
        TestGovernorHoursApproval._pending_id = d["id"]

    def test_governor_cannot_approve_via_review(self, gov_sess):
        hid = TestGovernorHoursApproval._pending_id
        assert hid
        r = gov_sess.put(f"{API}/hours/{hid}/review", json={"status": "approved"}, timeout=10)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"

    def test_governor_cannot_approve_via_edit(self, gov_sess):
        hid = TestGovernorHoursApproval._pending_id
        assert hid
        r = gov_sess.put(f"{API}/hours/{hid}", json={"status": "approved"}, timeout=10)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"

    def test_governor_can_reject_via_review(self, gov_sess):
        hid = TestGovernorHoursApproval._pending_id
        assert hid
        r = gov_sess.put(f"{API}/hours/{hid}/review", json={"status": "rejected", "note": "TEST_iter111"}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rejected"

    def test_full_admin_auto_approves(self, admin_sess):
        # Pick any member
        r = admin_sess.get(f"{API}/members", timeout=10)
        assert r.status_code == 200
        members = r.json()
        m = next((m for m in members if m.get("role") != "admin"), members[0])
        payload = {
            "user_id": m["id"],
            "hours": 1.0,
            "activity": "TEST_iter111 full admin auto-approve",
            "event_type": "trendsetters_spirits",  # regression check
            "date": "2026-01-15T10:00:00",
        }
        r = admin_sess.post(f"{API}/hours/admin", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "approved", f"expected approved got {d.get('status')}"
        assert d["event_type"] == "trendsetters_spirits"
        # cleanup
        admin_sess.delete(f"{API}/hours/{d['id']}", timeout=10)

    def test_cleanup_pending(self, admin_sess):
        hid = TestGovernorHoursApproval._pending_id
        if hid:
            admin_sess.delete(f"{API}/hours/{hid}", timeout=10)


# ================= Awards Eligibility =================
class TestAwardsEligibility:
    EXPECTED_KEYS = [
        "service_ribbon",
        "fundraiser_ribbon",
        "community_service_ribbon",
        "ken_thompson",
        "recruitment_ribbon",
        "members_ribbon",
        "chapter_of_the_year",
    ]

    def test_full_admin_ok(self, admin_sess):
        r = admin_sess.get(f"{API}/awards/eligibility", params={"year": 2026}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in self.EXPECTED_KEYS:
            assert k in data, f"missing key {k}"
            assert isinstance(data[k], list)

    def test_governor_forbidden(self, gov_sess):
        r = gov_sess.get(f"{API}/awards/eligibility", params={"year": 2026}, timeout=10)
        assert r.status_code == 403, f"expected 403 got {r.status_code}"

    def test_membership_manager_forbidden(self, mm_sess):
        r = mm_sess.get(f"{API}/awards/eligibility", params={"year": 2026}, timeout=10)
        assert r.status_code == 403, f"expected 403 got {r.status_code}"

    def test_invalid_year_range(self, admin_sess):
        r = admin_sess.get(f"{API}/awards/eligibility", params={"year": 1999}, timeout=10)
        assert r.status_code == 400
