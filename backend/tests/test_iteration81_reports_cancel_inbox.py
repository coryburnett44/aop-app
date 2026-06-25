"""Iter81 — Reports RSVPs filter parity + cancellation emails + admin inbox.

Covers four areas the user asked about:
  A. /api/reports/rsvps now accepts year/quarter/month/ticket_type filters and
     returns chapter_name on every row.
  B. /api/reports/rsvps/summary returns group-by member|chapter|period buckets
     mirroring /api/reports/hours/summary.
  C. /api/events/{id} PUT with cancelled=true triggers the cancellation-email
     fan-out (no email actually leaves the pod in tests since RESEND_API_KEY
     isn't set — we just assert the request returns 200 and writes the right
     fields). The behaviour is fire-and-forget; the API response can't be
     blocked by Resend so we test the side effects on the DB rows directly.
  D. /api/admin/stats now exposes inbox.pending_event_tickets[].
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "jordan.reed@clubhaven.app", "password": "Demo123!"}


def _mongo():
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


@pytest.fixture(scope="module")
def member_s():
    return _login(MEMBER)


def _iso_future(days=30, hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


# ============================================================
# A & B — RSVP report filters + summary
# ============================================================

@pytest.fixture
def two_events_with_rsvps(admin_s, member_s):
    """Create two events in different months, RSVP same member to both with
    different ticket types. Yield (e1, e2, member_id). Clean up after."""
    members = admin_s.get(f"{API}/members", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    target = next((m for m in members if m.get("email") == MEMBER["email"]), None)
    assert target

    e1 = admin_s.post(f"{API}/events", json={
        "title": f"Iter81 EvA {uuid.uuid4().hex[:6]}",
        "description": "iter81 filter test",
        "location": "DC",
        "start_at": _iso_future(20),
        "end_at": _iso_future(20, 3),
        "category": "general",
        "capacity": 50,
        "allows_ticket_types": True,
        "enabled_ticket_types": ["vip", "general"],
    }, timeout=15).json()
    e2 = admin_s.post(f"{API}/events", json={
        "title": f"Iter81 EvB {uuid.uuid4().hex[:6]}",
        "description": "iter81 filter test",
        "location": "DC",
        "start_at": _iso_future(75),
        "end_at": _iso_future(75, 3),
        "category": "general",
        "capacity": 50,
        "allows_ticket_types": True,
        "enabled_ticket_types": ["vip", "general"],
    }, timeout=15).json()
    # Admin-RSVP the demo member to both with different ticket types.
    admin_s.post(f"{API}/events/{e1['id']}/admin-rsvp", json={"user_id": target["id"], "ticket_type": "vip", "send_email": False}, timeout=15)
    admin_s.post(f"{API}/events/{e2['id']}/admin-rsvp", json={"user_id": target["id"], "ticket_type": "general", "send_email": False}, timeout=15)
    yield e1, e2, target
    admin_s.delete(f"{API}/events/{e1['id']}", timeout=10)
    admin_s.delete(f"{API}/events/{e2['id']}", timeout=10)


def test_rsvps_report_ticket_type_filter(admin_s, two_events_with_rsvps):
    e1, e2, _ = two_events_with_rsvps
    # ticket_type=vip should only return the e1 RSVP.
    r = admin_s.get(f"{API}/reports/rsvps", params={"ticket_type": "vip"}, timeout=15)
    assert r.status_code == 200, r.text
    rows = [row for row in r.json() if row["event_id"] in (e1["id"], e2["id"])]
    assert len(rows) == 1
    assert rows[0]["event_id"] == e1["id"]
    assert rows[0]["ticket_type"] == "vip"


def test_rsvps_report_event_filter(admin_s, two_events_with_rsvps):
    e1, _, _ = two_events_with_rsvps
    r = admin_s.get(f"{API}/reports/rsvps", params={"event_id": e1["id"]}, timeout=15)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert all(row["event_id"] == e1["id"] for row in rows)
    # chapter_name is now part of every row.
    for row in rows:
        assert "chapter_name" in row


def test_rsvps_summary_by_member(admin_s, two_events_with_rsvps):
    _, _, target = two_events_with_rsvps
    r = admin_s.get(f"{API}/reports/rsvps/summary", params={"group_by": "member"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "totals" in body and "rows" in body
    mine = next((row for row in body["rows"] if row.get("user_id") == target["id"]), None)
    assert mine, "demo member missing from member summary"
    assert mine["rsvp_count"] >= 2  # at least the two we just created


def test_rsvps_summary_by_chapter(admin_s, two_events_with_rsvps):
    r = admin_s.get(f"{API}/reports/rsvps/summary", params={"group_by": "chapter"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("rows"), list)
    if body["rows"]:
        first = body["rows"][0]
        assert "chapter_name" in first and "rsvp_count" in first


def test_rsvps_summary_by_period(admin_s, two_events_with_rsvps):
    r = admin_s.get(f"{API}/reports/rsvps/summary", params={"group_by": "period"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("rows"), list)
    if body["rows"]:
        first = body["rows"][0]
        assert "period_key" in first and "period_label" in first


# ============================================================
# C — Cancellation triggers email fan-out side-effects
# ============================================================

def test_cancel_event_marks_cascade_and_keeps_rsvp_intact(admin_s, member_s):
    """Smoke-check the cancel path runs without 500s when there are RSVPs.
    Tests for the actual email body live behind RESEND_API_KEY; here we just
    verify the API contract and that the rsvp row survives cancellation."""
    members = admin_s.get(f"{API}/members", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    target = next((m for m in members if m.get("email") == MEMBER["email"]), None)
    assert target
    ev = admin_s.post(f"{API}/events", json={
        "title": f"Iter81 CancelTest {uuid.uuid4().hex[:6]}",
        "description": "cancel-email smoke test",
        "location": "DC",
        "start_at": _iso_future(50),
        "end_at": _iso_future(50, 3),
        "category": "general",
        "capacity": 50,
    }, timeout=15).json()
    admin_s.post(f"{API}/events/{ev['id']}/admin-rsvp", json={"user_id": target["id"], "send_email": False}, timeout=15)
    r = admin_s.put(f"{API}/events/{ev['id']}", json={"cancelled": True, "cancellation_note": "Weather"}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["cancelled"] is True
    # RSVP row must still be present so reports continue to include it.
    rsvps = admin_s.get(f"{API}/events/{ev['id']}/rsvps", timeout=15).json()
    assert any(row["user_id"] == target["id"] for row in rsvps), "RSVP rows must persist after cancellation"
    admin_s.delete(f"{API}/events/{ev['id']}", timeout=10)


# ============================================================
# D — admin/stats inbox.pending_event_tickets
# ============================================================

def test_admin_inbox_pending_event_tickets_field_present(admin_s):
    r = admin_s.get(f"{API}/admin/stats", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "inbox" in body
    inbox = body["inbox"]
    assert "pending_event_tickets" in inbox, "inbox missing pending_event_tickets field"
    assert isinstance(inbox["pending_event_tickets"], list)
    assert "total" in inbox


def test_admin_inbox_lists_pending_event_ticket_when_one_exists(admin_s):
    """Insert a fake pending event_ticket transaction directly and confirm the
    inbox surfaces it."""
    db = _mongo()
    tx_id = str(uuid.uuid4())
    db.transactions.insert_one({
        "id": tx_id,
        "purpose": "event_ticket",
        "status": "pending",
        "user_id": "iter81-test-uid",
        "user_name": "Iter81 Receipt Submitter",
        "event_id": "iter81-test-evt",
        "event_title": "Iter81 Mock Paid Event",
        "amount": 25.0,
        "zeffy_confirmation": "Z-IT81-XYZ",
        "created_at": "2026-02-01T12:00:00+00:00",
    })
    try:
        r = admin_s.get(f"{API}/admin/stats", timeout=15)
        assert r.status_code == 200, r.text
        tickets = r.json()["inbox"]["pending_event_tickets"]
        match = next((t for t in tickets if t["id"] == tx_id), None)
        assert match, "newly-inserted pending ticket missing from inbox"
        assert match["zeffy_confirmation"] == "Z-IT81-XYZ"
        assert match["user_name"] == "Iter81 Receipt Submitter"
        assert match["amount"] == 25.0
    finally:
        db.transactions.delete_one({"id": tx_id})
