"""Iteration 91 — Overdue-dues Zeffy URL for inactive members.

When a member's status is inactive (either an admin set status_override="inactive"
or the grace-period reaper auto-inactivated them), `/api/payments/zeffy/config`
returns the OVERDUE Zeffy URL instead of the normal annual-dues URL. Once dues
are approved (auto or admin), the inactive flag(s) are cleared and the normal
URL returns on the next config fetch.
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

import random

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/")

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}

OVERDUE_URL = "https://www.zeffy.com/en-US/ticketing/aop-membership-renewal-overdue-dues"
NORMAL_URL = "https://www.zeffy.com/en-US/ticketing/national-yearly-dues"


def login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin_s():
    return login(ADMIN)


@pytest.fixture(scope="module")
def member_s():
    return login(MEMBER)


@pytest.fixture(scope="module")
def member_id(member_s):
    return member_s.get(f"{BASE_URL}/api/auth/me", timeout=20).json()["id"]


@pytest.fixture(scope="module")
def mongo_db():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip().strip('"').strip("'")
    db_name = os.environ.get("DB_NAME", "clubhaven").strip().strip('"').strip("'")
    return MongoClient(mongo_url)[db_name]


def _make_rct():
    """Generate a valid `RCT-XXXX-XXXX` receipt that classify_zeffy_receipt
    will recognize. Pattern: RCT-3-5 digits dash 3-6 digits."""
    return f"RCT-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"


def test_default_member_gets_normal_dues_url(member_s):
    r = member_s.get(f"{BASE_URL}/api/payments/zeffy/config", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"] == NORMAL_URL
    assert body["is_overdue"] is False


def test_inactive_member_gets_overdue_url(admin_s, member_s, member_id, mongo_db):
    """Admin marks member as inactive via status_override → next zeffy/config
    call from the member returns the overdue URL."""
    original = mongo_db.users.find_one({"id": member_id}, {"status_override": 1, "auto_inactivated_at": 1})
    try:
        # Flip inactive flag.
        r = admin_s.put(
            f"{BASE_URL}/api/members/{member_id}",
            json={"member_status": "inactive"}, timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "inactive"

        # Member's zeffy/config now returns the overdue URL.
        r = member_s.get(f"{BASE_URL}/api/payments/zeffy/config", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["url"] == OVERDUE_URL, f"expected overdue URL, got {body['url']}"
        assert body["is_overdue"] is True
    finally:
        # Restore original status.
        mongo_db.users.update_one(
            {"id": member_id},
            {"$set": {
                "status_override": (original or {}).get("status_override") or None,
                "auto_inactivated_at": (original or {}).get("auto_inactivated_at") or None,
            }},
        )
        # If original status_override was None, unset it.
        if not (original or {}).get("status_override"):
            mongo_db.users.update_one({"id": member_id}, {"$unset": {"status_override": ""}})
        if not (original or {}).get("auto_inactivated_at"):
            mongo_db.users.update_one({"id": member_id}, {"$unset": {"auto_inactivated_at": ""}})


def test_auto_inactivated_member_also_gets_overdue_url(member_s, member_id, mongo_db):
    """The grace-period reaper sets `auto_inactivated_at` without touching
    `status_override`. Verify that path also surfaces the overdue URL."""
    mongo_db.users.update_one({"id": member_id}, {"$set": {"auto_inactivated_at": "2026-01-01T00:00:00+00:00"}})
    try:
        r = member_s.get(f"{BASE_URL}/api/payments/zeffy/config", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["url"] == OVERDUE_URL
        assert body["is_overdue"] is True
    finally:
        mongo_db.users.update_one({"id": member_id}, {"$unset": {"auto_inactivated_at": ""}})


def test_admin_approve_zeffy_clears_inactive_flag(admin_s, member_s, member_id, mongo_db):
    """End-to-end: inactive member submits a Zeffy receipt, admin approves
    it, the inactive flag clears, and zeffy/config returns the normal URL."""
    # Set inactive
    r = admin_s.put(
        f"{BASE_URL}/api/members/{member_id}",
        json={"member_status": "inactive"}, timeout=20,
    )
    assert r.status_code == 200

    try:
        # Member confirms a real-format receipt — should land as PENDING.
        ref = _make_rct()
        r = member_s.post(
            f"{BASE_URL}/api/payments/zeffy/confirm",
            json={"confirmation": ref, "amount": 105.0}, timeout=20,
        )
        assert r.status_code == 200, r.text
        tx_id = r.json()["transaction_id"]
        # Note: trust_zeffy is likely off → status should be pending.

        # Admin approves the dues transaction.
        r = admin_s.put(f"{BASE_URL}/api/transactions/{tx_id}/approve-zeffy", timeout=20)
        assert r.status_code == 200, r.text

        # Verify the user doc had inactive cleared + reactivated_at stamp set.
        user_doc = mongo_db.users.find_one({"id": member_id})
        assert user_doc is not None
        assert user_doc.get("status_override") is None or user_doc.get("status_override") == ""
        assert user_doc.get("reactivated_at"), "reactivated_at audit stamp should be set"

        # Config call now returns the normal URL.
        r = member_s.get(f"{BASE_URL}/api/payments/zeffy/config", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["url"] == NORMAL_URL
        assert body["is_overdue"] is False
    finally:
        # Cleanup: delete the test transaction + reset member.
        # (admin approve already cleared the inactive flag.)
        mongo_db.transactions.delete_many({"user_id": member_id, "zeffy_confirmation": {"$regex": "^RCT-"}})
        mongo_db.users.update_one(
            {"id": member_id},
            {"$unset": {
                "reactivated_at": "",
                "reactivated_by": "",
                "reactivated_by_name": "",
                "auto_inactivated_at": "",
            }},
        )


def test_auto_approve_path_clears_inactive_flag(admin_s, member_s, member_id, mongo_db):
    """If trust_zeffy=True the confirm endpoint auto-approves AND clears the
    inactive flag in one step."""
    # Set trust_zeffy + inactive in one DB write.
    mongo_db.users.update_one(
        {"id": member_id},
        {"$set": {"trust_zeffy": True, "status_override": "inactive"}},
    )
    try:
        ref = _make_rct()
        r = member_s.post(
            f"{BASE_URL}/api/payments/zeffy/confirm",
            json={"confirmation": ref, "amount": 105.0}, timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "completed"
        assert body["auto_approved"] is True

        # Inactive flag cleared.
        user_doc = mongo_db.users.find_one({"id": member_id})
        assert user_doc.get("status_override") is None or user_doc.get("status_override") == ""
        assert user_doc.get("reactivated_at")

        # Normal URL returned.
        r = member_s.get(f"{BASE_URL}/api/payments/zeffy/config", timeout=20)
        assert r.json()["url"] == NORMAL_URL
    finally:
        mongo_db.transactions.delete_many({"user_id": member_id, "zeffy_confirmation": {"$regex": "^RCT-"}})
        mongo_db.users.update_one(
            {"id": member_id},
            {"$unset": {
                "trust_zeffy": "",
                "reactivated_at": "",
                "reactivated_by": "",
                "auto_inactivated_at": "",
            }},
        )
