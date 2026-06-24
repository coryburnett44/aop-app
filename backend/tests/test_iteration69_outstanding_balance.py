"""Iteration 69 — Outstanding-balance lifecycle tests.

Smoke-covers the full happy path (admin sets URL → adds 2 lines → member submits
receipt → admin approves → admin marks the other line paid → total = 0) plus
the negative paths: bad URL, edit/delete paid line, line locking via pending
receipt, double-submit guard, etc.
"""
import os
import sys
import asyncio
import uuid

import pytest
import httpx

# We hit the live preview backend (same approach as other iter*_*.py tests),
# but if REACT_APP_BACKEND_URL isn't in the env we skip the suite cleanly.
API_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not API_BASE:
    pytest.skip("REACT_APP_BACKEND_URL not set — skipping live API tests", allow_module_level=True)

API = f"{API_BASE.rstrip('/')}/api"
ADMIN = ("admin@clubhaven.app", "Admin123!")
MAYA = ("maya.patel@clubhaven.app", "Demo123!")


def _login(client, email, password):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def admin_client():
    c = httpx.Client(timeout=15.0, follow_redirects=True)
    _login(c, *ADMIN)
    yield c
    c.close()


@pytest.fixture
def maya_client():
    c = httpx.Client(timeout=15.0, follow_redirects=True)
    _login(c, *MAYA)
    yield c
    c.close()


@pytest.fixture
def maya_id(admin_client):
    r = admin_client.get(f"{API}/members")
    assert r.status_code == 200
    rows = r.json()
    maya = next(m for m in rows if m["email"] == MAYA[0])
    return maya["id"]


@pytest.fixture(autouse=True)
def cleanup(admin_client, maya_id):
    """Reset balance state before each test."""
    # Read current balance (best effort), delete every line, clear URL.
    try:
        bal = admin_client.get(f"{API}/admin/members/{maya_id}/balance").json()
        for ln in bal.get("lines", []):
            if not ln.get("paid_at"):
                admin_client.delete(f"{API}/admin/members/{maya_id}/balance/lines/{ln['id']}")
        admin_client.put(f"{API}/admin/members/{maya_id}/balance/zeffy-url", json={"url": ""})
    except Exception:
        pass
    yield


