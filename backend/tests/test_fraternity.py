"""ClubHaven fraternity-extension backend API tests.
Covers: chapters, tiers, awards, hours, photos, documents, file proxy, admin stats."""
import os
import io
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASSWORD = "Member123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def member_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"member login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def member_id(member_session):
    me = member_session.get(f"{API}/auth/me", timeout=15)
    assert me.status_code == 200
    return me.json()["id"]


# ---------- public_user fields ----------
def test_public_user_includes_fraternity_fields(member_session):
    me = member_session.get(f"{API}/auth/me", timeout=15)
    assert me.status_code == 200
    j = me.json()
    for f in ("within_grace", "is_expired", "chapter_id", "tier_id", "email_verified"):
        assert f in j, f"public_user missing field: {f}"


# ---------- Chapters ----------
def test_chapters_seeded(admin_session):
    r = requests.get(f"{API}/chapters", timeout=15)
    assert r.status_code == 200
    items = r.json()
    names = {c["name"] for c in items}
    assert {"Alpha Beta", "Gamma Delta", "Epsilon Theta"}.issubset(names)
    for c in items:
        assert "member_count" in c and isinstance(c["member_count"], int)


def test_chapters_create_admin_only(member_session):
    r = member_session.post(f"{API}/chapters", json={"name": "TEST_X"}, timeout=15)
    assert r.status_code == 403


