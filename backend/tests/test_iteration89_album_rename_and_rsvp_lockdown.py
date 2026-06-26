"""Iteration 89 — Photo album rename + RSVP-lockdown ("rsvps_closed" flag).

Covers two new features:
  1. Admins/album creators can update the album title via PUT /api/photos/albums/{id}.
     - Photos cascade-rename (photo.album field rewritten).
     - Admin override extends to default (canonical) albums — the old name is
       tombstoned so the boot seeder won't recreate it; the album is demoted
       from `is_default=True` in the process.
     - Empty + clashing names rejected.
  2. Admins can flip events.rsvps_closed=true to lock the headcount.
     - Member self-RSVP (POST /events/{id}/rsvp) → 403.
     - Member guest-list update (PUT /events/{id}/rsvp/guests) → 403.
     - Admin can still RSVP members via POST /events/{id}/admin-rsvp.
     - Toggling back → members can RSVP again.
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/")

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


def login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_s():
    return login(ADMIN)


@pytest.fixture(scope="module")
def member_s():
    return login(MEMBER)


@pytest.fixture(scope="module")
def member_id(member_s):
    r = member_s.get(f"{BASE_URL}/api/auth/me", timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def mongo_db():
    """Direct DB handle for fully-reversible cleanups (e.g. removing the
    `deleted_default_albums` tombstone created by the default-rename test)."""
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip().strip('"').strip("'")
    db_name = os.environ.get("DB_NAME", "clubhaven").strip().strip('"').strip("'")
    return MongoClient(mongo_url)[db_name]


# ===================================================================
# Feature 1 — Photo album rename
# ===================================================================
class TestAlbumRename:
    def _create(self, admin_s, suffix=""):
        name = f"Iter89 Rename {suffix or uuid.uuid4().hex[:6]}"
        r = admin_s.post(f"{BASE_URL}/api/photos/albums", json={"name": name, "category": "events"}, timeout=20)
        assert r.status_code == 200, r.text
        return r.json(), name

    def _cleanup(self, admin_s, album_id):
        admin_s.delete(f"{BASE_URL}/api/photos/albums/{album_id}", timeout=20)

    def test_rename_persists_and_appears_in_list(self, admin_s):
        album, original_name = self._create(admin_s, "A")
        try:
            new_name = f"Iter89 Renamed {uuid.uuid4().hex[:6]}"
            r = admin_s.put(
                f"{BASE_URL}/api/photos/albums/{album['id']}",
                json={"name": new_name}, timeout=20,
            )
            assert r.status_code == 200, r.text
            assert r.json()["name"] == new_name

            # GET list should reflect the new name.
            lst = admin_s.get(f"{BASE_URL}/api/photos/albums", timeout=20).json()
            mine = [a for a in lst if a["id"] == album["id"]]
            assert mine and mine[0]["name"] == new_name
            # Original name should be gone from the list (uniqueness held).
            assert not any(a["name"] == original_name for a in lst)
        finally:
            self._cleanup(admin_s, album["id"])

    def test_empty_name_rejected(self, admin_s):
        album, _ = self._create(admin_s, "B")
        try:
            r = admin_s.put(
                f"{BASE_URL}/api/photos/albums/{album['id']}",
                json={"name": "   "}, timeout=20,
            )
            assert r.status_code == 400, r.text
            assert "empty" in r.text.lower()
        finally:
            self._cleanup(admin_s, album["id"])

    def test_clashing_name_rejected(self, admin_s):
        a1, n1 = self._create(admin_s, "C1")
        a2, _ = self._create(admin_s, "C2")
        try:
            r = admin_s.put(
                f"{BASE_URL}/api/photos/albums/{a2['id']}",
                json={"name": n1.lower()},  # case-insensitive collision
                timeout=20,
            )
            assert r.status_code == 400, r.text
            assert "already exists" in r.text.lower()
        finally:
            self._cleanup(admin_s, a1["id"])
            self._cleanup(admin_s, a2["id"])

    def test_default_album_rename_now_allowed_for_admins(self, admin_s, mongo_db):
        """Iter 89.2 — admins have override authority on default albums too.
        The rename tombstones the old canonical name so the boot seeder won't
        resurrect it, and demotes the album to a regular (non-default) one.
        Cleanup restores the canonical name, removes the tombstone, and
        re-flags the album as default so the suite is fully reversible."""
        lst = admin_s.get(f"{BASE_URL}/api/photos/albums", timeout=20).json()
        defaults = [a for a in lst if a.get("is_default")]
        if not defaults:
            pytest.skip("no default albums in this environment")
        d = defaults[0]
        original_name = d["name"]
        new_name = f"Iter89.2 Renamed Default {uuid.uuid4().hex[:6]}"
        try:
            r = admin_s.put(
                f"{BASE_URL}/api/photos/albums/{d['id']}",
                json={"name": new_name}, timeout=20,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["name"] == new_name

            # GET list: the new name is present, the old canonical name is gone,
            # AND the album lost its is_default badge.
            lst2 = admin_s.get(f"{BASE_URL}/api/photos/albums", timeout=20).json()
            mine = next((a for a in lst2 if a["id"] == d["id"]), None)
            assert mine is not None
            assert mine["name"] == new_name
            assert mine.get("is_default") is False
            assert not any(a["name"] == original_name for a in lst2)

            # Tombstone exists so the seeder skips this canonical name on boot.
            tomb = mongo_db.deleted_default_albums.find_one({"name": original_name})
            assert tomb is not None
            assert tomb.get("renamed_to") == new_name
        finally:
            # Fully reverse the test mutation so the suite stays idempotent.
            admin_s.put(
                f"{BASE_URL}/api/photos/albums/{d['id']}",
                json={"name": original_name}, timeout=20,
            )
            mongo_db.deleted_default_albums.delete_one({"name": original_name})
            mongo_db.photo_albums.update_one({"id": d["id"]}, {"$set": {"is_default": True}})

    def test_category_change_still_works_alongside_name(self, admin_s):
        album, _ = self._create(admin_s, "E")
        try:
            new_name = f"Iter89 Cat+Name {uuid.uuid4().hex[:6]}"
            r = admin_s.put(
                f"{BASE_URL}/api/photos/albums/{album['id']}",
                json={"name": new_name, "category": "community"}, timeout=20,
            )
            assert r.status_code == 200, r.text
            payload = r.json()
            assert payload["name"] == new_name
            assert payload["category"] == "community"
        finally:
            self._cleanup(admin_s, album["id"])


# ===================================================================
# Feature 2 — events.rsvps_closed lockdown
# ===================================================================
class TestRsvpLockdown:
    def _create_event(self, admin_s):
        r = admin_s.post(
            f"{BASE_URL}/api/events",
            json={
                "title": f"Iter89 Lockdown {uuid.uuid4().hex[:6]}",
                "description": "lockdown probe",
                "location": "online",
                "start_at": "2026-11-20T18:00:00Z",
                "category": "social",
            }, timeout=20,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def _cleanup_event(self, admin_s, event_id):
        admin_s.delete(f"{BASE_URL}/api/events/{event_id}", timeout=20)

    def test_event_out_includes_rsvps_closed(self, admin_s, member_s):
        ev = self._create_event(admin_s)
        try:
            r = member_s.get(f"{BASE_URL}/api/events/{ev['id']}", timeout=20)
            assert r.status_code == 200, r.text
            body = r.json()
            assert "rsvps_closed" in body
            assert body["rsvps_closed"] is False  # default
        finally:
            self._cleanup_event(admin_s, ev["id"])

    def test_member_self_rsvp_blocked_when_closed(self, admin_s, member_s):
        ev = self._create_event(admin_s)
        try:
            # baseline: member can RSVP
            r = member_s.post(f"{BASE_URL}/api/events/{ev['id']}/rsvp", json={}, timeout=20)
            assert r.status_code == 200, r.text
            # member cancels to start clean
            member_s.post(f"{BASE_URL}/api/events/{ev['id']}/rsvp", json={}, timeout=20)
            # admin closes RSVPs
            r = admin_s.put(
                f"{BASE_URL}/api/events/{ev['id']}",
                json={"rsvps_closed": True}, timeout=20,
            )
            assert r.status_code == 200 and r.json()["rsvps_closed"] is True
            # member can't RSVP anymore
            r = member_s.post(f"{BASE_URL}/api/events/{ev['id']}/rsvp", json={}, timeout=20)
            assert r.status_code == 403, r.text
            assert "closed" in r.text.lower()
        finally:
            self._cleanup_event(admin_s, ev["id"])

    def test_admin_rsvp_for_member_still_works_when_closed(self, admin_s, member_s, member_id):
        ev = self._create_event(admin_s)
        try:
            admin_s.put(f"{BASE_URL}/api/events/{ev['id']}",
                        json={"rsvps_closed": True}, timeout=20)
            r = admin_s.post(
                f"{BASE_URL}/api/events/{ev['id']}/admin-rsvp",
                json={"user_id": member_id, "send_email": False}, timeout=20,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("rsvped") is True
            assert body.get("user_id") == member_id
        finally:
            admin_s.delete(f"{BASE_URL}/api/events/{ev['id']}/rsvps/{member_id}", timeout=20)
            self._cleanup_event(admin_s, ev["id"])

    def test_member_guest_update_blocked_when_closed(self, admin_s, member_s, member_id):
        ev = self._create_event(admin_s)
        try:
            # member RSVPs first (lockdown not yet active)
            r = member_s.post(f"{BASE_URL}/api/events/{ev['id']}/rsvp", json={}, timeout=20)
            assert r.status_code == 200, r.text
            # admin closes RSVPs
            admin_s.put(f"{BASE_URL}/api/events/{ev['id']}",
                        json={"rsvps_closed": True}, timeout=20)
            # member's guest list update is now 403
            r = member_s.put(
                f"{BASE_URL}/api/events/{ev['id']}/rsvp/guests",
                json={"guests": [{"name": "Plus One"}]}, timeout=20,
            )
            assert r.status_code == 403, r.text
        finally:
            admin_s.delete(f"{BASE_URL}/api/events/{ev['id']}/rsvps/{member_id}", timeout=20)
            self._cleanup_event(admin_s, ev["id"])

    def test_reopen_restores_member_rsvp(self, admin_s, member_s):
        ev = self._create_event(admin_s)
        try:
            admin_s.put(f"{BASE_URL}/api/events/{ev['id']}",
                        json={"rsvps_closed": True}, timeout=20)
            r = member_s.post(f"{BASE_URL}/api/events/{ev['id']}/rsvp", json={}, timeout=20)
            assert r.status_code == 403
            # reopen
            r = admin_s.put(f"{BASE_URL}/api/events/{ev['id']}",
                            json={"rsvps_closed": False}, timeout=20)
            assert r.status_code == 200 and r.json()["rsvps_closed"] is False
            # member can RSVP again
            r = member_s.post(f"{BASE_URL}/api/events/{ev['id']}/rsvp", json={}, timeout=20)
            assert r.status_code == 200, r.text
        finally:
            self._cleanup_event(admin_s, ev["id"])

    def test_sub_event_lockdown_is_independent_of_parent(self, admin_s, member_s, member_id):
        """Iter 89.1: sub-events get the same RSVP lockdown.
        The parent (umbrella) event refuses direct RSVPs anyway, so the
        lockdown only matters on the child. Verify the child's rsvps_closed
        flag blocks the member while the admin-rsvp path still works."""
        parent = self._create_event(admin_s)
        try:
            # Create a sub-event under the parent.
            r = admin_s.post(
                f"{BASE_URL}/api/events",
                json={
                    "title": f"Iter89 Sub {uuid.uuid4().hex[:6]}",
                    "description": "",
                    "location": "online",
                    "start_at": "2026-11-21T18:00:00Z",
                    "category": "social",
                    "parent_event_id": parent["id"],
                }, timeout=20,
            )
            assert r.status_code == 200, r.text
            sub = r.json()
            try:
                # Baseline: member can RSVP to the sub.
                r = member_s.post(f"{BASE_URL}/api/events/{sub['id']}/rsvp", json={}, timeout=20)
                assert r.status_code == 200, r.text
                member_s.post(f"{BASE_URL}/api/events/{sub['id']}/rsvp", json={}, timeout=20)  # cancel

                # Admin closes RSVPs on the SUB ONLY (parent unaffected).
                r = admin_s.put(
                    f"{BASE_URL}/api/events/{sub['id']}",
                    json={"rsvps_closed": True}, timeout=20,
                )
                assert r.status_code == 200 and r.json()["rsvps_closed"] is True

                # Parent should still report rsvps_closed=false.
                p = admin_s.get(f"{BASE_URL}/api/events/{parent['id']}", timeout=20).json()
                assert p["rsvps_closed"] is False

                # Member self-RSVP on sub → 403.
                r = member_s.post(f"{BASE_URL}/api/events/{sub['id']}/rsvp", json={}, timeout=20)
                assert r.status_code == 403, r.text

                # Admin can still RSVP a member onto the locked sub.
                r = admin_s.post(
                    f"{BASE_URL}/api/events/{sub['id']}/admin-rsvp",
                    json={"user_id": member_id, "send_email": False}, timeout=20,
                )
                assert r.status_code == 200, r.text
                assert r.json().get("rsvped") is True
            finally:
                admin_s.delete(f"{BASE_URL}/api/events/{sub['id']}/rsvps/{member_id}", timeout=20)
                admin_s.delete(f"{BASE_URL}/api/events/{sub['id']}", timeout=20)
        finally:
            self._cleanup_event(admin_s, parent["id"])