def test_admin_can_set_zeffy_url(admin_client, maya_id):
    r = admin_client.put(
        f"{API}/admin/members/{maya_id}/balance/zeffy-url",
        json={"url": "https://www.zeffy.com/en-US/ticketing/test-link"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["zeffy_url"] == "https://www.zeffy.com/en-US/ticketing/test-link"


def test_zeffy_url_rejects_non_https(admin_client, maya_id):
    r = admin_client.put(
        f"{API}/admin/members/{maya_id}/balance/zeffy-url",
        json={"url": "http://insecure.example.com"},
    )
    assert r.status_code == 400
    assert "https" in r.json()["detail"].lower()


def test_admin_add_edit_delete_line(admin_client, maya_id):
    r = admin_client.post(
        f"{API}/admin/members/{maya_id}/balance/lines",
        json={"label": "Test Anniversary", "amount": 100.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 100.0
    line = body["lines"][-1]
    # Edit
    r2 = admin_client.put(
        f"{API}/admin/members/{maya_id}/balance/lines/{line['id']}",
        json={"amount": 125.50},
    )
    assert r2.status_code == 200
    edited = next(ln for ln in r2.json()["lines"] if ln["id"] == line["id"])
    assert edited["amount"] == 125.5
    # Delete
    r3 = admin_client.delete(f"{API}/admin/members/{maya_id}/balance/lines/{line['id']}")
    assert r3.status_code == 200
    assert r3.json()["total"] == 0


def test_admin_mark_paid_creates_transaction(admin_client, maya_id):
    r = admin_client.post(
        f"{API}/admin/members/{maya_id}/balance/lines",
        json={"label": "Mark-paid test", "amount": 75.0},
    )
    line = r.json()["lines"][-1]
    r2 = admin_client.post(f"{API}/admin/members/{maya_id}/balance/lines/{line['id']}/mark-paid")
    assert r2.status_code == 200
    bal = r2.json()
    paid = next(ln for ln in bal["lines"] if ln["id"] == line["id"])
    assert paid["paid_at"] is not None
    assert paid["paid_via"] == "admin_mark_paid"
    assert bal["total"] == 0
    # The associated transaction must exist with status=completed
    txs = admin_client.get(f"{API}/transactions?user_id={maya_id}").json()
    tx = next((t for t in txs if t.get("id") == paid["paid_tx_id"]), None)
    assert tx is not None
    assert tx["status"] == "completed"
    assert tx["purpose"] == "balance"
    assert tx["amount"] == 75.0


def test_cannot_edit_or_delete_paid_line(admin_client, maya_id):
    r = admin_client.post(
        f"{API}/admin/members/{maya_id}/balance/lines",
        json={"label": "Sealed", "amount": 10.0},
    )
    line = r.json()["lines"][-1]
    admin_client.post(f"{API}/admin/members/{maya_id}/balance/lines/{line['id']}/mark-paid")
    # Edit attempt
    re = admin_client.put(
        f"{API}/admin/members/{maya_id}/balance/lines/{line['id']}",
        json={"amount": 999.0},
    )
    assert re.status_code == 400
    # Delete attempt
    rd = admin_client.delete(f"{API}/admin/members/{maya_id}/balance/lines/{line['id']}")
    assert rd.status_code == 400


def test_member_can_view_own_balance(admin_client, maya_client, maya_id):
    admin_client.put(
        f"{API}/admin/members/{maya_id}/balance/zeffy-url",
        json={"url": "https://www.zeffy.com/en-US/ticketing/maya-link"},
    )
    admin_client.post(
        f"{API}/admin/members/{maya_id}/balance/lines",
        json={"label": "Anniv", "amount": 200.0},
    )
    r = maya_client.get(f"{API}/me/balance")
    assert r.status_code == 200
    body = r.json()
    assert body["zeffy_url"] == "https://www.zeffy.com/en-US/ticketing/maya-link"
    # Only unpaid lines contribute to total; previous test runs may have
    # left paid lines on the record (paid lines cannot be deleted by design).
    assert body["total"] == 200.0
    unpaid = [ln for ln in body["lines"] if not ln["paid_at"]]
    assert len(unpaid) == 1
    assert unpaid[0]["label"] == "Anniv"


def test_member_submits_receipt_admin_approves(admin_client, maya_client, maya_id):
    r = admin_client.post(
        f"{API}/admin/members/{maya_id}/balance/lines",
        json={"label": "Anniv flow", "amount": 50.0},
    )
    line_id = r.json()["lines"][-1]["id"]
    # Member submits
    rs = maya_client.post(
        f"{API}/me/balance/submit-receipt",
        json={"confirmation": "RCT-1234-5678", "line_ids": [line_id]},
    )
    assert rs.status_code == 200, rs.text
    tx_id = rs.json()["transaction_id"]
    # Member's balance now lists the receipt as pending; line is still unpaid.
    bal = maya_client.get(f"{API}/me/balance").json()
    assert bal["total"] == 50.0  # unchanged until admin approves
    assert any(r["id"] == tx_id for r in bal["pending_receipts"])
    # Double-submit blocked
    rs2 = maya_client.post(
        f"{API}/me/balance/submit-receipt",
        json={"confirmation": "RCT-9999-9999", "line_ids": [line_id]},
    )
    assert rs2.status_code == 400
    # Admin approves
    ra = admin_client.put(f"{API}/admin/transactions/{tx_id}/approve-balance")
    assert ra.status_code == 200
    # Balance now cleared
    bal2 = maya_client.get(f"{API}/me/balance").json()
    assert bal2["total"] == 0
    paid = next(ln for ln in bal2["lines"] if ln["id"] == line_id)
    assert paid["paid_via"] == "member_receipt"


def test_member_cannot_select_paid_line(admin_client, maya_client, maya_id):
    r = admin_client.post(
        f"{API}/admin/members/{maya_id}/balance/lines",
        json={"label": "Pre-paid", "amount": 25.0},
    )
    line_id = r.json()["lines"][-1]["id"]
    admin_client.post(f"{API}/admin/members/{maya_id}/balance/lines/{line_id}/mark-paid")
    # Maya can't submit a receipt against a paid line
    rs = maya_client.post(
        f"{API}/me/balance/submit-receipt",
        json={"confirmation": "RCT-AAAA-BBBB", "line_ids": [line_id]},
    )
    assert rs.status_code == 400


def test_member_balance_endpoints_require_auth():
    c = httpx.Client(timeout=10.0)
    r = c.get(f"{API}/me/balance")
    assert r.status_code in (401, 403)
    c.close()


def test_admin_balance_endpoints_require_admin(maya_client, maya_id):
    # Maya is a member, not admin — admin-only endpoints must reject.
    r = maya_client.get(f"{API}/admin/members/{maya_id}/balance")
    assert r.status_code in (401, 403)
