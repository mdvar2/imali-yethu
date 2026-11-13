
"""Integration tests for agent-signed payment validation."""

import pytest
from fastapi.testclient import TestClient
from xrpl.models.transactions import Memo, Payment
from xrpl.transaction import sign
from xrpl.utils import str_to_hex
from xrpl.wallet import Wallet

from rules_server.main import app
from rules_server.xrpl_verification import INVOICE_NUMBER

client = TestClient(app)


@pytest.fixture
def payment_environment(monkeypatch):
    """Create temporary test wallets and isolated policy settings."""

    agent = Wallet.create()
    treasury = Wallet.create()
    supplier = Wallet.create()

    monkeypatch.setenv("RULES_SERVER_API_KEY", "test-secret")
    monkeypatch.setenv("AGENT_ADDRESS", agent.address)
    monkeypatch.setenv("DEMO_TREASURY_ADDRESS", treasury.address)
    monkeypatch.setenv("HONEST_SUPPLIER_ADDRESS", supplier.address)

    return agent, treasury, supplier


def signed_payment(agent, treasury, supplier):
    """Create an agent-signed XRPL payment without submitting it."""

    payment = Payment(
        account=treasury.address,
        destination=supplier.address,
        amount="10000000",
        fee="30",
        sequence=1,
        last_ledger_sequence=90000000,
        signing_pub_key="",
        memos=[
            Memo(
                memo_type=str_to_hex("invoice"),
                memo_data=str_to_hex(INVOICE_NUMBER),
            )
        ],
    )

    return sign(
        payment,
        agent,
        multisign=True,
    ).to_xrpl()


def test_valid_signed_payment(payment_environment):
    agent, treasury, supplier = payment_environment

    transaction = signed_payment(agent, treasury, supplier)

    expected_memo = {
        "Memo": {
            "MemoType": str_to_hex("invoice"),
            "MemoData": str_to_hex(INVOICE_NUMBER),
        }
    }

    print("\nACTUAL MEMO:", repr(transaction.get("Memos")))
    print("EXPECTED MEMO:", repr([expected_memo]))

    response = client.post(
        "/validate-agent-payment",
        json=transaction,
        headers={"X-Service-Key": "test-secret"},
    )

    print("VALIDATION RESPONSE:", response.json())

    assert response.status_code == 200
    assert response.json()["approved"] is True, response.json()


def test_tampered_destination_rejected(payment_environment):
    agent, treasury, supplier = payment_environment

    transaction = signed_payment(agent, treasury, supplier)
    transaction["Destination"] = Wallet.create().address

    response = client.post(
        "/validate-agent-payment",
        json=transaction,
        headers={"X-Service-Key": "test-secret"},
    )

    assert response.status_code == 200
    assert response.json()["approved"] is False


def test_tampered_amount_rejected(payment_environment):
    agent, treasury, supplier = payment_environment

    transaction = signed_payment(agent, treasury, supplier)
    transaction["Amount"] = "50000000"

    response = client.post(
        "/validate-agent-payment",
        json=transaction,
        headers={"X-Service-Key": "test-secret"},
    )

    assert response.status_code == 200
    assert response.json()["approved"] is False


def test_missing_api_key_rejected(payment_environment):
    agent, treasury, supplier = payment_environment

    transaction = signed_payment(agent, treasury, supplier)

    response = client.post(
        "/validate-agent-payment",
        json=transaction,
    )

    assert response.status_code == 401
