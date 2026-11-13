
"""Offline tests for XRPL multisignature preparation."""

import pytest
from xrpl.models.transactions import Memo, Payment
from xrpl.transaction import sign
from xrpl.utils import str_to_hex
from xrpl.wallet import Wallet

from rules_server.cosigning import prepare_cosigned_payment


@pytest.fixture
def wallets(monkeypatch):
    agent = Wallet.create()
    rules = Wallet.create()
    treasury = Wallet.create()
    supplier = Wallet.create()

    monkeypatch.setenv("AGENT_ADDRESS", agent.address)
    monkeypatch.setenv("RULES_SERVER_SEED", rules.seed)
    monkeypatch.setenv("DEMO_TREASURY_ADDRESS", treasury.address)
    monkeypatch.setenv("HONEST_SUPPLIER_ADDRESS", supplier.address)

    return agent, rules, treasury, supplier


def create_agent_payment(agent, treasury, supplier):
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
                memo_data=str_to_hex("INV-2026-0001"),
            )
        ],
    )

    return sign(payment, agent, multisign=True).to_xrpl()


def test_cosigning_produces_two_signatures(wallets):
    agent, rules, treasury, supplier = wallets

    transaction = create_agent_payment(
        agent, treasury, supplier
    )

    result = prepare_cosigned_payment(transaction)

    assert result["approved"] is True, result
    assert len(result["transaction"]["Signers"]) == 2

    signer_addresses = {
        entry["Signer"]["Account"]
        for entry in result["transaction"]["Signers"]
    }

    assert signer_addresses == {
        agent.address,
        rules.address,
    }


def test_cosigning_rejects_tampered_payment(wallets):
    agent, rules, treasury, supplier = wallets

    transaction = create_agent_payment(
        agent, treasury, supplier
    )

    transaction["Amount"] = "50000000"

    result = prepare_cosigned_payment(transaction)

    assert result["approved"] is False
    assert "transaction" not in result


def test_cosigning_rejects_missing_rules_key(
    wallets,
    monkeypatch,
):
    agent, rules, treasury, supplier = wallets

    transaction = create_agent_payment(
        agent, treasury, supplier
    )

    monkeypatch.delenv("RULES_SERVER_SEED")

    result = prepare_cosigned_payment(transaction)

    assert result["approved"] is False
    assert "transaction" not in result
