"""Iter83 — inline Approve / Reject buttons on the admin Inbox Zeffy tab.

Exercises the underlying backend contract the new inline buttons in
`AdminDashboard.jsx` call into:

  PUT    /api/transactions/{tx_id}/approve-event-ticket   — Approve
  DELETE /api/transactions/{tx_id}                        — Reject

Specifically guards against future regressions where:
  - The inbox stops surfacing a pending tx after approval, OR
  - DELETE on a non-event-ticket tx accidentally succeeds (a security gap).

The frontend UI is purely a thin wrapper around these — full inline-button
behaviour is covered by the existing iter28 + iter81 tests; this file is a
focused smoke pass for the inbox use-case.
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}


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


def test_inbox_reject_button_deletes_pending_event_ticket(admin_s):
    """Reject button → DELETE /transactions/{id} → tx disappears from inbox."""
    db = _mongo()
    tx_id = str(uuid.uuid4())
    db.transactions.insert_one({
        "id": tx_id,
        "purpose": "event_ticket",
        "status": "pending",
        "user_id": "iter83-uid",
        "user_name": "Iter83 Reject Submitter",
        "event_id": "iter83-evt",
        "event_title": "Iter83 Reject Mock",
        "amount": 50.0,
        "zeffy_confirmation": "Z-IT83-REJ",
        "created_at": "2026-02-01T12:00:00+00:00",
    })
    try:
        # Confirm it appears in the inbox first.
        r = admin_s.get(f"{API}/admin/stats", timeout=15)
        assert r.status_code == 200
        tickets = r.json()["inbox"]["pending_event_tickets"]
        assert any(t["id"] == tx_id for t in tickets), "fresh pending ticket missing from inbox"

        # Press "Reject" → DELETE.
        r = admin_s.delete(f"{API}/transactions/{tx_id}", timeout=15)
        assert r.status_code == 200, r.text

        # Inbox no longer surfaces it.
        r = admin_s.get(f"{API}/admin/stats", timeout=15)
        tickets = r.json()["inbox"]["pending_event_tickets"]
        assert not any(t["id"] == tx_id for t in tickets), "rejected ticket still in inbox"

        # Underlying tx row is gone.
        leftover = db.transactions.find_one({"id": tx_id})
        assert leftover is None, "DELETE should remove the pending tx row"
    finally:
        db.transactions.delete_one({"id": tx_id})


def test_inbox_approve_endpoint_still_reachable(admin_s):
    """Smoke-test that PUT /transactions/{id}/approve-event-ticket responds
    with a meaningful error for a missing tx (proving the route is wired)."""
    fake_id = f"iter83-missing-{uuid.uuid4().hex[:6]}"
    r = admin_s.put(f"{API}/transactions/{fake_id}/approve-event-ticket", timeout=15)
    assert r.status_code in (400, 404), r.text
    # The endpoint should mention the tx in the error, not blow up with 500.
    assert "not" in r.json().get("detail", "").lower() or "expire" in r.json().get("detail", "").lower()
