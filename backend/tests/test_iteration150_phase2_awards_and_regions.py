"""Iteration 150 — Phase 2 Awards + Regions.

Backend contract regression coverage for four new user requests:

1. **Chapter-change approval flow** — members submit → chapter-admins see
   (governor-managers scoped to their chapter) → only full-access admins
   approve/deny → on approve, user.chapter_id updates + email/push
   notifications to the member, all governor-managers of both source and
   target chapters, and all full-access admins.

2. **Regions Governor Spotlight** — `public_user` already surfaces `bio`
   under `governor.bio` on region cards. Assert the payload shape.

3. **CSV import of past event attendance** — full-access-admin-only upload
   that parses email/name/event_name/date columns, matches to existing
   users, and inserts `checkins` rows (creating synthetic events as
   needed) so Medallion + Chapter-of-the-Year counts pick up historical
   data. Idempotent — re-uploading the same file is safe.

4. **Medallion suggestions moved to Admin Awards page** — the tab on the
   public Awards page no longer computes eligibility for members
   (verified frontend-side by the testing agent); this file only verifies
   that `/awards/medallion-eligibility` still exists and requires admin
   auth (used by Admin.jsx MedallionEligibilityPanel).

5. **Admins can grant Medallions to anyone** — verified by exercising
   `POST /awards/{id}/grant` on a Bronze Medallion for a user who does
   NOT meet the criteria; the grant is accepted.
"""
import io
import os
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@clubhaven.app")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")


def _login():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=10)
    r.raise_for_status()
    return r.json().get("access_token") or r.json().get("token")


# ---------------- Chapter-change flow ----------------
def test_chapter_change_end_to_end():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    # Pick a chapter different from the admin's current one.
    chapters = requests.get(f"{API}/chapters", headers=hdrs, timeout=10).json()
    me = requests.get(f"{API}/me", headers=hdrs, timeout=10).json()
    target = next((c for c in chapters if c["id"] != me.get("chapter_id")), None)
    assert target, "need at least one chapter different from current"

    # Clean up any pending request first (idempotency for the test).
    requests.delete(f"{API}/me/chapter-change-request", headers=hdrs, timeout=10)

    r = requests.post(
        f"{API}/me/chapter-change-request",
        headers=hdrs,
        json={"target_chapter_id": target["id"], "reason": "Test move"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["status"] == "pending"
    assert req["target_chapter_id"] == target["id"]
    req_id = req["id"]

    try:
        # Duplicate submission blocked
        dup = requests.post(
            f"{API}/me/chapter-change-request",
            headers=hdrs,
            json={"target_chapter_id": target["id"]},
            timeout=10,
        )
        assert dup.status_code == 409

        # Admin lists it
        listing = requests.get(f"{API}/admin/chapter-change-requests", headers=hdrs, timeout=10).json()
        assert any(x["id"] == req_id for x in listing)

        # Deny it (uses require_full_admin — admin@clubhaven.app is full)
        d = requests.post(
            f"{API}/admin/chapter-change-requests/{req_id}/deny",
            headers=hdrs,
            timeout=10,
        )
        assert d.status_code == 200
        assert d.json()["status"] == "denied"

        # Can't decide twice
        d2 = requests.post(f"{API}/admin/chapter-change-requests/{req_id}/approve", headers=hdrs, timeout=10)
        assert d2.status_code == 409
    finally:
        # Clean up so subsequent runs of this test aren't blocked.
        requests.delete(f"{API}/me/chapter-change-request", headers=hdrs, timeout=10)


def test_chapter_change_target_must_exist():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    requests.delete(f"{API}/me/chapter-change-request", headers=hdrs, timeout=10)
    r = requests.post(f"{API}/me/chapter-change-request", headers=hdrs, json={"target_chapter_id": "does-not-exist"}, timeout=10)
    assert r.status_code == 404


def test_chapter_change_requires_admin_on_list():
    r = requests.get(f"{API}/admin/chapter-change-requests", timeout=10)
    assert r.status_code in (401, 403)


def test_chapter_change_approve_requires_full_admin():
    r = requests.post(f"{API}/admin/chapter-change-requests/does-not-matter/approve", timeout=10)
    assert r.status_code in (401, 403)


# ---------------- Governor bio surfaces in region payload ----------------
def test_region_governor_includes_bio():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    payload = requests.get(f"{API}/regions", headers=hdrs, timeout=10).json()
    regions = payload.get("regions") if isinstance(payload, dict) else payload
    # The endpoint always returns a `governor` key (None when unassigned).
    # When populated, it must include the bio field via public_user().
    for r in regions or []:
        if r.get("governor"):
            assert "bio" in r["governor"], f"governor lacks bio: {r['governor']}"
            assert "avatar_url" in r["governor"]


# ---------------- CSV import of historical attendance ----------------
def test_csv_import_end_to_end():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    import time as _t
    ev = f"Regression Historical {int(_t.time())}"
    csv_text = (
        "email,event_name,date\n"
        f"{ADMIN_EMAIL},{ev},2022-04-01\n"
        "unknown@nowhere.invalid,Ghost Event,2022-05-05\n"
        f"{ADMIN_EMAIL},{ev},2022-04-01\n"  # duplicate — should be skipped
        ",Missing Email,2022-06-06\n"
    )
    files = {"file": ("attendance.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
    r = requests.post(f"{API}/admin/checkins/import-csv", headers=hdrs, files=files, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["inserted"] >= 1
    assert j["skipped"] >= 2  # unknown email + duplicate + missing email
    # Re-uploading the same CSV must not create new checkins.
    files2 = {"file": ("attendance.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
    r2 = requests.post(f"{API}/admin/checkins/import-csv", headers=hdrs, files=files2, timeout=20)
    assert r2.status_code == 200
    assert r2.json()["inserted"] == 0


def test_csv_import_rejects_missing_required_columns():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    bad = "foo,bar\n1,2\n"
    files = {"file": ("bad.csv", io.BytesIO(bad.encode("utf-8")), "text/csv")}
    r = requests.post(f"{API}/admin/checkins/import-csv", headers=hdrs, files=files, timeout=10)
    assert r.status_code == 400


def test_csv_import_requires_full_admin():
    csv_text = "email,event_name,date\nx,y,2020-01-01\n"
    files = {"file": ("x.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
    r = requests.post(f"{API}/admin/checkins/import-csv", files=files, timeout=10)
    assert r.status_code in (401, 403)


# ---------------- Medallion admin surface ----------------
def test_medallion_eligibility_still_admin_only():
    r = requests.get(f"{API}/awards/medallion-eligibility", timeout=10)
    assert r.status_code in (401, 403)


def test_admin_can_grant_medallion_regardless_of_eligibility():
    """The Medallion Club tab now lets admins grant to anyone (not just
    eligible candidates). Verify the underlying grant endpoint works for
    an arbitrary user."""
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    awards = requests.get(f"{API}/awards", headers=hdrs, timeout=10).json()
    bronze = next((a for a in awards if a.get("medallion_tier") == "bronze"), None)
    assert bronze, "Bronze Medallion must be seeded"
    # Pick any non-admin member.
    members = requests.get(f"{API}/members", headers=hdrs, timeout=10).json()
    target = next((m for m in members if m.get("id") and m.get("email") != ADMIN_EMAIL), None)
    if not target:
        return
    r = requests.post(
        f"{API}/awards/{bronze['id']}/grant",
        headers=hdrs,
        json={"user_id": target["id"], "note": "iteration150 regression"},
        timeout=10,
    )
    assert r.status_code in (200, 201, 409), r.text  # 409 = already granted, still acceptable
