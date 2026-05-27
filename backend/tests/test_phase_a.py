"""Phase A backend tests for AOP member portal:
chapters region/state, hours new fields, member address/birthdate/branch/status,
award granted_at, /members-new, /members-birthdays, set status override."""
import os
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
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def member():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def member_id(member):
    me = member.get(f"{API}/auth/me", timeout=15)
    assert me.status_code == 200
    return me.json()["id"]


# ---------- Chapters: region & state ----------
def test_chapter_create_with_region_state(admin):
    name = f"TEST_Ch_{uuid.uuid4().hex[:6]}"
    r = admin.post(f"{API}/chapters", json={
        "name": name,
        "region": "Northeast",
        "state": "NY",
        "founded_year": 1989,
        "description": "Test chapter",
    }, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == name
    assert body["region"] == "Northeast"
    assert body["state"] == "NY"
    assert body["founded_year"] == 1989
    cid = body["id"]
    # GET list verifies persistence
    items = requests.get(f"{API}/chapters", timeout=15).json()
    found = next((c for c in items if c["id"] == cid), None)
    assert found is not None
    assert found["region"] == "Northeast"
    assert found["state"] == "NY"
    # PUT update region/state
    u = admin.put(f"{API}/chapters/{cid}", json={"region": "Southeast", "state": "FL"}, timeout=15)
    assert u.status_code == 200
    assert u.json()["region"] == "Southeast"
    assert u.json()["state"] == "FL"
    # cleanup
    admin.delete(f"{API}/chapters/{cid}", timeout=15)


def test_chapters_list_has_region_state_fields(admin):
    items = requests.get(f"{API}/chapters", timeout=15).json()
    assert len(items) > 0
    for c in items:
        assert "region" in c
        assert "state" in c


# ---------- Hours: new fields ----------
def test_hours_log_with_new_fields(member, member_id, admin):
    payload = {
        "hours": 1.5,
        "date": datetime.now(timezone.utc).isoformat(),
        "event_type": "aop_related",
        "agency_name": "TEST_Red Cross",
        "activity": "TEST_food drive",
        "host_name": "Jane Host",
        "host_email": "jane@example.com",
        "host_phone": "555-0101",
    }
    r = member.post(f"{API}/hours", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    hid = body["id"]
    for k in ("event_type", "agency_name", "activity", "host_name", "host_email", "host_phone"):
        assert body[k] == payload[k], f"field {k} mismatch: {body.get(k)}"
    assert body["status"] == "pending"

    # GET /api/me/hours
    mine = member.get(f"{API}/me/hours", timeout=15).json()
    entry = next((h for h in mine if h["id"] == hid), None)
    assert entry is not None
    assert entry["event_type"] == "aop_related"
    assert entry["agency_name"] == "TEST_Red Cross"
    assert entry["host_name"] == "Jane Host"
    assert entry["host_email"] == "jane@example.com"
    assert entry["host_phone"] == "555-0101"
    assert entry["activity"] == "TEST_food drive"

    # admin /api/hours
    adm = admin.get(f"{API}/hours?status_filter=pending", timeout=15).json()
    e2 = next((h for h in adm if h["id"] == hid), None)
    assert e2 is not None
    assert e2["agency_name"] == "TEST_Red Cross"

    # cleanup
    member.delete(f"{API}/hours/{hid}", timeout=15)


# ---------- Admin create/update member: address, birthdate, branch, status ----------
def test_admin_create_member_with_new_fields(admin):
    email = f"test_pa_{uuid.uuid4().hex[:6]}@example.com"
    r = admin.post(f"{API}/admin/members", json={
        "email": email,
        "password": "Password123!",
        "first_name": "TEST",
        "last_name": "User",
        "address": "123 Main St, Anywhere",
        "birthdate": "1990-06-15",
        "branch_of_service": "Army",
        "member_status": "active",
    }, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    uid = body["id"]
    assert body["address"] == "123 Main St, Anywhere"
    assert body["birthdate"] == "1990-06-15"
    assert body["branch_of_service"] == "Army"
    assert body["status"] == "active"
    assert body.get("status_override") == "active"

    # GET /api/members/{id}
    g = admin.get(f"{API}/members/{uid}", timeout=15).json()
    assert g["address"] == "123 Main St, Anywhere"
    assert g["birthdate"] == "1990-06-15"
    assert g["branch_of_service"] == "Army"

    # Update via PUT /api/members/{id}
    u = admin.put(f"{API}/members/{uid}", json={
        "address": "456 Side Rd",
        "birthdate": "1991-07-20",
        "branch_of_service": "Navy",
        "member_status": "inactive",
    }, timeout=15)
    assert u.status_code == 200, u.text
    ub = u.json()
    assert ub["address"] == "456 Side Rd"
    assert ub["birthdate"] == "1991-07-20"
    assert ub["branch_of_service"] == "Navy"
    assert ub["status_override"] == "inactive"
    assert ub["status"] == "inactive"

    # cleanup
    admin.delete(f"{API}/members/{uid}", timeout=15)


# ---------- PUT /api/members/{id}/status ----------
def test_set_member_status_endpoint_deceased_then_active(admin):
    # Create a temp member
    email = f"test_st_{uuid.uuid4().hex[:6]}@example.com"
    r = admin.post(f"{API}/admin/members", json={
        "email": email, "password": "Password123!", "first_name": "TEST", "last_name": "Status",
    }, timeout=15)
    uid = r.json()["id"]

    # Set deceased
    s1 = admin.put(f"{API}/members/{uid}/status", json={"status": "deceased"}, timeout=15)
    assert s1.status_code == 200, s1.text
    j = s1.json()
    assert j["status"] == "deceased"
    assert j["status_override"] == "deceased"
    assert j["deceased_at"], "deceased_at should be auto-set"

    # Set back to active -> deceased_at cleared
    s2 = admin.put(f"{API}/members/{uid}/status", json={"status": "active"}, timeout=15)
    assert s2.status_code == 200
    j2 = s2.json()
    assert j2["status"] == "active"
    assert j2["status_override"] == "active"
    assert j2.get("deceased_at") in (None, ""), f"expected null deceased_at, got {j2.get('deceased_at')}"

    # cleanup
    admin.delete(f"{API}/members/{uid}", timeout=15)


# ---------- Award grant with custom granted_at ----------
def test_award_grant_custom_granted_at(admin, member_id):
    name = f"TEST_Aw_{uuid.uuid4().hex[:6]}"
    a = admin.post(f"{API}/awards", json={"name": name, "icon": "trophy"}, timeout=15)
    assert a.status_code == 200, a.text
    aid = a.json()["id"]
    custom_date = "2020-03-15T00:00:00+00:00"
    g = admin.post(f"{API}/awards/{aid}/grant", json={
        "user_id": member_id, "reason": "TEST_back-dated", "granted_at": custom_date
    }, timeout=15)
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["granted_at"] == custom_date
    # Verify via member listing
    listing = requests.get(f"{API}/members/{member_id}/awards", timeout=15).json()
    found = next((x for x in listing if x["id"] == body["id"]), None)
    assert found is not None
    assert found["granted_at"] == custom_date
    # cleanup
    admin.delete(f"{API}/awards/grants/{body['id']}", timeout=15)
    admin.delete(f"{API}/awards/{aid}", timeout=15)


# ---------- /api/members-new ----------
def test_new_members_returns_recent_first(admin):
    # Create two members
    ids = []
    for i in range(2):
        em = f"test_new_{uuid.uuid4().hex[:6]}@example.com"
        r = admin.post(f"{API}/admin/members", json={
            "email": em, "password": "Password123!", "first_name": "TEST", "last_name": f"New{i}",
        }, timeout=15)
        assert r.status_code == 200
        ids.append(r.json()["id"])
    # Query
    r = requests.get(f"{API}/members-new?days=30&limit=6", timeout=15)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    found_ids = [x["id"] for x in items]
    for uid in ids:
        assert uid in found_ids, f"newly created member {uid} not in /members-new"
    # Ordering: created_at desc
    if len(items) >= 2:
        for i in range(len(items) - 1):
            assert items[i].get("join_date", "") >= items[i + 1].get("join_date", "")
    # cleanup
    for uid in ids:
        admin.delete(f"{API}/members/{uid}", timeout=15)


# ---------- /api/members-birthdays ----------
def test_upcoming_birthdays(admin):
    today = datetime.now(timezone.utc).date()
    # Create a member with birthdate 5 days from now (preserve year=1985)
    target = today + timedelta(days=5)
    bd_str = f"1985-{target.month:02d}-{target.day:02d}"
    em = f"test_bd_{uuid.uuid4().hex[:6]}@example.com"
    r = admin.post(f"{API}/admin/members", json={
        "email": em, "password": "Password123!", "first_name": "TEST", "last_name": "Birthday",
        "birthdate": bd_str,
    }, timeout=15)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]

    # Query
    rb = requests.get(f"{API}/members-birthdays?days=30&limit=25", timeout=15)
    assert rb.status_code == 200, rb.text
    items = rb.json()
    assert isinstance(items, list)
    found = next((x for x in items if x["id"] == uid), None)
    assert found is not None, "newly created birthdate member missing"
    assert "next_birthday" in found
    assert "days_until_birthday" in found
    assert "age_turning" in found
    assert found["days_until_birthday"] == 5

    # Ascending order by days_until_birthday
    if len(items) >= 2:
        for i in range(len(items) - 1):
            assert items[i]["days_until_birthday"] <= items[i + 1]["days_until_birthday"]

    # cleanup
    admin.delete(f"{API}/members/{uid}", timeout=15)


# ---------- PUT /api/members/me with address/birthdate ----------
def test_update_me_address_birthdate(member):
    me0 = member.get(f"{API}/auth/me", timeout=15).json()
    addr_orig = me0.get("address", "")
    bd_orig = me0.get("birthdate", "")

    u = member.put(f"{API}/members/me", json={
        "address": "TEST_999 Profile Way",
        "birthdate": "1988-04-22",
    }, timeout=15)
    assert u.status_code == 200, u.text
    body = u.json()
    assert body["address"] == "TEST_999 Profile Way"
    assert body["birthdate"] == "1988-04-22"

    # restore
    member.put(f"{API}/members/me", json={"address": addr_orig, "birthdate": bd_orig}, timeout=15)
