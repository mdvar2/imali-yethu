
"""Tests for transaction freshness verification."""

from unittest.mock import MagicMock

from rules_server.transaction_freshness import (
    verify_transaction_freshness,
)


TREASURY = "rTestTreasury"


def mock_client(sequence=100, ledger=200):
    client = MagicMock()

    account_response = MagicMock()
    account_response.is_successful.return_value = True
    account_response.result = {
        "account_data": {"Sequence": sequence}
    }

    ledger_response = MagicMock()
    ledger_response.is_successful.return_value = True
    ledger_response.result = {
        "ledger_current_index": ledger
    }

    client.request.side_effect = [
        account_response,
        ledger_response,
    ]

    return client


def payment(sequence=100, last_ledger=220):
    return {
        "Account": TREASURY,
        "Sequence": sequence,
        "LastLedgerSequence": last_ledger,
    }


def test_fresh_transaction_is_accepted():
    valid, reason = verify_transaction_freshness(
        mock_client(), payment(), TREASURY
    )
    assert valid is True


def test_wrong_sequence_is_rejected():
    valid, reason = verify_transaction_freshness(
        mock_client(), payment(sequence=99), TREASURY
    )
    assert valid is False
    assert reason == "Treasury sequence mismatch"


def test_expired_transaction_is_rejected():
    valid, reason = verify_transaction_freshness(
        mock_client(), payment(last_ledger=199), TREASURY
    )
    assert valid is False
    assert reason == "Transaction has expired"


def test_excessive_expiry_is_rejected():
    valid, reason = verify_transaction_freshness(
        mock_client(), payment(last_ledger=400), TREASURY
    )
    assert valid is False
    assert reason == "Transaction expiry is too far in the future"


def test_wrong_treasury_is_rejected():
    valid, reason = verify_transaction_freshness(
        mock_client(),
        {"Account": "rOther", "Sequence": 100, "LastLedgerSequence": 220},
        TREASURY,
    )
    assert valid is False
    assert reason == "Unexpected Treasury account"
