
from fastapi.testclient import TestClient
from rules_server.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_valid_payment():
    response = client.post("/validate-payment", json={
        "invoice_number": "INV-2026-0001",
        "supplier_id": "SUP-001",
        "amount": 15000
    })
    assert response.status_code == 200
    assert response.json()["approved"] is True


def test_unapproved_supplier():
    response = client.post("/validate-payment", json={
        "invoice_number": "INV-2026-0001",
        "supplier_id": "SUP-999",
        "amount": 15000
    })
    assert response.json()["approved"] is False
    assert "Supplier is not approved" in response.json()["reasons"]


def test_excessive_payment():
    response = client.post("/validate-payment", json={
        "invoice_number": "INV-2026-0001",
        "supplier_id": "SUP-001",
        "amount": 60000
    })
    assert response.json()["approved"] is False
    assert "Payment exceeds the spending limit" in response.json()["reasons"]


def test_invoice_mismatch():
    response = client.post("/validate-payment", json={
        "invoice_number": "INV-2026-0001",
        "supplier_id": "SUP-002",
        "amount": 15000
    })
    assert response.json()["approved"] is False


def test_unknown_invoice():
    response = client.post("/validate-payment", json={
        "invoice_number": "INV-UNKNOWN",
        "supplier_id": "SUP-001",
        "amount": 15000
    })
    assert response.json()["approved"] is False
    assert "Invoice is not registered" in response.json()["reasons"]
