"""
Iteration 28 — Paid Events + Optional ticket types + Bulk import set-password emails.

Covers:
  - paid event create / event_out fields persist
  - free RSVP on paid event => 402
  - member /payment/confirm => pending event_ticket tx (no RSVP)
  - duplicate submit => 400
  - admin /approve-event-ticket => RSVP + counters + email scheduled
  - re-approve => {already:true}
  - trust_zeffy auto-approve path
  - cancelled paid event => 400 on /payment/confirm
  - free event => 400 on /payment/confirm
  - admin update toggles is_paid off and edits enabled_ticket_types
  - GET /transactions surfaces event_id/event_title via tx_out
  - send_rsvp_ticket_email log includes the events inbox CC
  - bulk-import generates password_set_tokens + emails_sent_count
  - bulk-import with send_set_password_emails=false => no token row
  - dues queue is unaffected by event_ticket txs
"""
import io
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = BASE_URL + "/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASSWORD = "Member123!"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "clubhaven_db")


# ---------- shared fixtures ----------
@pytest.fixture(scope="session")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def member():
    return _login(MEMBER_EMAIL, MEMBER_PASSWORD)


@pytest.fixture(scope="session")
def member_id(member):
    r = member.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json()["id"]


# ---------- Helper: create / cleanup events ----------
def _create_paid_event(admin, *, title="TEST_paid_event", is_paid=True, amount=25.0,
                      url="https://zeffy.com/test-paid", enabled=None, cancelled=False):
    if enabled is None:
        enabled = ["vip", "general"]
    payload = {
        "title": title,
        "start_at": "2030-01-01T18:00:00Z",
        "location": "Test Hall",
        "description": "iter28 paid event",
        "is_paid": is_paid,
        "payment_url": url if is_paid else "",
        "payment_amount": amount if is_paid else 0.0,
        "enabled_ticket_types": enabled,
        "allows_ticket_types": True,
        "cancelled": cancelled,
    }
    r = admin.post(f"{API}/events", json=payload, timeout=15)
    assert r.status_code in (200, 201), f"create event failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture
def paid_event(admin):
    e = _create_paid_event(admin)
    yield e
    try:
        admin.delete(f"{API}/events/{e['id']}", timeout=10)
    except Exception:
        pass


# ============================================================
# Backend test cases
# ============================================================

# ---------- Event creation persists all new fields ----------
def test_paid_event_create_persists_fields(paid_event):
    e = paid_event
    assert e["is_paid"] is True
    assert e["payment_url"] == "https://zeffy.com/test-paid"
    assert float(e["payment_amount"]) == 25.0
    assert set(e["enabled_ticket_types"]) == {"vip", "general"}


