
import copy

import pytest
from fastapi.testclient import TestClient

from rules_server.main import app

client = TestClient(app)

TREASURY = "rTestTreasuryAddress"
SUPPLIER = "rTestSupplierAddress"
HEADERS = {"X-Service-Key": "test-secret"}


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-secret")
    monkeypatch.setenv("TREASURY_ADDRESS", TREASURY)
    monkeypatch.setenv("HONEST_SUPPLIER_ADDRESS", SUPPLIER)


def valid_transaction():
    return {
        "TransactionType": "Payment",
        "Account": TREASURY,
        "Destination": SUPPLIER,
        "Amount": "10000000",
        "Memos": [
            {
                "Memo": {
                    "MemoType": "invoice".encode().hex().upper(),
                    "MemoData": "INV-2026-0001".encode().hex().upper(),
                }
            }
        ],
    }


def verify(transaction, headers=HEADERS):
    return client.post(
        "/verify-xrpl-transaction",
        json=transaction,
        headers=headers,
    )


def test_valid_transaction():
    response = verify(valid_transaction())
    assert response.status_code == 200
    assert response.json()["verified"] is True


def test_wrong_destination():
    transaction = valid_transaction()
    transaction["Destination"] = "rWrongSupplier"

    response = verify(transaction)
    assert response.json()["verified"] is False
    assert "Supplier destination mismatch" in response.json()["reasons"]


def test_wrong_amount():
    transaction = valid_transaction()
    transaction["Amount"] = "20000000"

    response = verify(transaction)
    assert response.json()["verified"] is False
    assert "Payment amount mismatch" in response.json()["reasons"]


def test_wrong_invoice_memo():
    transaction = valid_transaction()
    transaction["Memos"][0]["Memo"]["MemoData"] = "WRONG".encode().hex().upper()

    response = verify(transaction)
    assert response.json()["verified"] is False
    assert "Invoice memo mismatch" in response.json()["reasons"]


def test_wrong_transaction_type():
    transaction = valid_transaction()
    transaction["TransactionType"] = "AccountSet"

    response = verify(transaction)
    assert response.json()["verified"] is False


def test_wrong_treasury():
    transaction = valid_transaction()
    transaction["Account"] = "rWrongTreasury"

    response = verify(transaction)
    assert response.json()["verified"] is False


def test_unexpected_transaction_field():
    transaction = valid_transaction()
    transaction["SendMax"] = "20000000"

    response = verify(transaction)
    assert response.json()["verified"] is False
    assert "Unexpected transaction fields" in response.json()["reasons"]


def test_missing_authentication():
    response = verify(valid_transaction(), headers={})
    assert response.status_code == 401


def test_missing_wallet_configuration(monkeypatch):
    monkeypatch.delenv("HONEST_SUPPLIER_ADDRESS")

    response = verify(valid_transaction())
    assert response.json()["verified"] is False
    assert "XRPL wallet policy is not configured" in response.json()["reasons"]


def test_additional_memo_rejected():
    transaction = copy.deepcopy(valid_transaction())
    transaction["Memos"].append(
        {"Memo": {"MemoData": "4558545241"}}
    )

    response = verify(transaction)
    assert response.json()["verified"] is False
