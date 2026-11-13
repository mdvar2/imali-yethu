"""Security and functionality tests for CFO payment history."""

from fastapi.testclient import TestClient

from rules_server import main


client = TestClient(main.app)


def test_payment_history_requires_admin_key(monkeypatch):
    monkeypatch.setenv("RULES_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-service-key")

    response = client.get("/admin/payment-history")

    assert response.status_code == 401


def test_payment_history_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("RULES_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-service-key")

    response = client.get(
        "/admin/payment-history",
        headers={"X-Admin-Key": "incorrect-key"},
    )

    assert response.status_code == 401


def test_payment_history_rejects_service_key(monkeypatch):
    monkeypatch.setenv("RULES_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-service-key")

    response = client.get(
        "/admin/payment-history",
        headers={"X-Admin-Key": "test-service-key"},
    )

    assert response.status_code == 401


def test_payment_history_requires_independent_admin_auth(monkeypatch):
    monkeypatch.setenv("RULES_ADMIN_API_KEY", "same-key")
    monkeypatch.setenv("RULES_SERVER_API_KEY", "same-key")

    response = client.get(
        "/admin/payment-history",
        headers={"X-Admin-Key": "same-key"},
    )

    assert response.status_code == 503


def test_payment_history_returns_records(monkeypatch):
    monkeypatch.setenv("RULES_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-service-key")

    expected = [
        {
            "invoice_number": "TEST-001",
            "supplier_id": "SUP-001",
            "amount": "15000.00",
            "status": "validated",
            "events": [
                {
                    "event_type": "VALIDATED",
                    "reason": None,
                    "transaction_hash": "test-transaction-hash",
                    "created_at": "2026-11-13 12:00:00",
                }
            ],
        }
    ]

    monkeypatch.setattr(
        main,
        "list_payment_history",
        lambda limit=100: expected,
    )

    response = client.get(
        "/admin/payment-history",
        headers={"X-Admin-Key": "test-admin-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"payments": expected}