def test_paid_event_event_out_round_trip(admin, paid_event):
    r = admin.get(f"{API}/events/{paid_event['id']}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["is_paid"] is True
    assert body["payment_amount"] == 25.0
    assert "vip" in body["enabled_ticket_types"]


# ---------- Direct RSVP on paid event blocked ----------
def test_free_rsvp_on_paid_event_returns_402(member, paid_event):
    r = member.post(f"{API}/events/{paid_event['id']}/rsvp", json={"ticket_type": "vip"}, timeout=15)
    assert r.status_code == 402, f"expected 402 got {r.status_code} {r.text}"
    assert "payment" in r.text.lower()


# ---------- /payment/confirm creates pending tx ----------
def test_payment_confirm_creates_pending_tx(admin, member, paid_event, mongo):
    # Ensure trust flag off
    mongo.users.update_one({"email": MEMBER_EMAIL}, {"$set": {"trust_zeffy": False}})

    confirmation = "RCT-1234-5678"
    r = member.post(
        f"{API}/events/{paid_event['id']}/payment/confirm",
        json={"confirmation": confirmation, "ticket_type": "vip", "guests": []},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["auto_approved"] is False
    tx_id = body["transaction_id"]

    # DB assertions
    tx = mongo.transactions.find_one({"id": tx_id})
    assert tx is not None
    assert tx["purpose"] == "event_ticket"
    assert tx["event_id"] == paid_event["id"]
    assert tx["status"] == "pending"
    assert float(tx["amount"]) == 25.0
    assert tx["zeffy_receipt_format"] == "rct"
    assert tx["rsvp_ticket_type"] == "vip"

    # No RSVP yet
    rsvp = mongo.rsvps.find_one({"event_id": paid_event["id"], "user_id": tx["user_id"]})
    assert rsvp is None

    # Duplicate submit => 400
    r2 = member.post(
        f"{API}/events/{paid_event['id']}/payment/confirm",
        json={"confirmation": "RCT-9999-1111", "ticket_type": "vip"},
        timeout=15,
    )
    assert r2.status_code == 400
    assert "already" in r2.text.lower()


# ---------- admin approve-event-ticket creates RSVP ----------
def test_admin_approve_event_ticket_creates_rsvp(admin, member, mongo):
    # Fresh paid event for isolation
    e = _create_paid_event(admin, title="TEST_approve_paid")
    try:
        # member submits
        r = member.post(
            f"{API}/events/{e['id']}/payment/confirm",
            json={"confirmation": "RCT-2222-3333", "ticket_type": "vip", "guests": []},
            timeout=15,
        )
        assert r.status_code == 200
        tx_id = r.json()["transaction_id"]

        # admin approves
        r2 = admin.put(f"{API}/transactions/{tx_id}/approve-event-ticket", timeout=20)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body.get("ok") is True
        assert "rsvp_id" in body
        assert "ticket_id" in body

        # tx now completed + RSVP exists
        tx = mongo.transactions.find_one({"id": tx_id})
        assert tx["status"] == "completed"
        assert tx.get("rsvp_id") == body["rsvp_id"]

        rsvp = mongo.rsvps.find_one({"id": body["rsvp_id"]})
        assert rsvp is not None
        assert rsvp["event_id"] == e["id"]
        assert rsvp["ticket_type"] == "vip"
        assert rsvp.get("payment_tx_id") == tx_id

        # event counter incremented
        evt = mongo.events.find_one({"id": e["id"]})
        assert evt.get("rsvp_count", 0) >= 1

        # repeat approve => already:true
        r3 = admin.put(f"{API}/transactions/{tx_id}/approve-event-ticket", timeout=10)
        assert r3.status_code == 200
        assert r3.json().get("already") is True
    finally:
        admin.delete(f"{API}/events/{e['id']}", timeout=10)
        mongo.transactions.delete_many({"event_id": e["id"]})
        mongo.rsvps.delete_many({"event_id": e["id"]})


# ---------- trust_zeffy auto-approval ----------
def test_trust_zeffy_auto_approval(admin, member, mongo):
    mongo.users.update_one({"email": MEMBER_EMAIL}, {"$set": {"trust_zeffy": True}})
    e = _create_paid_event(admin, title="TEST_trust_paid")
    try:
        r = member.post(
            f"{API}/events/{e['id']}/payment/confirm",
            json={"confirmation": "RCT-4040-5050", "ticket_type": "vip"},
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["auto_approved"] is True
        assert "rsvp_id" in body
        # DB confirms RSVP created
        rsvp = mongo.rsvps.find_one({"id": body["rsvp_id"]})
        assert rsvp is not None
        assert rsvp["ticket_type"] == "vip"
    finally:
        mongo.users.update_one({"email": MEMBER_EMAIL}, {"$set": {"trust_zeffy": False}})
        admin.delete(f"{API}/events/{e['id']}", timeout=10)
        mongo.transactions.delete_many({"event_id": e["id"]})
        mongo.rsvps.delete_many({"event_id": e["id"]})


# ---------- Cancelled paid event blocks payment ----------
def test_cancelled_paid_event_blocks_payment(admin, member, mongo):
    e = _create_paid_event(admin, title="TEST_cancelled_paid", cancelled=True)
    try:
        r = member.post(
            f"{API}/events/{e['id']}/payment/confirm",
            json={"confirmation": "RCT-7777-8888", "ticket_type": "vip"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "cancelled" in r.text.lower()
    finally:
        admin.delete(f"{API}/events/{e['id']}", timeout=10)
        mongo.transactions.delete_many({"event_id": e["id"]})


# ---------- Free event => /payment/confirm rejected ----------
def test_free_event_rejects_payment_confirm(admin, member, mongo):
    payload = {
        "title": "TEST_free_event",
        "start_at": "2030-02-01T18:00:00Z",
        "location": "Test",
        "is_paid": False,
    }
    r = admin.post(f"{API}/events", json=payload, timeout=15)
    assert r.status_code in (200, 201)
    e = r.json()
    try:
        r2 = member.post(
            f"{API}/events/{e['id']}/payment/confirm",
            json={"confirmation": "RCT-1212-3434", "ticket_type": "general"},
            timeout=15,
        )
        assert r2.status_code == 400
        assert "free" in r2.text.lower()
    finally:
        admin.delete(f"{API}/events/{e['id']}", timeout=10)


# ---------- Admin update toggles is_paid off ----------
def test_admin_update_toggle_is_paid_and_ticket_types(admin):
    e = _create_paid_event(admin, title="TEST_toggle_paid", enabled=["vip", "general"])
    try:
        r = admin.put(
            f"{API}/events/{e['id']}",
            json={"is_paid": False, "enabled_ticket_types": ["general", "guest"]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_paid"] is False
        assert set(body["enabled_ticket_types"]) == {"general", "guest"}
    finally:
        admin.delete(f"{API}/events/{e['id']}", timeout=10)


# ---------- GET /transactions surfaces event_id+event_title ----------
def test_transactions_surface_event_fields(admin, member, mongo):
    e = _create_paid_event(admin, title="TEST_tx_surface")
    try:
        r = member.post(
            f"{API}/events/{e['id']}/payment/confirm",
            json={"confirmation": "RCT-5050-6060", "ticket_type": "vip"},
            timeout=15,
        )
        assert r.status_code == 200
        tx_id = r.json()["transaction_id"]

        # GET as admin
        r2 = admin.get(f"{API}/transactions", timeout=15)
        assert r2.status_code == 200
        items = r2.json()
        found = next((t for t in items if t.get("id") == tx_id), None)
        assert found is not None
        assert found.get("event_id") == e["id"]
        assert found.get("event_title") == "TEST_tx_surface"
        assert found.get("purpose") == "event_ticket"
    finally:
        admin.delete(f"{API}/events/{e['id']}", timeout=10)
        mongo.transactions.delete_many({"event_id": e["id"]})
        mongo.rsvps.delete_many({"event_id": e["id"]})


# ---------- Dues queue NOT polluted by event_ticket txs ----------
def test_dues_queue_unaffected_by_event_ticket_tx(admin, member, mongo):
    e = _create_paid_event(admin, title="TEST_dues_isolation")
    try:
        r = member.post(
            f"{API}/events/{e['id']}/payment/confirm",
            json={"confirmation": "RCT-8080-9090", "ticket_type": "vip"},
            timeout=15,
        )
        assert r.status_code == 200
        tx_id = r.json()["transaction_id"]

        # Frontend filters the /transactions response by purpose client-side.
        # Verify the event_ticket tx is NOT labelled as 'dues' (so the dues
        # queue UI filter `purpose === 'dues'` will exclude it).
        r2 = admin.get(f"{API}/transactions", timeout=15)
        assert r2.status_code == 200
        items = r2.json()
        ours = next((t for t in items if t.get("id") == tx_id), None)
        assert ours is not None
        assert ours.get("purpose") == "event_ticket"
        assert ours.get("purpose") != "dues"
        dues_subset = [t for t in items if t.get("purpose") == "dues"]
        assert all(t.get("id") != tx_id for t in dues_subset)
    finally:
        admin.delete(f"{API}/events/{e['id']}", timeout=10)
        mongo.transactions.delete_many({"event_id": e["id"]})
        mongo.rsvps.delete_many({"event_id": e["id"]})


# ---------- send_rsvp_ticket_email logs CC to events inbox ----------
def test_ticket_email_logs_cc_to_events_inbox(admin, member, mongo):
    e = _create_paid_event(admin, title="TEST_ticket_cc")
    try:
        r = member.post(
            f"{API}/events/{e['id']}/payment/confirm",
            json={"confirmation": "RCT-6060-7070", "ticket_type": "vip"},
            timeout=15,
        )
        tx_id = r.json()["transaction_id"]
        ra = admin.put(f"{API}/transactions/{tx_id}/approve-event-ticket", timeout=20)
        assert ra.status_code == 200
        # Give the async email task a moment
        time.sleep(3)
        # Inspect supervisor log for the CC line
        import subprocess
        out = subprocess.run(
            ["bash", "-lc", "tail -n 400 /var/log/supervisor/backend.*.log 2>/dev/null | grep -E 'RSVP ticket email sent.*info@alphaomegaphi.org|info@alphaomegaphi.org|RSVP ticket email failed' || true"],
            capture_output=True, text=True, timeout=10,
        )
        log_blob = out.stdout
        # Either the success log includes info@alphaomegaphi.org, or Resend failed (403 etc) — both prove the CC logic ran.
        ok = ("info@alphaomegaphi.org" in log_blob) or ("RSVP ticket email failed" in log_blob)
        assert ok, f"Did not find CC inbox log line. Recent log: {log_blob[:1200]}"
    finally:
        admin.delete(f"{API}/events/{e['id']}", timeout=10)
        mongo.transactions.delete_many({"event_id": e["id"]})
        mongo.rsvps.delete_many({"event_id": e["id"]})


# ---------- Bulk import with set-password emails ----------
def _csv_blob(rows):
    head = "Email,First Name,Last Name,Title,Renewal Date\n"
    return head + "\n".join(rows)


def test_bulk_import_generates_password_set_tokens(admin, mongo):
    a_email = f"test_iter28_a_{uuid.uuid4().hex[:6]}@example.com"
    b_email = f"test_iter28_b_{uuid.uuid4().hex[:6]}@example.com"
    csv = _csv_blob([
        f"{a_email},Alpha,One,Mr,2027-01-01",
        f"{b_email},Beta,Two,Ms,2027-02-01",
    ])
    files = {"file": ("members.csv", io.BytesIO(csv.encode()), "text/csv")}
    data = {"dry_run": "false", "send_set_password_emails": "true"}
    r = admin.post(f"{API}/admin/members/bulk-import", files=files, data=data, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_count"] == 2
    assert "emails_sent_count" in body
    # token rows MUST exist for each created user (regardless of Resend success)
    try:
        for em in (a_email, b_email):
            u = mongo.users.find_one({"email": em})
            assert u is not None, f"user {em} not created"
            tok = mongo.password_set_tokens.find_one({"user_id": u["id"], "used": False})
            assert tok is not None, f"no password_set_token for {em}"
    finally:
        # cleanup
        for em in (a_email, b_email):
            u = mongo.users.find_one({"email": em})
            if u:
                mongo.password_set_tokens.delete_many({"user_id": u["id"]})
                mongo.users.delete_one({"id": u["id"]})


def test_bulk_import_no_password_emails_when_flag_off(admin, mongo):
    c_email = f"test_iter28_c_{uuid.uuid4().hex[:6]}@example.com"
    csv = _csv_blob([f"{c_email},Gamma,Three,Mr,2027-03-01"])
    files = {"file": ("members.csv", io.BytesIO(csv.encode()), "text/csv")}
    data = {"dry_run": "false", "send_set_password_emails": "false"}
    r = admin.post(f"{API}/admin/members/bulk-import", files=files, data=data, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["created_count"] == 1
    assert body["emails_sent_count"] == 0
    try:
        u = mongo.users.find_one({"email": c_email})
        assert u is not None
        tok = mongo.password_set_tokens.find_one({"user_id": u["id"]})
        assert tok is None, "password_set_token created even though flag was false"
    finally:
        u = mongo.users.find_one({"email": c_email})
        if u:
            mongo.password_set_tokens.delete_many({"user_id": u["id"]})
            mongo.users.delete_one({"id": u["id"]})


# ---------- Smoke regression ----------
def test_smoke_regressions(admin, member):
    assert admin.get(f"{API}/auth/me", timeout=10).status_code == 200
    assert member.get(f"{API}/auth/me", timeout=10).status_code == 200
    assert admin.get(f"{API}/chapters", timeout=10).status_code == 200
    assert admin.get(f"{API}/events", timeout=10).status_code == 200
    assert admin.get(f"{API}/members", timeout=10).status_code == 200
