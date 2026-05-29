"""Backend tests for Omega tab tributes (templates + backgrounds).

Validates:
 - GET /api/omega/options returns the 3 templates + 7 backgrounds (per user spec).
 - POST /api/omega/tributes validates Literal template/background (rejects old values 422).
 - Successful create flips member status to deceased and tribute appears in GET /api/omega.
 - PUT updates rank/service_dates/template/background; DELETE removes.
 - Non-full-admin (governor_manager) is 403 on create (admin_tab_dep('members')).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(session: requests.Session, email: str, password: str) -> bool:
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    return r.status_code == 200


@pytest.fixture
def admin_session():
    s = requests.Session()
    assert _login(s, "admin@clubhaven.app", "Admin123!"), "admin login failed"
    return s


@pytest.fixture
def member_session():
    s = requests.Session()
    assert _login(s, "member@clubhaven.app", "Member123!"), "member login failed"
    return s


@pytest.fixture
def governor_session():
    s = requests.Session()
    ok = _login(s, "governor.tx@clubhaven.app", "Governor123!")
    if not ok:
        pytest.skip("governor account missing")
    return s


@pytest.fixture
def tribute_subject_id(admin_session):
    r = admin_session.get(f"{API}/members")
    assert r.status_code == 200
    members = r.json()
    # Try maya first
    for m in members:
        if m.get("email") == "maya.patel@clubhaven.app":
            return m["id"]
    # Fall back to any non-admin
    for m in members:
        if m.get("role") != "admin":
            return m["id"]
    pytest.skip("no member found to use as tribute subject")


# ---- Cleanup helpers ----
def _delete_tribute_if_exists(admin_session, user_id):
    r = admin_session.get(f"{API}/omega")
    if r.status_code == 200:
        for it in r.json():
            if it.get("user_id") == user_id and it.get("type") == "tribute":
                admin_session.delete(f"{API}/omega/tributes/{it['id']}")


def _clear_deceased(admin_session, user_id):
    # admin PUT /api/members/{id} uses 'member_status' field (maps to status_override)
    admin_session.put(
        f"{API}/members/{user_id}",
        json={"member_status": "active", "deceased_at": ""},
    )


# ============================================================
# 1) GET /api/omega/options
# ============================================================
class TestOmegaOptions:
    def test_options_templates_and_backgrounds(self, admin_session):
        r = admin_session.get(f"{API}/omega/options")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["templates"] == ["biography", "memorial-card", "in-service"]
        assert data["backgrounds"] == [
            "american-flag", "navy-starfield", "marble", "sepia",
            "solid-red", "solid-navy", "solid-white",
        ]

    def test_options_requires_auth(self):
        r = requests.get(f"{API}/omega/options")
        assert r.status_code in (401, 403)


# ============================================================
# 2) POST validation — old values rejected
# ============================================================
class TestOmegaValidation:
    @pytest.mark.parametrize("bad_template", ["classic", "portrait", "modern"])
    def test_reject_old_templates(self, admin_session, tribute_subject_id, bad_template):
        r = admin_session.post(
            f"{API}/omega/tributes",
            json={"user_id": tribute_subject_id, "template": bad_template, "background": "marble"},
        )
        assert r.status_code == 422, f"expected 422 for template={bad_template}, got {r.status_code} {r.text}"

    @pytest.mark.parametrize("bad_bg", ["navy-radial", "midnight", "ivory-soft", "patriot-stripe", "parchment"])
    def test_reject_old_backgrounds(self, admin_session, tribute_subject_id, bad_bg):
        r = admin_session.post(
            f"{API}/omega/tributes",
            json={"user_id": tribute_subject_id, "template": "biography", "background": bad_bg},
        )
        assert r.status_code == 422, f"expected 422 for background={bad_bg}, got {r.status_code} {r.text}"


# ============================================================
# 3) Full CRUD lifecycle on a tribute
# ============================================================
class TestTributeLifecycle:
    def test_create_update_delete(self, admin_session, tribute_subject_id):
        # ensure clean slate
        _delete_tribute_if_exists(admin_session, tribute_subject_id)
        _clear_deceased(admin_session, tribute_subject_id)

        try:
            # CREATE — in-service + american-flag
            payload = {
                "user_id": tribute_subject_id,
                "template": "in-service",
                "background": "american-flag",
                "rank": "TEST_Sgt. First Class",
                "service_dates": "1998 — 2018",
                "epitaph": "TEST_Honor above all.",
                "synopsis": "TEST_synopsis for in-service tribute.",
                "biography": "TEST_long biography text.",
                "born_at": "1970-04-12",
                "passed_at": "2024-11-20",
                "location": "TEST_Arlington",
            }
            r = admin_session.post(f"{API}/omega/tributes", json=payload)
            assert r.status_code == 200, r.text
            t = r.json()
            tribute_id = t["id"]
            assert t["template"] == "in-service"
            assert t["background"] == "american-flag"
            assert t["rank"] == "TEST_Sgt. First Class"
            assert t["service_dates"] == "1998 — 2018"
            assert t["user_id"] == tribute_subject_id

            # Verify it appears in /api/omega and member is now marked deceased
            r = admin_session.get(f"{API}/omega")
            assert r.status_code == 200
            items = r.json()
            match = [it for it in items if it.get("id") == tribute_id]
            assert match, "tribute not in /api/omega listing"
            assert match[0]["type"] == "tribute"
            assert match[0]["member"]["id"] == tribute_subject_id
            # member should be flagged deceased
            mr = admin_session.get(f"{API}/members/{tribute_subject_id}")
            assert mr.status_code == 200
            mdata = mr.json()
            assert mdata.get("status_override") == "deceased" or mdata.get("deceased_at")

            # Duplicate create should 400
            dup = admin_session.post(f"{API}/omega/tributes", json=payload)
            assert dup.status_code == 400

            # UPDATE — change template + background + rank + service_dates
            upd = admin_session.put(
                f"{API}/omega/tributes/{tribute_id}",
                json={
                    "template": "memorial-card",
                    "background": "marble",
                    "rank": "TEST_Captain",
                    "service_dates": "2000 — 2020",
                },
            )
            assert upd.status_code == 200, upd.text
            u = upd.json()
            assert u["template"] == "memorial-card"
            assert u["background"] == "marble"
            assert u["rank"] == "TEST_Captain"
            assert u["service_dates"] == "2000 — 2020"

            # DELETE
            d = admin_session.delete(f"{API}/omega/tributes/{tribute_id}")
            assert d.status_code == 200

            # Verify gone from collection-side: another create succeeds (no duplicate)
            r2 = admin_session.post(f"{API}/omega/tributes", json={**payload, "template": "biography", "background": "sepia"})
            assert r2.status_code == 200, r2.text
            admin_session.delete(f"{API}/omega/tributes/{r2.json()['id']}")
        finally:
            _delete_tribute_if_exists(admin_session, tribute_subject_id)
            _clear_deceased(admin_session, tribute_subject_id)


# ============================================================
# 4) Access control — non-full-admin gated
# ============================================================
class TestTributeAccessControl:
    def test_member_cannot_create(self, member_session, tribute_subject_id):
        r = member_session.post(
            f"{API}/omega/tributes",
            json={"user_id": tribute_subject_id, "template": "biography", "background": "marble"},
        )
        assert r.status_code in (401, 403), r.text

    def test_governor_manager_cannot_create(self, governor_session, tribute_subject_id):
        r = governor_session.post(
            f"{API}/omega/tributes",
            json={"user_id": tribute_subject_id, "template": "biography", "background": "marble"},
        )
        assert r.status_code == 403, r.text

    def test_unauth_cannot_create(self, tribute_subject_id):
        r = requests.post(
            f"{API}/omega/tributes",
            json={"user_id": tribute_subject_id, "template": "biography", "background": "marble"},
        )
        assert r.status_code in (401, 403)
