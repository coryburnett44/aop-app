"""Phase N - 9-item enhancement batch:
1. Forgot/Reset Password
2. Photo Album Cover + Category + Filter
3. Chat TTL + Reply (server-side schema)
4. Document folders + multi-doc upload
5. Members filter/sort (smoke - frontend)
6. Hours review enrichment (host fields)
7. Cascade delete member
"""
import os
import io
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASS = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASS = "Member123!"


# ---------- shared fixtures ----------
@pytest.fixture(scope="session")
def mongo_db():
    mc = MongoClient("mongodb://localhost:27017")
    yield mc["clubhaven_db"]
    mc.close()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="session")
def member():
    return _login(MEMBER_EMAIL, MEMBER_PASS)


# =======================================================================
# 1. FORGOT PASSWORD / RESET PASSWORD
# =======================================================================
class TestForgotReset:
    def test_forgot_password_returns_200_always(self):
        # valid email
        r = requests.post(f"{API}/auth/forgot-password", json={"email": MEMBER_EMAIL}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # unknown email - must still 200 (no enum leak)
        r = requests.post(f"{API}/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex[:6]}@example.com"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_reset_password_full_flow(self, mongo_db):
        # request reset
        r = requests.post(f"{API}/auth/forgot-password", json={"email": MEMBER_EMAIL}, timeout=15)
        assert r.status_code == 200
        # grab latest token from DB
        tok = mongo_db.password_reset_tokens.find_one(
            {"used": False}, sort=[("created_at", -1)]
        )
        assert tok is not None, "No reset token persisted"
        token = tok["token"]

        # reset to a temp password
        new_pw = "TempReset123!"
        r = requests.post(f"{API}/auth/reset-password", json={"token": token, "new_password": new_pw}, timeout=15)
        assert r.status_code == 200, r.text

        # login with new password
        r = requests.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": new_pw}, timeout=15)
        assert r.status_code == 200, "Login with new password failed"

        # reused token must 400
        r2 = requests.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "Whatever123!"}, timeout=15)
        assert r2.status_code == 400

        # restore original password
        r = requests.post(f"{API}/auth/forgot-password", json={"email": MEMBER_EMAIL}, timeout=15)
        tok2 = mongo_db.password_reset_tokens.find_one({"used": False}, sort=[("created_at", -1)])
        requests.post(f"{API}/auth/reset-password", json={"token": tok2["token"], "new_password": MEMBER_PASS}, timeout=15)
        r = requests.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASS}, timeout=15)
        assert r.status_code == 200, "Restore-original-password failed"

    def test_reset_password_invalid_token(self):
        r = requests.post(f"{API}/auth/reset-password", json={"token": "garbage-not-in-db", "new_password": "X9aaaaaa!"}, timeout=15)
        assert r.status_code == 400


# =======================================================================
# 2. PHOTO ALBUM COVER + CATEGORY
# =======================================================================
class TestPhotoAlbums:
    def test_list_albums_has_category_and_cover(self):
        r = requests.get(f"{API}/photos/albums", timeout=20)
        assert r.status_code == 200
        albums = r.json()
        assert isinstance(albums, list)
        assert len(albums) >= 1
        for a in albums[:3]:
            assert "category" in a
            assert "cover_url" in a or a.get("cover_url") in (None, "")
        # Categories observed
        cats = {a.get("category") for a in albums}
        assert cats.intersection({"anniversary", "ceremony", "conference", "tournament", "line", "community", "other"})

    def test_filter_by_category(self):
        r = requests.get(f"{API}/photos/albums", params={"category": "tournament"}, timeout=20)
        assert r.status_code == 200
        albums = r.json()
        # All returned must be tournament
        for a in albums:
            assert a.get("category") == "tournament", f"unexpected category {a.get('category')}"

    def test_update_album_category_as_admin(self, admin):
        r = admin.get(f"{API}/photos/albums", timeout=20)
        assert r.status_code == 200
        albums = r.json()
        assert albums, "no albums to mutate"
        target = albums[0]
        aid = target["id"]
        original_cat = target.get("category")
        new_cat = "ceremony" if original_cat != "ceremony" else "other"
        r = admin.put(f"{API}/photos/albums/{aid}", json={"category": new_cat}, timeout=15)
        assert r.status_code == 200, r.text
        # verify
        r = requests.get(f"{API}/photos/albums", timeout=20)
        updated = next((a for a in r.json() if a["id"] == aid), None)
        assert updated and updated.get("category") == new_cat
        # restore
        admin.put(f"{API}/photos/albums/{aid}", json={"category": original_cat}, timeout=15)


