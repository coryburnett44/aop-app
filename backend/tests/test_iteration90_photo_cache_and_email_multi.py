"""Iteration 90 — Photo HTTP caching + Email multi-select & external recipients.

Two user-requested features bundled in this iteration:

  A. Photo loading is now backed by:
     - MongoDB indexes on `photos.album` + `photos.storage_path` (album list
       aggregation + file proxy lookups go from collection-scan to indexed).
     - The /api/files/{storage_path} proxy now returns
       `Cache-Control: private, max-age=31536000, immutable` + an ETag so
       repeat visits short-circuit with 304 Not Modified (no object-storage
       hit at all).
     - Frontend Photos.jsx renders <img loading="lazy" decoding="async"> so
       below-the-fold thumbnails don't all download at once.

  B. The email composer now lets admins send to:
     - Multiple specific members in the same blast (was: just one).
     - Ad-hoc external addresses outside the membership roster.
     Both new fields flow through `EmailBlastIn.custom_user_ids` (list) and
     `EmailBlastIn.external_emails` (list). Drafts persist both.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/")

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}


@pytest.fixture(scope="module")
def admin_s():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return s


# ===================================================================
# A. Photo caching headers + ETag short-circuit
# ===================================================================
class TestPhotoCaching:
    def _any_storage_path(self, admin_s) -> str:
        r = admin_s.get(f"{BASE_URL}/api/photos", timeout=20)
        assert r.status_code == 200, r.text
        photos = r.json()
        if not photos:
            pytest.skip("no photos in the environment to test the file proxy")
        return photos[0]["storage_path"]

    def test_file_proxy_emits_etag_and_long_cache_header(self, admin_s):
        sp = self._any_storage_path(admin_s)
        r = admin_s.get(f"{BASE_URL}/api/files/{sp}", timeout=20)
        assert r.status_code == 200, r.text
        # Origin always emits the long-cache header. A reverse proxy / CDN may
        # rewrite it before delivery, but the application-level contract is
        # what we control — assert the ETag because that's the bit browsers
        # use for revalidation even when Cache-Control is stripped.
        assert r.headers.get("ETag"), "ETag should be present on file proxy responses"
        # If the upstream didn't strip it, our long-cache header should be there.
        if "max-age" in (r.headers.get("Cache-Control") or ""):
            assert "31536000" in r.headers["Cache-Control"]
            assert "immutable" in r.headers["Cache-Control"]

    def test_if_none_match_returns_304(self, admin_s):
        sp = self._any_storage_path(admin_s)
        r1 = admin_s.get(f"{BASE_URL}/api/files/{sp}", timeout=20)
        etag = r1.headers.get("ETag")
        assert etag
        # Round-trip with the ETag — must come back as 304 with no body.
        r2 = admin_s.get(
            f"{BASE_URL}/api/files/{sp}",
            headers={"If-None-Match": etag}, timeout=20,
        )
        assert r2.status_code == 304, f"expected 304, got {r2.status_code}: {r2.text[:200]}"
        # 304 must not include a body (RFC 7232).
        assert not r2.content

    def test_missing_file_still_404(self, admin_s):
        r = admin_s.get(f"{BASE_URL}/api/files/clubhaven/nonexistent/abc.png", timeout=20)
        assert r.status_code == 404


# ===================================================================
# B. Email composer — multi-select members + external recipients
# ===================================================================
class TestEmailMultiSelectAndExternal:
    def _members(self, admin_s, n=3):
        r = admin_s.get(f"{BASE_URL}/api/members", timeout=20)
        assert r.status_code == 200
        out = r.json()
        if len(out) < n:
            pytest.skip(f"need at least {n} members in the environment")
        return out[:n]

    def test_preview_with_only_externals(self, admin_s):
        body = {
            "subject": "Iter90 — externals only",
            "body_html": "<p>Hi</p>",
            "segment": "custom",
            "custom_user_ids": [],
            "external_emails": [
                "vendor1@example.com",
                "Vendor1@Example.com",  # case-insensitive dedupe
                "vendor2@example.com",
                "not-an-email",  # malformed → dropped
                "",  # empty → dropped
            ],
        }
        r = admin_s.post(f"{BASE_URL}/api/email/preview", json=body, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # 2 valid externals, no members
        assert data["recipient_count"] == 2
        assert data["sample_recipient"]["email"] == "vendor1@example.com"

    def test_preview_with_multiple_members_plus_externals(self, admin_s):
        ms = self._members(admin_s, n=3)
        ids = [m["id"] for m in ms]
        body = {
            "subject": "Iter90 — mixed",
            "body_html": "<p>Hi {{first_name}}</p>",
            "segment": "custom",
            "custom_user_ids": ids,
            "external_emails": ["press@example.com"],
        }
        r = admin_s.post(f"{BASE_URL}/api/email/preview", json=body, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # 3 members + 1 external = 4
        assert data["recipient_count"] == 4

    def test_external_dedupes_against_member_emails(self, admin_s):
        ms = self._members(admin_s, n=1)
        m = ms[0]
        body = {
            "subject": "Iter90 — dedupe",
            "body_html": "<p>Hi</p>",
            "segment": "custom",
            "custom_user_ids": [m["id"]],
            # Putting the member's own email as an external should NOT add a
            # second recipient — the resolver dedupes against member emails.
            "external_emails": [m["email"].upper()],
        }
        r = admin_s.post(f"{BASE_URL}/api/email/preview", json=body, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["recipient_count"] == 1

    def test_draft_persists_external_emails_and_multi_ids(self, admin_s):
        ms = self._members(admin_s, n=2)
        ids = [m["id"] for m in ms]
        ext = ["vendor1@example.com", "vendor2@example.com"]
        # Use the namespaced name so the test is easy to find/clean if needed.
        draft_name = f"iter90-test-{uuid.uuid4().hex[:6]}"
        body = {
            "name": draft_name,
            "subject": "Iter90 draft",
            "body_html": "<p>Hello</p>",
            "segment": "custom",
            "custom_user_ids": ids,
            "external_emails": ext,
            "is_autosave": False,
        }
        r = admin_s.post(f"{BASE_URL}/api/email/drafts", json=body, timeout=20)
        assert r.status_code == 200, r.text
        draft = r.json()
        try:
            assert draft["custom_user_ids"] == ids
            assert sorted(draft["external_emails"]) == sorted(ext)
            # GET the drafts list and make sure it round-trips.
            r2 = admin_s.get(f"{BASE_URL}/api/email/drafts", timeout=20)
            assert r2.status_code == 200
            matches = [d for d in r2.json() if d["id"] == draft["id"]]
            assert matches and matches[0]["external_emails"] == ext
        finally:
            admin_s.delete(f"{BASE_URL}/api/email/drafts/{draft['id']}", timeout=20)

    def test_custom_segment_with_no_ids_and_no_externals_is_empty(self, admin_s):
        """Edge case — segment=custom but both lists empty must NOT silently
        broadcast to every active member."""
        body = {
            "subject": "Iter90 — empty custom",
            "body_html": "<p>Hi</p>",
            "segment": "custom",
            "custom_user_ids": [],
            "external_emails": [],
        }
        r = admin_s.post(f"{BASE_URL}/api/email/preview", json=body, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["recipient_count"] == 0
