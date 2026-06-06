"""Iteration 39 — RSVP / paid-event / check-in route extraction regression suite.

Verifies that the new /app/backend/routes/rsvps.py module preserves the same
API surface and response shapes as before (routes were moved out of server.py,
not modified).

Covers:
  - POST /api/events/{id}/rsvp toggle on a FREE event
  - POST /api/events/{id}/rsvp on a PAID event -> 402
  - POST /api/events/{id}/rsvp on a CANCELLED event -> 400
  - PUT  /api/events/{id}/rsvp/guests in-place edit
  - GET  /api/me/events lists the caller's RSVP'd events
  - POST /api/events/{id}/payment/confirm creates pending event_ticket tx
  - PUT  /api/transactions/{tx_id}/approve-event-ticket marks completed + makes RSVP
  - GET  /api/checkin/lookup/{token} (bad + good)
  - POST /api/checkin/scan/{token} idempotent + 403 for non-admin
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://club-express-lite.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@clubhaven.app", "Admin123!")
MEMBER = ("member@clubhaven.app", "Member123!")


# ---------- helpers ----------
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_s():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def member_s():
    return _login(*MEMBER)


def _iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _make_event(admin_s, *, is_paid=False, cancelled=False, capacity=0, title_suffix=""):
    payload = {
        "title": f"TEST_iter39_evt_{title_suffix or uuid.uuid4().hex[:6]}",
        "description": "iter39 test",
        "start_at": _iso(datetime.now(timezone.utc) + timedelta(days=14)),
        "end_at": _iso(datetime.now(timezone.utc) + timedelta(days=14, hours=2)),
        "location": "Test Venue",
        "capacity": capacity,
        "is_paid": is_paid,
        "payment_amount": 25.0 if is_paid else 0.0,
    }
    r = admin_s.post(f"{API}/events", json=payload, timeout=20)
    assert r.status_code in (200, 201), f"create event: {r.status_code} {r.text}"
    eid = r.json()["id"]
    if cancelled:
        rc = admin_s.put(f"{API}/events/{eid}", json={"cancelled": True}, timeout=20)
        assert rc.status_code == 200, f"cancel event: {rc.status_code} {rc.text}"
    return eid


def _cleanup_event(admin_s, eid):
    try:
        admin_s.delete(f"{API}/events/{eid}", timeout=20)
    except Exception:
        pass


# ---------- RSVP on FREE event (toggle) ----------
class TestFreeRSVPToggle:
    def test_rsvp_create_then_remove(self, admin_s, member_s):
        eid = _make_event(admin_s, is_paid=False)
        try:
            # First RSVP -> rsvped True
            r1 = member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            assert r1.status_code == 200, r1.text
            d1 = r1.json()
            assert d1["rsvped"] is True
            assert d1["guests"] == 0
            assert isinstance(d1.get("ticket_id"), str) and len(d1["ticket_id"]) > 0

            # Event counters incremented
            e_after = admin_s.get(f"{API}/events/{eid}", timeout=20).json()
            assert e_after.get("rsvp_count", 0) >= 1

            # Visible in /me/events
            mine = member_s.get(f"{API}/me/events", timeout=20)
            assert mine.status_code == 200
            assert any(ev["id"] == eid for ev in mine.json())

            # Second call toggles OFF
            r2 = member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            assert r2.status_code == 200, r2.text
            assert r2.json() == {"rsvped": False}

            mine2 = member_s.get(f"{API}/me/events", timeout=20).json()
            assert not any(ev["id"] == eid for ev in mine2)
        finally:
            _cleanup_event(admin_s, eid)


# ---------- RSVP on PAID -> 402, CANCELLED -> 400 ----------
class TestRSVPGuards:
    def test_paid_event_returns_402(self, admin_s, member_s):
        eid = _make_event(admin_s, is_paid=True)
        try:
            r = member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
            assert "payment" in (r.json().get("detail", "").lower())
            assert "/payment/confirm" in r.json().get("detail", "")
        finally:
            _cleanup_event(admin_s, eid)

    def test_cancelled_event_returns_400(self, admin_s, member_s):
        eid = _make_event(admin_s, is_paid=False, cancelled=True)
        try:
            r = member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
            assert "cancel" in (r.json().get("detail", "").lower())
        finally:
            _cleanup_event(admin_s, eid)


# ---------- Guest-list edit-in-place ----------
class TestGuestListEdit:
    def test_put_guests_does_not_toggle(self, admin_s, member_s):
        eid = _make_event(admin_s, is_paid=False, capacity=0)
        try:
            # Create RSVP first
            r0 = member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            assert r0.status_code == 200
            assert r0.json()["rsvped"] is True

            # Add two guests via PUT
            payload = {
                "guests": [
                    {"name": "TEST Guest A", "ticket_type": "general"},
                    {"name": "TEST Guest B", "ticket_type": "general"},
                ]
            }
            r1 = member_s.put(f"{API}/events/{eid}/rsvp/guests", json=payload, timeout=20)
            assert r1.status_code == 200, r1.text
            assert r1.json() == {"ok": True, "guests": 2}

            # Still RSVP'd (verify by /me/events)
            mine = member_s.get(f"{API}/me/events", timeout=20).json()
            assert any(ev["id"] == eid for ev in mine)

            # Edit again: remove one guest -> should still not toggle
            r2 = member_s.put(
                f"{API}/events/{eid}/rsvp/guests",
                json={"guests": [{"name": "TEST Guest A", "ticket_type": "general"}]},
                timeout=20,
            )
            assert r2.status_code == 200
            assert r2.json()["guests"] == 1
        finally:
            # untoggle RSVP cleanly
            try:
                member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            except Exception:
                pass
            _cleanup_event(admin_s, eid)


# ---------- Paid path: confirm receipt -> pending tx -> admin approve -> RSVP ----------
class TestPaidEventApprovalFlow:
    def test_full_paid_flow(self, admin_s, member_s):
        eid = _make_event(admin_s, is_paid=True)
        tx_id = None
        try:
            # Member submits Zeffy receipt -> pending transaction
            body = {
                "confirmation": f"TEST-ZEFFY-{uuid.uuid4().hex[:8]}",
                "ticket_type": "general",
                "guests": [],
            }
            r1 = member_s.post(f"{API}/events/{eid}/payment/confirm", json=body, timeout=20)
            assert r1.status_code == 200, r1.text
            d1 = r1.json()
            tx_id = d1.get("transaction_id")
            assert isinstance(tx_id, str) and len(tx_id) > 0
            assert d1.get("status") == "pending"
            assert d1.get("auto_approved") is False

            # No RSVP yet (member shouldn't see the event in /me/events)
            mine = member_s.get(f"{API}/me/events", timeout=20).json()
            assert not any(ev["id"] == eid for ev in mine), "RSVP must NOT exist before admin approval"

            # Admin approves
            r2 = admin_s.put(f"{API}/transactions/{tx_id}/approve-event-ticket", timeout=20)
            assert r2.status_code == 200, r2.text
            d2 = r2.json()
            assert d2.get("ok") is True
            assert isinstance(d2.get("rsvp_id"), str) and len(d2["rsvp_id"]) > 0
            assert isinstance(d2.get("ticket_id"), str) and len(d2["ticket_id"]) > 0

            # Re-approval is idempotent
            r3 = admin_s.put(f"{API}/transactions/{tx_id}/approve-event-ticket", timeout=20)
            assert r3.status_code == 200
            assert r3.json().get("already") is True

            # Now the event shows up in member's RSVPs
            mine2 = member_s.get(f"{API}/me/events", timeout=20).json()
            assert any(ev["id"] == eid for ev in mine2), "RSVP must exist after approval"
        finally:
            # cleanup RSVP & event
            try:
                member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            except Exception:
                pass
            _cleanup_event(admin_s, eid)


# ---------- Check-in lookup + scan ----------
class TestCheckin:
    def test_lookup_bad_token_returns_400(self):
        r = requests.get(f"{API}/checkin/lookup/not-a-real-token", timeout=20)
        assert r.status_code == 400
        assert "invalid" in r.json().get("detail", "").lower()

    def test_lookup_and_scan_valid_flow(self, admin_s, member_s):
        eid = _make_event(admin_s, is_paid=False)
        try:
            # member RSVPs free
            r0 = member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            assert r0.status_code == 200
            ticket_id = r0.json()["ticket_id"]

            # We need the signed JWT token — backend exposes it via /me/tickets? not guaranteed.
            # Use admin endpoint listing rsvps OR mint the token via /api/events/{id}/my-ticket if present.
            # Fall-back: rely on the admin transactions endpoint — but free event has no tx.
            # Try a likely helper endpoint first.
            # Mint the token directly using the backend JWT secret (same algo as routes/rsvps.py)
            import time
            try:
                import jwt as _jwt
            except ImportError:
                pytest.skip("pyjwt not installed in test runner")
                return
            secret = os.environ.get("JWT_SECRET")
            if not secret:
                # Read from backend/.env
                try:
                    with open("/app/backend/.env") as fh:
                        for ln in fh:
                            if ln.startswith("JWT_SECRET"):
                                secret = ln.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except Exception:
                    pass
            if not secret:
                pytest.skip("JWT_SECRET unavailable to mint test ticket token")
                return
            tok = _jwt.encode(
                {
                    "event_id": eid,
                    "ticket_id": ticket_id,
                    "kind": "member",
                    "ticket_type": "general",
                    "name": "TEST Member",
                    "iat": int(time.time()),
                },
                secret,
                algorithm="HS256",
            )

            # Lookup as anonymous (no auth)
            r_lookup = requests.get(f"{API}/checkin/lookup/{tok}", timeout=20)
            assert r_lookup.status_code == 200, r_lookup.text
            assert r_lookup.json().get("ticket_id") == ticket_id

            # Member (non-admin) scan -> 403
            r_member_scan = member_s.post(f"{API}/checkin/scan/{tok}", timeout=20)
            assert r_member_scan.status_code == 403

            # Admin scan -> first time records check-in
            r_scan1 = admin_s.post(f"{API}/checkin/scan/{tok}", timeout=20)
            assert r_scan1.status_code == 200, r_scan1.text
            assert r_scan1.json().get("already_checked_in") is False
            # Second scan -> idempotent
            r_scan2 = admin_s.post(f"{API}/checkin/scan/{tok}", timeout=20)
            assert r_scan2.status_code == 200
            assert r_scan2.json().get("already_checked_in") is True
        finally:
            try:
                member_s.post(f"{API}/events/{eid}/rsvp", json={"guests": []}, timeout=20)
            except Exception:
                pass
            _cleanup_event(admin_s, eid)
