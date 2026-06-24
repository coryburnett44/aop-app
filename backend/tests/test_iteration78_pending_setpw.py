"""Iter78 — pending_set_password badge stays permanent until member resets.

Covers four guarantees:
  1. Logging in does NOT auto-clear pending_set_password (the previous "glitch").
  2. /auth/reset-password DOES clear pending_set_password.
  3. /auth/change-password DOES clear pending_set_password.
  4. /auth/set-password (already correct) clears pending_set_password.

The boot-time `reconcile_pending_set_password()` migration is exercised
indirectly by the test setup: we manually flip the flag back to false on the
seeded admin and verify a successful login doesn't touch it.
"""
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}


def _mongo():
    """Direct DB handle for setup/teardown (the boot migration loads env, so we
    do the same)."""
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_s():
    return _login(ADMIN)


@pytest.fixture
def pending_user(admin_s):
    """Create a temp member flagged pending_set_password=True and bcrypt-hash
    their password directly in Mongo so we can log them in. Cleans up at end."""
    db = _mongo()
    email = f"iter78-{uuid.uuid4().hex[:8]}@aop.test"
    # Use the same passlib config the app uses (bcrypt)
    from passlib.context import CryptContext
    pw_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    uid = str(uuid.uuid4())
    db.users.insert_one({
        "id": uid,
        "email": email,
        "name": "Iter78 Test User",
        "password_hash": pw_ctx.hash("TempPass!23"),
        "role": "member",
        "pending_set_password": True,
        "is_active": True,
        "token_version": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    yield {"id": uid, "email": email, "password": "TempPass!23"}
    db.users.delete_one({"id": uid})


def test_login_does_not_clear_pending_set_password(pending_user):
    """Regression: log in with admin-set temp password, badge must persist."""
    db = _mongo()
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": pending_user["email"], "password": pending_user["password"]}, timeout=20)
    assert r.status_code == 200, r.text
    # Flag must still be true
    fresh = db.users.find_one({"id": pending_user["id"]}, {"_id": 0, "pending_set_password": 1})
    assert fresh.get("pending_set_password") is True, "login should NOT clear pending_set_password"
    # And /auth/me should also report true
    me = s.get(f"{API}/auth/me", timeout=10)
    assert me.status_code == 200
    assert me.json().get("pending_set_password") is True


def test_reset_password_clears_pending_set_password(pending_user):
    """After forgot/reset flow, flag must clear."""
    db = _mongo()
    import secrets
    token = secrets.token_urlsafe(32)
    db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": pending_user["id"],
        "expires_at": "2099-01-01T00:00:00+00:00",
        "used": False,
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    r = requests.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "NewSecret!23"}, timeout=15)
    assert r.status_code == 200, r.text
    fresh = db.users.find_one({"id": pending_user["id"]}, {"_id": 0, "pending_set_password": 1})
    assert fresh.get("pending_set_password") is False, "reset-password should clear pending_set_password"


def test_change_password_clears_pending_set_password(pending_user):
    """After logged-in /change-password, flag must clear."""
    db = _mongo()
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": pending_user["email"], "password": pending_user["password"]}, timeout=20)
    assert r.status_code == 200
    # Confirm still pending after login (already covered above, defensive check)
    me = s.get(f"{API}/auth/me", timeout=10).json()
    assert me.get("pending_set_password") is True
    # Now change password
    r = s.post(f"{API}/auth/change-password", json={"current_password": pending_user["password"], "new_password": "Changed!23"}, timeout=15)
    assert r.status_code == 200, r.text
    fresh = db.users.find_one({"id": pending_user["id"]}, {"_id": 0, "pending_set_password": 1})
    assert fresh.get("pending_set_password") is False, "change-password should clear pending_set_password"


def test_set_password_clears_pending_set_password(pending_user):
    """The original /set-password token flow must keep clearing the flag."""
    db = _mongo()
    import secrets
    token = secrets.token_urlsafe(32)
    db.password_set_tokens.insert_one({
        "token": token,
        "user_id": pending_user["id"],
        "expires_at": "2099-01-01T00:00:00+00:00",
        "used": False,
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    r = requests.post(f"{API}/auth/set-password", json={"token": token, "new_password": "FromWelcome!23"}, timeout=15)
    assert r.status_code == 200, r.text
    fresh = db.users.find_one({"id": pending_user["id"]}, {"_id": 0, "pending_set_password": 1})
    assert fresh.get("pending_set_password") is False, "set-password should clear pending_set_password"


def test_reconcile_migration_reflags_issued_but_unused(pending_user):
    """Spawn a token for a user, then manually flip their flag to false, then
    invoke the migration via a backend restart-equivalent (we just call the
    helper directly). Flag must come back to true."""
    db = _mongo()
    import secrets
    token = secrets.token_urlsafe(32)
    db.password_set_tokens.insert_one({
        "token": token,
        "user_id": pending_user["id"],
        "expires_at": "2099-01-01T00:00:00+00:00",
        "used": False,
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    # Simulate the historical bug: flag was cleared even though token was never consumed.
    db.users.update_one({"id": pending_user["id"]}, {"$set": {"pending_set_password": False}})

    # Trigger reconciliation by restarting the backend (simplest reliable way).
    import subprocess
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True)
    time.sleep(4)

    fresh = db.users.find_one({"id": pending_user["id"]}, {"_id": 0, "pending_set_password": 1})
    assert fresh.get("pending_set_password") is True, "migration must re-flag users with issued-but-unused tokens"
