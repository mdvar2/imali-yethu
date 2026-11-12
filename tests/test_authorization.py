
import pytest
from fastapi.testclient import TestClient

from rules_server import authorization
from rules_server.main import app

client = TestClient(app)

AUTH_HEADERS = {"X-Service-Key": "test-secret"}


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-secret")

    monkeypatch.setattr(
        authorization,
        "DB_PATH",
        tmp_path / "authorizations.db",
    )


def valid_payment():
    return {
        "invoice_number": "INV-2026-0001",
        "supplier_id": "SUP-001",
        "amount": 15000,
    }


def test_first_authorization_succeeds():
    response = client.post(
    "/authorize-payment",
    json=valid_payment(),
    headers=AUTH_HEADERS,
)
    assert response.status_code == 200
    assert response.json()["authorized"] is True



def test_duplicate_authorization_rejected():
    first = client.post(
        "/authorize-payment",
        json=valid_payment(),
        headers=AUTH_HEADERS,
    )

    second = client.post(
        "/authorize-payment",
        json=valid_payment(),
        headers=AUTH_HEADERS,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["authorized"] is True
    assert second.json()["authorized"] is False


def test_invalid_payment_not_authorized():
    payment = valid_payment()
    payment["supplier_id"] = "SUP-999"

    response = client.post(
        "/authorize-payment",
        json=payment,
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["authorized"] is False



def test_validation_does_not_reserve_invoice():
    response = client.post("/validate-payment", json=valid_payment())
    assert response.json()["approved"] is True

    response = client.post(
    "/authorize-payment",
    json=valid_payment(),
    headers=AUTH_HEADERS,
)
    assert response.json()["authorized"] is True
