"""HTTP tests for the citizen transparency API."""

import pytest
from fastapi.testclient import TestClient

from rules_server import main


client = TestClient(main.app)

PUBLIC_RECORD = {
    "invoice_number": "TEST-INV-001",
    "supplier_id": "TEST-SUP-001",
    "amount": "15000.00",
    "status": "validated",
    "network": "XRPL Testnet",
    "transaction_hash": "A" * 64,
    "explorer_url": (
        "https://testnet.xrpl.org/transactions/" + "A" * 64
    ),
    "verification_status": "recorded_validated",
}


def test_public_endpoint_requires_no_credentials(monkeypatch):
    monkeypatch.setattr(
        main,
        "list_public_payments",
        lambda limit=100: [PUBLIC_RECORD],
    )

    response = client.get("/public/payments")

    assert response.status_code == 200
    assert response.json() == {
        "network": "XRPL Testnet",
        "environment": "demonstration",
        "payments": [PUBLIC_RECORD],
    }


def test_public_endpoint_does_not_return_internal_audit(monkeypatch):
    monkeypatch.setattr(
        main,
        "list_public_payments",
        lambda limit=100: [PUBLIC_RECORD],
    )

    response = client.get("/public/payments")

    assert response.status_code == 200

    body = response.json()

    assert "events" not in str(body)
    assert "PRIVATE INTERNAL FAILURE DETAILS" not in str(body)
    assert "reason" not in body["payments"][0]


@pytest.mark.parametrize(
    "limit",
    ["0", "-1", "101", "abc", "1.5"],
)
def test_invalid_limits_are_rejected(limit):
    response = client.get(
        "/public/payments",
        params={"limit": limit},
    )

    assert response.status_code == 422


def test_valid_limit_is_forwarded(monkeypatch):
    observed = []

    def fake_public_payments(limit=100):
        observed.append(limit)
        return []

    monkeypatch.setattr(
        main,
        "list_public_payments",
        fake_public_payments,
    )

    response = client.get(
        "/public/payments",
        params={"limit": 5},
    )

    assert response.status_code == 200
    assert observed == [5]


def test_admin_history_still_requires_credentials(monkeypatch):
    monkeypatch.setenv(
        "RULES_SERVER_API_KEY",
        "test-service-key",
    )
    monkeypatch.setenv(
        "RULES_ADMIN_API_KEY",
        "different-test-admin-key",
    )

    response = client.get("/admin/payment-history")

    assert response.status_code == 401
    assert "payments" not in response.json()


def test_public_endpoint_does_not_expose_admin_fields(monkeypatch):
    monkeypatch.setattr(
        main,
        "list_public_payments",
        lambda limit=100: [PUBLIC_RECORD],
    )

    response = client.get("/public/payments")

    assert response.status_code == 200

    allowed_fields = set(PUBLIC_RECORD)

    for payment in response.json()["payments"]:
        assert set(payment) == allowed_fields
        assert "reason" not in payment
        assert "events" not in payment
        assert "created_at" not in payment