# =======================================================================
# 3. CHAT - TTL + REPLY schema
# =======================================================================
class TestChatTTLReply:
    def _ensure_conv(self, admin):
        r = admin.get(f"{API}/conversations", timeout=15)
        assert r.status_code == 200
        convs = r.json()
        if convs:
            return convs[0]["id"]
        # create one
        # find members
        r = admin.get(f"{API}/members", timeout=15)
        member_ids = [m["id"] for m in r.json()[:2]]
        r = admin.post(f"{API}/conversations", json={"member_ids": member_ids, "is_group": False}, timeout=15)
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def test_conversation_has_ttl_field(self, admin):
        cid = self._ensure_conv(admin)
        r = admin.get(f"{API}/conversations", timeout=15)
        conv = next((c for c in r.json() if c["id"] == cid), None)
        assert conv is not None
        assert "ttl" in conv, f"conversation missing ttl field: {list(conv.keys())}"

    def test_update_conversation_ttl(self, admin):
        cid = self._ensure_conv(admin)
        r = admin.put(f"{API}/conversations/{cid}", json={"ttl": "1h"}, timeout=15)
        assert r.status_code == 200, r.text
        r = admin.get(f"{API}/conversations", timeout=15)
        conv = next((c for c in r.json() if c["id"] == cid), None)
        assert conv.get("ttl") == "1h"
        # reset
        admin.put(f"{API}/conversations/{cid}", json={"ttl": "off"}, timeout=15)

    def test_send_message_with_ttl_override_and_reply(self, admin):
        cid = self._ensure_conv(admin)
        # base message
        r = admin.post(f"{API}/conversations/{cid}/messages", json={"body": f"Base-{uuid.uuid4().hex[:6]}"}, timeout=15)
        assert r.status_code in (200, 201), r.text
        base = r.json()
        base_id = base.get("id")
        assert base_id, base
        # reply with ttl override
        r = admin.post(
            f"{API}/conversations/{cid}/messages",
            json={"body": "Reply with 24h ttl", "reply_to": base_id, "ttl": "24h"},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        msg = r.json()
        assert msg.get("reply_to") == base_id
        assert msg.get("ttl_seconds") in (86400, 86400.0), f"got ttl_seconds={msg.get('ttl_seconds')}"


# =======================================================================
# 4. DOCUMENT FOLDERS (2-level) + MULTI-DOC UPLOAD
# =======================================================================
class TestDocsFolders:
    def test_create_root_subfolder_and_block_third_level(self, admin):
        root_name = f"TEST_Bylaws_{uuid.uuid4().hex[:6]}"
        r = admin.post(f"{API}/document-folders", json={"name": root_name, "parent_id": None}, timeout=15)
        assert r.status_code in (200, 201), r.text
        root = r.json()
        root_id = root["id"]
        assert root.get("parent_id") in (None, "")

        # subfolder
        sub_name = f"TEST_Sub_{uuid.uuid4().hex[:6]}"
        r = admin.post(f"{API}/document-folders", json={"name": sub_name, "parent_id": root_id}, timeout=15)
        assert r.status_code in (200, 201), r.text
        sub = r.json()
        sub_id = sub["id"]

        # 3rd level should fail with 400
        r = admin.post(f"{API}/document-folders", json={"name": "TEST_TooDeep", "parent_id": sub_id}, timeout=15)
        assert r.status_code == 400, f"Expected 400 for 3rd level, got {r.status_code}: {r.text}"

        # GET list includes doc_count
        r = admin.get(f"{API}/document-folders", timeout=15)
        assert r.status_code == 200
        listed = r.json()
        found = next((f for f in listed if f["id"] == root_id), None)
        assert found is not None
        assert "doc_count" in found

        # cleanup
        admin.delete(f"{API}/document-folders/{sub_id}", timeout=15)
        admin.delete(f"{API}/document-folders/{root_id}", timeout=15)

    def test_bulk_upload(self, admin):
        files = [
            ("files", (f"TEST_doc_{i}.txt", io.BytesIO(f"hello {i}".encode()), "text/plain"))
            for i in range(3)
        ]
        r = admin.post(f"{API}/documents/bulk", files=files, timeout=30)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert "uploaded" in data
        assert "failed" in data
        assert len(data["uploaded"]) == 3, f"expected 3 uploaded, got {data}"
        # cleanup
        for d in data["uploaded"]:
            did = d.get("id") if isinstance(d, dict) else None
            if did:
                admin.delete(f"{API}/documents/{did}", timeout=15)


# =======================================================================
# 6. HOURS REVIEW ENRICHMENT - check fields persisted + returned
# =======================================================================
class TestHoursEnrichment:
    def test_submit_hours_with_full_fields(self, member, admin):
        payload = {
            "hours": 2.5,
            "activity": "TEST_packed care boxes",
            "date": "2026-01-10T00:00:00Z",
            "event_type": "aop_related",
            "agency_name": "Dorn VA",
            "host_name": "Jane Doe",
            "host_email": "jane@example.com",
            "host_phone": "555-1234",
            "description": "TEST_packed care boxes",
        }
        r = member.post(f"{API}/hours", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        hid = created.get("id")
        assert hid

        # admin list
        r = admin.get(f"{API}/hours", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        found = next((h for h in rows if h.get("id") == hid), None)
        assert found is not None
        # required enrichment fields
        for k in ("hours", "date", "event_type", "agency_name", "host_name", "host_email", "host_phone", "description"):
            assert k in found, f"hours admin row missing {k}: {found.keys()}"
        assert found.get("agency_name") == "Dorn VA"
        assert found.get("host_email") == "jane@example.com"
        # cleanup
        admin.delete(f"{API}/hours/{hid}", timeout=15)


# =======================================================================
# 7. CASCADE DELETE MEMBER
# =======================================================================
class TestCascadeDelete:
    def test_delete_member_cascades(self, admin, mongo_db):
        # Create a throwaway member
        email = f"test-cascade-{uuid.uuid4().hex[:6]}@example.com"
        r = admin.post(f"{API}/admin/members", json={
            "name": "TEST Cascade Member",
            "email": email,
            "password": "Cascade123!",
            "role": "member",
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        mid = r.json()["id"]

        # delete cascade
        r = admin.delete(f"{API}/members/{mid}", timeout=20)
        assert r.status_code == 200, r.text

        # verify users row gone
        u = mongo_db.users.find_one({"id": mid})
        assert u is None, "user not deleted"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
