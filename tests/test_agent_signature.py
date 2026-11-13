
"""Tests for agent multisignature verification."""

from xrpl.models.transactions import Payment
from xrpl.transaction import sign
from xrpl.wallet import Wallet

from rules_server.signature_verification import verify_agent_signature


def make_signed_transaction():
    agent = Wallet.create()

    transaction = Payment(
        account=Wallet.create().address,
        destination=Wallet.create().address,
        amount="1000000",
        fee="30",
        sequence=1,
        last_ledger_sequence=100000,
        signing_pub_key="",
    )

    signed = sign(transaction, agent, multisign=True)

    return signed.to_xrpl(), agent


def test_valid_agent_signature():
    transaction, agent = make_signed_transaction()

    valid, reason = verify_agent_signature(
        transaction,
        agent.address,
    )

    assert valid is True, reason


def test_modified_destination_rejected():
    transaction, agent = make_signed_transaction()
    transaction["Destination"] = Wallet.create().address

    valid, _ = verify_agent_signature(
        transaction,
        agent.address,
    )

    assert valid is False


def test_modified_amount_rejected():
    transaction, agent = make_signed_transaction()
    transaction["Amount"] = "9000000"

    valid, _ = verify_agent_signature(
        transaction,
        agent.address,
    )

    assert valid is False


def test_wrong_agent_rejected():
    transaction, _ = make_signed_transaction()
    unauthorized = Wallet.create()

    valid, _ = verify_agent_signature(
        transaction,
        unauthorized.address,
    )

    assert valid is False


def test_missing_signature_rejected():
    transaction, agent = make_signed_transaction()
    transaction["Signers"] = []

    valid, _ = verify_agent_signature(
        transaction,
        agent.address,
    )

    assert valid is False