def test_chapters_crud(admin_session):
    name = f"TEST_Chapter_{uuid.uuid4().hex[:6]}"
    r = admin_session.post(f"{API}/chapters", json={"name": name, "school": "TEST U", "city": "Nowhere", "founded_year": 2024}, timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert r.json()["name"] == name
    assert r.json()["member_count"] == 0
    # update
    upd = admin_session.put(f"{API}/chapters/{cid}", json={"city": "Updated City"}, timeout=15)
    assert upd.status_code == 200
    assert upd.json()["city"] == "Updated City"
    # delete
    d = admin_session.delete(f"{API}/chapters/{cid}", timeout=15)
    assert d.status_code == 200
    # confirm gone
    after = requests.get(f"{API}/chapters", timeout=15).json()
    assert cid not in {c["id"] for c in after}


def test_chapter_delete_unassigns_members(admin_session, member_id):
    # Create chapter, assign member, delete chapter, member should have no chapter_id
    name = f"TEST_DelCh_{uuid.uuid4().hex[:6]}"
    r = admin_session.post(f"{API}/chapters", json={"name": name}, timeout=15)
    cid = r.json()["id"]
    assign = admin_session.put(f"{API}/members/{member_id}/chapter", json={"chapter_id": cid}, timeout=15)
    assert assign.status_code == 200
    assert assign.json()["chapter_id"] == cid
    # delete chapter
    admin_session.delete(f"{API}/chapters/{cid}", timeout=15)
    after = admin_session.get(f"{API}/members/{member_id}", timeout=15).json()
    assert after.get("chapter_id") in (None, "")


# ---------- Tiers ----------
def test_tiers_seeded():
    r = requests.get(f"{API}/tiers", timeout=15)
    assert r.status_code == 200
    items = r.json()
    names = [t["name"] for t in items]
    for n in ("Pledge", "Active", "Alumni", "Lifetime", "Honorary"):
        assert n in names, f"tier missing: {n}"
    # sorted by order ascending
    orders = [t["order"] for t in items]
    assert orders == sorted(orders)


def test_tiers_admin_only(member_session):
    assert member_session.post(f"{API}/tiers", json={"name": "TEST_T"}, timeout=15).status_code == 403
    assert member_session.put(f"{API}/tiers/x", json={"name": "y"}, timeout=15).status_code == 403
    assert member_session.delete(f"{API}/tiers/x", timeout=15).status_code == 403


def test_tier_crud(admin_session):
    name = f"TEST_Tier_{uuid.uuid4().hex[:6]}"
    c = admin_session.post(f"{API}/tiers", json={"name": name, "order": 99, "annual_dues": 12.5}, timeout=15)
    assert c.status_code == 200
    tid = c.json()["id"]
    u = admin_session.put(f"{API}/tiers/{tid}", json={"annual_dues": 25.0}, timeout=15)
    assert u.status_code == 200 and u.json()["annual_dues"] == 25.0
    d = admin_session.delete(f"{API}/tiers/{tid}", timeout=15)
    assert d.status_code == 200


# ---------- Awards ----------
def test_awards_seeded():
    r = requests.get(f"{API}/awards", timeout=15)
    assert r.status_code == 200
    items = r.json()
    expected = {"Founder's Medal", "Service Star", "Brotherhood Award", "Scholar", "Rookie of the Year"}
    assert expected.issubset({a["name"] for a in items})
    for a in items:
        assert "granted_count" in a


def test_award_admin_only(member_session):
    r = member_session.post(f"{API}/awards", json={"name": "TEST_A"}, timeout=15)
    assert r.status_code == 403


def test_award_grant_revoke_flow(admin_session, member_id):
    name = f"TEST_Award_{uuid.uuid4().hex[:6]}"
    a = admin_session.post(f"{API}/awards", json={"name": name, "icon": "trophy"}, timeout=15)
    assert a.status_code == 200
    aid = a.json()["id"]
    # grant
    g = admin_session.post(f"{API}/awards/{aid}/grant", json={"user_id": member_id, "reason": "for testing"}, timeout=15)
    assert g.status_code == 200, g.text
    grant = g.json()
    assert grant["award_id"] == aid and grant["user_id"] == member_id
    assert grant["reason"] == "for testing"
    grant_id = grant["id"]
    # duplicate grant -> 400
    dup = admin_session.post(f"{API}/awards/{aid}/grant", json={"user_id": member_id}, timeout=15)
    assert dup.status_code == 400
    # member awards listing
    list_resp = requests.get(f"{API}/members/{member_id}/awards", timeout=15)
    assert list_resp.status_code == 200
    assert any(x["id"] == grant_id for x in list_resp.json())
    # revoke
    rv = admin_session.delete(f"{API}/awards/grants/{grant_id}", timeout=15)
    assert rv.status_code == 200
    # cleanup award
    admin_session.delete(f"{API}/awards/{aid}", timeout=15)


# ---------- Hours ----------
def test_hours_member_log_and_admin_review(admin_session, member_session, member_id):
    # member logs
    r = member_session.post(f"{API}/hours", json={
        "hours": 2.5, "description": "TEST_helping at event",
        "date": datetime.now(timezone.utc).isoformat(),
    }, timeout=15)
    assert r.status_code == 200, r.text
    hid = r.json()["id"]
    assert r.json()["status"] == "pending"
    # member sees it
    mine = member_session.get(f"{API}/me/hours", timeout=15)
    assert mine.status_code == 200
    assert any(h["id"] == hid for h in mine.json())
    # admin list with status filter
    pend = admin_session.get(f"{API}/hours?status_filter=pending", timeout=15)
    assert pend.status_code == 200
    assert any(h["id"] == hid for h in pend.json())
    # member cannot list all hours
    forbidden = member_session.get(f"{API}/hours", timeout=15)
    assert forbidden.status_code == 403
    # approve
    rev = admin_session.put(f"{API}/hours/{hid}/review", json={"status": "approved", "note": "ok"}, timeout=15)
    assert rev.status_code == 200
    assert rev.json()["status"] == "approved"
    assert rev.json()["reviewed_by"]
    # cleanup
    member_session.delete(f"{API}/hours/{hid}", timeout=15)


# ---------- Member admin operations ----------
def test_role_chapter_tier_assignment(admin_session, member_session, member_id):
    # role toggle
    r = admin_session.put(f"{API}/members/{member_id}/role", json={"role": "admin"}, timeout=15)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    r2 = admin_session.put(f"{API}/members/{member_id}/role", json={"role": "member"}, timeout=15)
    assert r2.status_code == 200 and r2.json()["role"] == "member"

    # chapter assignment
    chapters = requests.get(f"{API}/chapters", timeout=15).json()
    cid = chapters[0]["id"]
    rc = admin_session.put(f"{API}/members/{member_id}/chapter", json={"chapter_id": cid}, timeout=15)
    assert rc.status_code == 200 and rc.json()["chapter_id"] == cid

    # tier assignment with extend_days
    tiers = requests.get(f"{API}/tiers", timeout=15).json()
    tid = next(t["id"] for t in tiers if t["name"] == "Active")
    before_me = admin_session.get(f"{API}/members/{member_id}", timeout=15).json()
    before_exp = before_me.get("membership_expires_at")
    rt = admin_session.put(f"{API}/members/{member_id}/tier", json={"tier_id": tid, "extend_days": 30}, timeout=15)
    assert rt.status_code == 200
    body = rt.json()
    assert body["tier_id"] == tid
    assert body["membership_tier"] == "Active"
    # expiry pushed
    if before_exp:
        assert body["membership_expires_at"] >= before_exp


# ---------- Photos / Documents / File proxy ----------
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0"
    b"\xc0\xc0\x00\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _storage_available():
    """Quick probe by attempting an upload; returns True if storage init works."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}, timeout=15)
    if r.status_code != 200:
        return False
    files = {"file": ("probe.png", PNG_BYTES, "image/png")}
    p = s.post(f"{API}/photos", files=files, data={"title": "TEST_probe", "album": "test"}, timeout=60)
    if p.status_code == 503:
        return False
    if p.status_code == 200:
        try:
            s.delete(f"{API}/photos/{p.json()['id']}", timeout=15)
        except Exception:
            pass
        return True
    return False


STORAGE_OK = _storage_available()


@pytest.mark.skipif(not STORAGE_OK, reason="object storage not available")
def test_photo_upload_list_delete(member_session):
    files = {"file": ("test.png", PNG_BYTES, "image/png")}
    r = member_session.post(f"{API}/photos", files=files, data={"title": "TEST_photo", "album": "test"}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    pid = body["id"]
    assert body["url"].startswith("/api/files/")
    assert body["album"] == "test"
    # list
    listing = requests.get(f"{API}/photos?album=test", timeout=15).json()
    assert any(p["id"] == pid for p in listing)
    # file proxy returns image
    file_url = f"{BASE_URL}{body['url']}"
    f = requests.get(file_url, timeout=30)
    assert f.status_code == 200
    assert f.headers.get("content-type", "").startswith("image/")
    assert len(f.content) > 0
    # delete (soft)
    d = member_session.delete(f"{API}/photos/{pid}", timeout=15)
    assert d.status_code == 200
    # listing should not include
    after = requests.get(f"{API}/photos?album=test", timeout=15).json()
    assert not any(p["id"] == pid for p in after)


@pytest.mark.skipif(not STORAGE_OK, reason="object storage not available")
def test_photo_upload_rejects_bad_type(member_session):
    files = {"file": ("bad.exe", b"MZbinary", "application/octet-stream")}
    r = member_session.post(f"{API}/photos", files=files, data={"title": "TEST_bad"}, timeout=30)
    assert r.status_code == 400


@pytest.mark.skipif(not STORAGE_OK, reason="object storage not available")
def test_document_upload_list_delete_and_file_proxy(member_session):
    files = {"file": ("notes.txt", b"hello fraternity", "text/plain")}
    r = member_session.post(f"{API}/documents", files=files, data={"title": "TEST_notes", "category": "test"}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    did = body["id"]
    assert body["url"].startswith("/api/files/")
    # list
    items = requests.get(f"{API}/documents?category=test", timeout=15).json()
    assert any(d["id"] == did for d in items)
    # file proxy returns the file content
    f = requests.get(f"{BASE_URL}{body['url']}", timeout=30)
    assert f.status_code == 200
    assert f.headers.get("content-type", "").startswith("text/")
    assert b"fraternity" in f.content
    # delete
    d = member_session.delete(f"{API}/documents/{did}", timeout=15)
    assert d.status_code == 200
    after = requests.get(f"{API}/documents?category=test", timeout=15).json()
    assert not any(x["id"] == did for x in after)


@pytest.mark.skipif(not STORAGE_OK, reason="object storage not available")
def test_pdf_upload(member_session):
    pdf = b"%PDF-1.4\n%TEST\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    files = {"file": ("doc.pdf", pdf, "application/pdf")}
    r = member_session.post(f"{API}/documents", files=files, data={"title": "TEST_pdf"}, timeout=60)
    assert r.status_code == 200, r.text
    member_session.delete(f"{API}/documents/{r.json()['id']}", timeout=15)


# ---------- Admin stats ----------
def test_admin_stats_fraternity_block(admin_session):
    r = admin_session.get(f"{API}/admin/stats", timeout=20)
    assert r.status_code == 200, r.text
    s = r.json()
    assert "fraternity" in s
    fr = s["fraternity"]
    for k in ("chapters", "chapter_roster", "tiers", "awards", "awards_granted", "hours_pending", "hours_approved_total"):
        assert k in fr, f"missing fraternity key: {k}"
    assert isinstance(fr["chapter_roster"], list)
    # content includes photos + documents
    assert "photos" in s["content"] and "documents" in s["content"]
