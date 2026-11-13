
import pytest
from fastapi.testclient import TestClient

from rules_server import authorization
from rules_server.main import app

PAYMENT = {
    "invoice_number": "INV-2026-0001",
    "supplier_id": "SUP-001",
    "amount": "15000.00",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Keep test reservations separate from real demo data.
    monkeypatch.setattr(
        authorization,
        "DB_PATH",
        tmp_path / "test_authorizations.db",
    )

    monkeypatch.setenv(
        "RULES_SERVER_API_KEY",
        "integration-test-key",
    )

    with TestClient(app) as test_client:
        yield test_client


def test_missing_api_key_is_rejected(client):
    response = client.post(
        "/authorize-payment",
        json=PAYMENT,
    )

    assert response.status_code == 401


def test_valid_payment_is_authorized(client):
    response = client.post(
        "/authorize-payment",
        json=PAYMENT,
        headers={
            "X-Service-Key": "integration-test-key",
        },
    )

    assert response.status_code == 200
    assert response.json()["authorized"] is True


def test_duplicate_invoice_is_rejected(client):
    headers = {
        "X-Service-Key": "integration-test-key",
    }

    first = client.post(
        "/authorize-payment",
        json=PAYMENT,
        headers=headers,
    )

    second = client.post(
        "/authorize-payment",
        json=PAYMENT,
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["authorized"] is True

    assert second.status_code == 200
    assert second.json()["authorized"] is False
    assert (
        second.json()["reason"]
        == "Invoice already reserved or authorized"
    )
