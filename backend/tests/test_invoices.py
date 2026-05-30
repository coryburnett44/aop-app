"""Backend tests for invoice API + PayPal config endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://invoice-pay-cory.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def sample_payload():
    return {
        "invoice_number": "TEST-INV-001",
        "issue_date": "2026-01-10",
        "due_date": "2026-01-24",
        "customer_name": "TEST_Customer",
        "customer_email": "test@example.com",
        "customer_address": "123 Test St",
        "items": [
            {"description": "Design work", "quantity": 2, "rate": 100.0},
            {"description": "Consulting", "quantity": 1, "rate": 50.0},
        ],
        "tax_rate": 10.0,
        "discount": 25.0,
        "notes": "Thanks!",
        "terms": "Net 14",
        "currency": "USD",
    }


# ---------- Health / Config ----------
def test_root(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("message") == "Invoice API"
    assert data.get("paypal_mode") == "sandbox"


def test_paypal_config(session):
    r = session.get(f"{API}/config/paypal")
    assert r.status_code == 200
    data = r.json()
    assert "client_id" in data
    assert "mode" in data
    assert "configured" in data
    assert data["mode"] == "sandbox"
    # SECRET is empty intentionally
    assert data["configured"] is False


# ---------- CRUD ----------
created_id = {"id": None}


def test_create_invoice(session, sample_payload):
    r = session.post(f"{API}/invoices", json=sample_payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["customer_name"] == "TEST_Customer"
    assert data["invoice_number"] == "TEST-INV-001"
    assert len(data["items"]) == 2
    # Totals: subtotal = 2*100 + 1*50 = 250; tax = 25; discount=25; total = 250-25+25=250
    assert data["subtotal"] == 250.0
    assert data["tax"] == 25.0
    assert data["discount"] == 25.0
    assert data["total"] == 250.0
    assert data["status"] == "draft"
    assert "id" in data and isinstance(data["id"], str)
    created_id["id"] = data["id"]


def test_list_invoices(session):
    r = session.get(f"{API}/invoices")
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list)
    assert any(i["id"] == created_id["id"] for i in arr)


def test_get_invoice(session):
    r = session.get(f"{API}/invoices/{created_id['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == created_id["id"]
    assert data["total"] == 250.0


def test_get_invoice_not_found(session):
    r = session.get(f"{API}/invoices/nonexistent-id-xyz")
    assert r.status_code == 404


def test_patch_invoice(session):
    update = {
        "items": [{"description": "Updated", "quantity": 3, "rate": 100.0}],
        "tax_rate": 5.0,
        "discount": 0.0,
    }
    r = session.patch(f"{API}/invoices/{created_id['id']}", json=update)
    assert r.status_code == 200, r.text
    data = r.json()
    # subtotal=300, tax=15, total=315
    assert data["subtotal"] == 300.0
    assert data["tax"] == 15.0
    assert data["total"] == 315.0
    # Verify persistence
    r2 = session.get(f"{API}/invoices/{created_id['id']}")
    assert r2.json()["subtotal"] == 300.0


def test_paypal_create_order_not_configured(session):
    # SECRET is empty -> should return 503
    r = session.post(f"{API}/invoices/{created_id['id']}/paypal/create-order")
    assert r.status_code == 503
    assert "PayPal" in r.json().get("detail", "")


def test_mark_paid(session):
    r = session.post(f"{API}/invoices/{created_id['id']}/mark-paid")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "paid"
    assert data.get("paid_at")


def test_mark_paid_not_found(session):
    r = session.post(f"{API}/invoices/nonexistent/mark-paid")
    assert r.status_code == 404


def test_delete_invoice(session):
    r = session.delete(f"{API}/invoices/{created_id['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    # Verify gone
    r2 = session.get(f"{API}/invoices/{created_id['id']}")
    assert r2.status_code == 404


def test_delete_invoice_not_found(session):
    r = session.delete(f"{API}/invoices/nonexistent-id-xyz")
    assert r.status_code == 404


# ---------- Totals edge cases ----------
def test_totals_zero_items(session):
    payload = {
        "invoice_number": "TEST-ZERO",
        "issue_date": "2026-01-10",
        "due_date": "2026-01-24",
        "customer_name": "TEST_Zero",
        "items": [],
        "tax_rate": 10,
        "discount": 0,
    }
    r = session.post(f"{API}/invoices", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["subtotal"] == 0
    assert data["total"] == 0
    # cleanup
    session.delete(f"{API}/invoices/{data['id']}")


def test_totals_discount_larger_than_subtotal_clamps_to_zero(session):
    payload = {
        "invoice_number": "TEST-NEG",
        "issue_date": "2026-01-10",
        "due_date": "2026-01-24",
        "customer_name": "TEST_Neg",
        "items": [{"description": "x", "quantity": 1, "rate": 10}],
        "tax_rate": 0,
        "discount": 50,
    }
    r = session.post(f"{API}/invoices", json=payload)
    assert r.status_code == 200
    data = r.json()
    # subtotal=10, total = max(10-50+0, 0)= 0
    assert data["total"] == 0
    session.delete(f"{API}/invoices/{data['id']}")
