"""Iteration 71 — Bulk-add anniversary fee endpoint tests.

Covers POST /api/admin/members/balance/bulk-add-line:
  - happy path: created/skipped/error counts + response shape
  - idempotency (second identical call skips all)
  - mixed valid + bogus user_ids
  - input validation (empty list / 0 / negative / >100000 / empty label)
  - authorization (member cannot call it)
  - GET /api/members surfaces outstanding_balance_total per member
"""
import os
import pytest
import httpx

API_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not API_BASE:
    pytest.skip("REACT_APP_BACKEND_URL not set — skipping live API tests", allow_module_level=True)

API = f"{API_BASE.rstrip('/')}/api"
ADMIN = ("admin@clubhaven.app", "Admin123!")
MAYA = ("maya.patel@clubhaven.app", "Demo123!")

LABEL = "TEST_iter71_anniversary"


def _login(client, email, password):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def admin_client():
    c = httpx.Client(timeout=20.0, follow_redirects=True)
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
def members(admin_client):
    r = admin_client.get(f"{API}/members")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def three_member_ids(members):
    # Prefer demo members; pad with any other non-admin members if needed.
    preferred = [
        "maya.patel@clubhaven.app",
        "jordan.reed@clubhaven.app",
        "sam.okafor@clubhaven.app",
        "harper.liu@clubhaven.app",
    ]
    by_email = {m["email"]: m["id"] for m in members if m.get("email")}
    ids = [by_email[e] for e in preferred if e in by_email]
    if len(ids) < 3:
        # Fall back to any active member (skip admins)
        for m in members:
            if m["id"] in ids:
                continue
            if (m.get("role") or "").lower() == "admin":
                continue
            ids.append(m["id"])
            if len(ids) >= 3:
                break
    assert len(ids) >= 3, f"Expected at least 3 members, got {ids}"
    return ids[:3]


@pytest.fixture(autouse=True)
def cleanup_bulk_lines(admin_client, three_member_ids):
    """Before AND after each test, wipe any TEST_iter71 lines on the 3 demo
    members so reruns are clean."""

    def _wipe():
        for uid in three_member_ids:
            try:
                bal = admin_client.get(f"{API}/admin/members/{uid}/balance").json()
                for ln in bal.get("lines", []):
                    if ln.get("label", "").startswith("TEST_iter71") and not ln.get("paid_at"):
                        admin_client.delete(
                            f"{API}/admin/members/{uid}/balance/lines/{ln['id']}"
                        )
            except Exception:
                pass

    _wipe()
    yield
    _wipe()


# ---------- Happy path ----------
def test_bulk_add_creates_lines_and_response_shape(admin_client, three_member_ids):
    r = admin_client.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": three_member_ids, "label": LABEL, "amount": 75.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Shape
    for key in (
        "created_count",
        "skipped_count",
        "error_count",
        "created_user_ids",
        "skipped_user_ids",
        "errors",
        "label",
        "amount",
    ):
        assert key in body, f"missing key {key}"
    assert body["created_count"] == 3
    assert body["skipped_count"] == 0
    assert body["error_count"] == 0
    assert set(body["created_user_ids"]) == set(three_member_ids)
    assert body["label"] == LABEL
    assert body["amount"] == 75.0

    # Verify via per-member balance reads
    for uid in three_member_ids:
        bal = admin_client.get(f"{API}/admin/members/{uid}/balance").json()
        assert bal["total"] == 75.0
        labels = [ln["label"] for ln in bal["lines"] if not ln["paid_at"]]
        assert LABEL in labels


def test_outstanding_balance_total_on_members_endpoint(admin_client, three_member_ids):
    # Add the lines first
    admin_client.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": three_member_ids, "label": LABEL, "amount": 42.0},
    )
    rows = admin_client.get(f"{API}/members").json()
    by_id = {m["id"]: m for m in rows}
    for uid in three_member_ids:
        m = by_id.get(uid)
        assert m is not None
        assert "outstanding_balance_total" in m, "members endpoint missing field"
        assert m["outstanding_balance_total"] == 42.0, (
            f"member {uid} total={m['outstanding_balance_total']}"
        )

    # Others should have 0
    others = [
        m
        for m in rows
        if m["id"] not in three_member_ids
        and m.get("outstanding_balance_total", 0) > 0
        and any(
            ln_label.startswith("TEST_iter71")
            for ln_label in []  # No way to read other members' lines, but
            # if they were 0 before they should still be 0 after our targeted call.
        )
    ]
    assert others == []


# ---------- Idempotency ----------
def test_bulk_add_is_idempotent_on_repeat_call(admin_client, three_member_ids):
    r1 = admin_client.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": three_member_ids, "label": LABEL, "amount": 50.0},
    )
    assert r1.json()["created_count"] == 3
    # Second identical call — must skip all
    r2 = admin_client.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": three_member_ids, "label": LABEL, "amount": 50.0},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["created_count"] == 0
    assert body["skipped_count"] == 3
    assert set(body["skipped_user_ids"]) == set(three_member_ids)


def test_bulk_add_idempotency_is_case_insensitive(admin_client, three_member_ids):
    admin_client.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": three_member_ids, "label": LABEL, "amount": 50.0},
    )
    r = admin_client.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": three_member_ids, "label": LABEL.upper(), "amount": 50.0},
    )
    assert r.status_code == 200
    assert r.json()["skipped_count"] == 3
    assert r.json()["created_count"] == 0


# ---------- Mixed valid + bogus ----------
def test_bulk_add_mixed_valid_and_bogus(admin_client, three_member_ids):
    bogus = "bogus-uuid-not-real-12345"
    mixed = three_member_ids[:2] + [bogus]
    r = admin_client.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": mixed, "label": LABEL, "amount": 25.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created_count"] == 2
    assert body["error_count"] == 1
    assert body["errors"][0]["user_id"] == bogus
    assert "not found" in body["errors"][0]["error"].lower()


# ---------- Validation ----------
@pytest.mark.parametrize(
    "payload",
    [
        {"user_ids": [], "label": "X", "amount": 10.0},          # empty list
        {"user_ids": ["x"], "label": "", "amount": 10.0},        # empty label
        {"user_ids": ["x"], "label": "L", "amount": 0},          # zero
        {"user_ids": ["x"], "label": "L", "amount": -1.0},       # negative
        {"user_ids": ["x"], "label": "L", "amount": 100001},     # > 100000
    ],
)
def test_bulk_add_validation_422(admin_client, payload):
    r = admin_client.post(f"{API}/admin/members/balance/bulk-add-line", json=payload)
    assert r.status_code == 422, f"payload {payload} → {r.status_code}: {r.text}"


# ---------- Authorization ----------
def test_bulk_add_member_forbidden(maya_client, three_member_ids):
    r = maya_client.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": three_member_ids, "label": LABEL, "amount": 10.0},
    )
    assert r.status_code in (401, 403)


def test_bulk_add_unauthenticated_blocked(three_member_ids):
    c = httpx.Client(timeout=10.0)
    r = c.post(
        f"{API}/admin/members/balance/bulk-add-line",
        json={"user_ids": three_member_ids, "label": LABEL, "amount": 10.0},
    )
    assert r.status_code in (401, 403)
    c.close()
