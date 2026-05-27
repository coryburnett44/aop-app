"""Phase B + C backend tests for AOP member portal:
B: Omega, Gear CRUD, Causes CRUD + pledge, Events calendar + check-ins, Reports.
C: PayPal client-id + create-order + capture-404, Email templates + preview + blast (test_only) + history + webhook.
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASSWORD = "Member123!"


# ---------- shared sessions ----------
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
def admin_id(admin):
    return admin.get(f"{API}/auth/me", timeout=15).json()["id"]


@pytest.fixture(scope="module")
def member_id(member):
    return member.get(f"{API}/auth/me", timeout=15).json()["id"]


# ============================================================
# PHASE B
# ============================================================

# ---------- Omega ----------
def test_omega_returns_list(admin):
    r = requests.get(f"{API}/omega", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    # all returned items must be deceased
    for u in data:
        assert u.get("status_override") == "deceased" or u.get("deceased_at")


# ---------- Gear ----------
def test_gear_seeded_list():
    r = requests.get(f"{API}/gear", timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) >= 4
    for g in items:
        assert "id" in g and "name" in g and "price" in g


def test_gear_admin_crud(admin):
    payload = {"name": f"TEST_Gear_{uuid.uuid4().hex[:5]}", "description": "test", "price": 9.99,
               "sizes": ["S", "M"], "colors": ["Navy"], "category": "apparel", "in_stock": True, "sku": "TST-01"}
    r = admin.post(f"{API}/gear", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    assert r.json()["name"] == payload["name"]

    g = requests.get(f"{API}/gear/{gid}", timeout=15).json()
    assert g["price"] == 9.99

    u = admin.put(f"{API}/gear/{gid}", json={"price": 12.5, "in_stock": False}, timeout=15)
    assert u.status_code == 200 and u.json()["price"] == 12.5 and u.json()["in_stock"] is False

    d = admin.delete(f"{API}/gear/{gid}", timeout=15)
    assert d.status_code == 200
    g404 = requests.get(f"{API}/gear/{gid}", timeout=15)
    assert g404.status_code == 404


def test_gear_create_forbidden_for_member(member):
    r = member.post(f"{API}/gear", json={"name": "X", "price": 1}, timeout=15)
    assert r.status_code in (401, 403)


# ---------- Causes ----------
def test_causes_seeded():
    r = requests.get(f"{API}/causes", timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) >= 3


def test_cause_admin_crud_and_pledge(admin, member, member_id):
    create = admin.post(f"{API}/causes", json={"title": f"TEST_Cause_{uuid.uuid4().hex[:5]}",
                                               "description": "tc", "goal_amount": 1000.0,
                                               "category": "general", "is_active": True}, timeout=15)
    assert create.status_code == 200, create.text
    cid = create.json()["id"]

    upd = admin.put(f"{API}/causes/{cid}", json={"goal_amount": 1500.0}, timeout=15)
    assert upd.status_code == 200 and upd.json()["goal_amount"] == 1500.0

    # Pledge as member
    p = member.post(f"{API}/causes/{cid}/pledge", json={"amount": 25.0, "anonymous": False, "note": "go team"},
                    timeout=15)
    assert p.status_code == 200, p.text
    pj = p.json()
    assert pj["status"] == "pending" and pj.get("transaction_id")

    # Admin can list donations for the cause
    dons = admin.get(f"{API}/causes/{cid}/donations", timeout=15)
    assert dons.status_code == 200
    assert any(t.get("amount") == 25.0 for t in dons.json())

    # Cleanup
    admin.delete(f"{API}/causes/{cid}", timeout=15)


def test_pledge_anonymous_uses_anonymous_name(admin, member):
    c = admin.post(f"{API}/causes", json={"title": f"TEST_Anon_{uuid.uuid4().hex[:5]}",
                                          "description": "tc"}, timeout=15)
    cid = c.json()["id"]
    p = member.post(f"{API}/causes/{cid}/pledge", json={"amount": 5.0, "anonymous": True}, timeout=15)
    assert p.status_code == 200
    dons = admin.get(f"{API}/causes/{cid}/donations", timeout=15).json()
    last = next(t for t in dons if t["id"] == p.json()["transaction_id"])
    assert last["user_name"] == "Anonymous" and last["anonymous"] is True
    admin.delete(f"{API}/causes/{cid}", timeout=15)


# ---------- Events Calendar ----------
def test_events_calendar_current_month(admin):
    today = datetime.now(timezone.utc)
    ym = f"{today.year:04d}-{today.month:02d}"
    r = requests.get(f"{API}/calendar/events", params={"month": ym}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for e in data:
        assert "rsvp_count" in e and "checkin_count" in e
        # event start must fall within month
        assert e["start_at"].startswith(ym)


def test_events_calendar_bad_month():
    r = requests.get(f"{API}/calendar/events", params={"month": "bad"}, timeout=15)
    assert r.status_code == 400


# ---------- Check-ins ----------
@pytest.fixture(scope="module")
def test_event(admin):
    # Create an event in the current month for checkins/calendar
    today = datetime.now(timezone.utc)
    start = today.replace(hour=18, minute=0, second=0, microsecond=0).isoformat()
    end = today.replace(hour=20, minute=0, second=0, microsecond=0).isoformat()
    r = admin.post(f"{API}/events", json={
        "title": f"TEST_Event_{uuid.uuid4().hex[:5]}",
        "description": "phase bc test event",
        "start_at": start, "end_at": end,
        "location": "Online",
    }, timeout=15)
    assert r.status_code == 200, r.text
    yield r.json()
    admin.delete(f"{API}/events/{r.json()['id']}", timeout=15)


def test_checkin_member_then_duplicate_then_guest(admin, member_id, test_event):
    eid = test_event["id"]
    # member checkin
    r = admin.post(f"{API}/events/{eid}/check-in",
                   json={"user_id": member_id, "ticket_type": "vip"}, timeout=15)
    assert r.status_code == 200, r.text
    ci = r.json()
    assert ci["ticket_type"] == "vip" and ci["user_id"] == member_id
    cid = ci["id"]

    # duplicate
    r2 = admin.post(f"{API}/events/{eid}/check-in",
                    json={"user_id": member_id, "ticket_type": "general"}, timeout=15)
    assert r2.status_code == 400

    # guest walk-in
    rg = admin.post(f"{API}/events/{eid}/check-in",
                    json={"guest_name": "TEST_Guest_Walkin", "ticket_type": "guest"}, timeout=15)
    assert rg.status_code == 200
    assert rg.json()["user_name"] == "TEST_Guest_Walkin"

    # list
    lst = admin.get(f"{API}/events/{eid}/check-ins", timeout=15)
    assert lst.status_code == 200
    ids = [c["id"] for c in lst.json()]
    assert cid in ids and rg.json()["id"] in ids

    # remove member checkin
    d = admin.delete(f"{API}/events/{eid}/check-ins/{cid}", timeout=15)
    assert d.status_code == 200
    lst2 = admin.get(f"{API}/events/{eid}/check-ins", timeout=15).json()
    assert cid not in [c["id"] for c in lst2]


def test_checkin_requires_user_or_guest(admin, test_event):
    r = admin.post(f"{API}/events/{test_event['id']}/check-in", json={"ticket_type": "general"}, timeout=15)
    assert r.status_code == 400


def test_checkin_member_forbidden(member, test_event):
    r = member.post(f"{API}/events/{test_event['id']}/check-in",
                    json={"user_id": "x", "ticket_type": "general"}, timeout=15)
    assert r.status_code in (401, 403)


# ---------- Reports ----------
def test_report_members_admin(admin):
    r = admin.get(f"{API}/reports/members", timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) >= 1


def test_report_members_filter_role(admin):
    r = admin.get(f"{API}/reports/members", params={"role": "admin"}, timeout=20)
    assert r.status_code == 200
    for m in r.json():
        assert m.get("role") == "admin"


def test_report_hours_admin(admin):
    r = admin.get(f"{API}/reports/hours", timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_report_donations_admin(admin):
    r = admin.get(f"{API}/reports/donations", timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    for t in items:
        assert t.get("type") == "donation"


def test_personnel_brief(admin, member_id):
    r = admin.get(f"{API}/reports/personnel-brief/{member_id}", timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    for key in ("member", "awards", "hours", "events", "checkins", "transactions",
                "approved_hours", "pending_hours", "total_paid", "generated_at"):
        assert key in b, f"missing {key}"
    assert b["member"]["id"] == member_id


def test_personnel_brief_404(admin):
    r = admin.get(f"{API}/reports/personnel-brief/does-not-exist", timeout=15)
    assert r.status_code == 404


def test_reports_admin_only(member, member_id):
    for path in ("/reports/members", "/reports/hours", "/reports/donations",
                 f"/reports/personnel-brief/{member_id}"):
        assert member.get(f"{API}{path}", timeout=15).status_code in (401, 403)


# ============================================================
# PHASE C
# ============================================================

# ---------- PayPal ----------
def test_paypal_client_id_public():
    r = requests.get(f"{API}/payments/paypal/client-id", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["enabled"] is True
    assert j["mode"] == "live"
    assert j["client_id"].startswith("Ac5RJk9ZMOzqKslr5FjxLb1KnSRvRx8ZHRl_hOEzNKlJOZfKTtay2IeSs1AvDkL")


def test_paypal_create_order_donation_persists_pending_tx(member):
    # Use any existing cause
    causes = requests.get(f"{API}/causes", timeout=15).json()
    assert causes, "no causes seeded"
    cid = causes[0]["id"]

    r = member.post(f"{API}/payments/paypal/orders",
                    json={"purpose": "donation", "amount": 1.00, "currency": "USD",
                          "cause_id": cid, "note": "TEST_pp_donation"}, timeout=40)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("order_id") and j.get("transaction_id")
    assert j.get("status") == "CREATED"

    # verify pending transaction was persisted (admin-only listing)
    s_admin = requests.Session()
    s_admin.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    dons = s_admin.get(f"{API}/reports/donations", params={"status_filter": "pending"}, timeout=20).json()
    found = next((d for d in dons if d.get("paypal_order_id") == j["order_id"]), None)
    assert found is not None, "pending donation transaction not persisted"
    assert found["status"] == "pending"
    assert found["type"] == "donation"
    assert found["method"] == "paypal"
    assert found["purpose"] == "donation"


def test_paypal_capture_unknown_order_id(member):
    # PayPal will reject this; we expect either 404 (no DB tx) or 502 from PayPal — both are sensible
    r = member.post(f"{API}/payments/paypal/orders/INVALIDORDER999/capture", timeout=40)
    assert r.status_code in (400, 404, 502), f"unexpected status: {r.status_code} {r.text}"


def test_paypal_create_order_requires_auth():
    r = requests.post(f"{API}/payments/paypal/orders",
                      json={"purpose": "donation", "amount": 1}, timeout=15)
    assert r.status_code in (401, 403)


# ---------- Email templates ----------
def test_email_template_crud(admin):
    body = {"name": f"TEST_Tpl_{uuid.uuid4().hex[:5]}", "subject": "Hi {{name}}",
            "body_html": "<p>Hi {{name}}</p>", "description": "test"}
    r = admin.post(f"{API}/email/templates", json=body, timeout=15)
    assert r.status_code == 200
    tid = r.json()["id"]

    lst = admin.get(f"{API}/email/templates", timeout=15).json()
    assert any(t["id"] == tid for t in lst)

    u = admin.put(f"{API}/email/templates/{tid}", json={"subject": "New {{name}}"}, timeout=15)
    assert u.status_code == 200 and u.json()["subject"] == "New {{name}}"

    d = admin.delete(f"{API}/email/templates/{tid}", timeout=15)
    assert d.status_code == 200


def test_email_templates_member_forbidden(member):
    assert member.get(f"{API}/email/templates", timeout=15).status_code in (401, 403)


# ---------- Email preview ----------
def test_email_preview(admin):
    r = admin.post(f"{API}/email/preview",
                   json={"subject": "Hello {{name}}", "body_html": "<p>Hi {{name}}, welcome!</p>",
                         "segment": "admins"}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "recipient_count" in j and j["recipient_count"] >= 1
    assert "html" in j and "<p>Hi" in j["html"]
    # variable substituted (admin's actual name in the html)
    assert "{{name}}" not in j["html"]


# ---------- Email blast (test_only) + history + webhook ----------
@pytest.fixture(scope="module")
def blast_id_holder():
    return {}


def test_email_blast_test_only(admin, blast_id_holder):
    body = {"subject": "TEST Blast {{name}}",
            "body_html": "<p>Hi {{name}}, this is a phase-c test blast.</p>",
            "segment": "admins", "test_only": True}
    r = admin.post(f"{API}/email/blast", json=body, timeout=60)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "blast_id" in j
    # On Resend free tier, sending to admin@clubhaven.app may fail — both are acceptable.
    assert (j["sent"] + j["failed"]) >= 1
    blast_id_holder["id"] = j["blast_id"]


def test_email_blasts_history(admin, blast_id_holder):
    r = admin.get(f"{API}/email/blasts", timeout=15)
    assert r.status_code == 200
    blasts = r.json()
    assert isinstance(blasts, list) and len(blasts) >= 1
    bid = blast_id_holder.get("id")
    if bid:
        found = next((b for b in blasts if b["id"] == bid), None)
        assert found is not None, "just-sent blast missing in history"
        assert "sent_count" in found and "failed_count" in found


def test_email_webhook_increments_counter(blast_id_holder):
    bid = blast_id_holder.get("id")
    if not bid:
        pytest.skip("no blast id from prior test")
    payload = {"type": "email.opened",
               "data": {"tags": [{"name": "blast_id", "value": bid}]}}
    r = requests.post(f"{API}/email/webhook", json=payload, timeout=15)
    assert r.status_code == 200 and r.json().get("ok") is True

    # verify counter incremented in history
    s = requests.Session()
    s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    blasts = s.get(f"{API}/email/blasts", timeout=15).json()
    found = next((b for b in blasts if b["id"] == bid), None)
    assert found is not None
    assert found.get("opens", 0) >= 1


def test_email_webhook_unknown_blast_ok():
    payload = {"type": "email.delivered",
               "data": {"tags": [{"name": "blast_id", "value": "nonexistent-blast"}]}}
    r = requests.post(f"{API}/email/webhook", json=payload, timeout=15)
    assert r.status_code == 200


def test_email_blast_member_forbidden(member):
    r = member.post(f"{API}/email/blast",
                    json={"subject": "x", "body_html": "<p>x</p>", "segment": "admins", "test_only": True},
                    timeout=15)
    assert r.status_code in (401, 403)


# ============================================================
# Phase A regression smoke
# ============================================================
def test_phase_a_endpoints_alive(admin):
    for p in ("/members-new", "/members-birthdays", "/chapters", "/awards", "/hours"):
        r = admin.get(f"{API}{p}", timeout=15)
        assert r.status_code == 200, f"{p}: {r.status_code} {r.text[:120]}"
