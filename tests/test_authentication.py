
from fastapi.testclient import TestClient

from rules_server import authorization
from rules_server.main import app

client = TestClient(app)

PAYMENT = {
    "invoice_number": "INV-2026-0001",
    "supplier_id": "SUP-001",
    "amount": 15000,
}


def test_missing_key_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-secret")
    monkeypatch.setattr(
        authorization, "DB_PATH", tmp_path / "auth.db"
    )

    response = client.post("/authorize-payment", json=PAYMENT)

    assert response.status_code == 401


def test_invalid_key_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-secret")
    monkeypatch.setattr(
        authorization, "DB_PATH", tmp_path / "auth.db"
    )

    response = client.post(
        "/authorize-payment",
        json=PAYMENT,
        headers={"X-Service-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_valid_key_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-secret")
    monkeypatch.setattr(
        authorization, "DB_PATH", tmp_path / "auth.db"
    )

    response = client.post(
        "/authorize-payment",
        json=PAYMENT,
        headers={"X-Service-Key": "test-secret"},
    )

    assert response.status_code == 200
    assert response.json()["authorized"] is True


def test_unconfigured_auth_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("RULES_SERVER_API_KEY", raising=False)
    monkeypatch.setattr(
        authorization, "DB_PATH", tmp_path / "auth.db"
    )

    response = client.post("/authorize-payment", json=PAYMENT)

    assert response.status_code == 503
