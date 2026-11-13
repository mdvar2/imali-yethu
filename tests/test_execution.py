"""Tests for guarded XRPL Testnet execution."""

from unittest.mock import MagicMock, patch

import pytest

from rules_server.execution import (
    check_validated_payment,
    execute_agent_payment,
    verify_invoice_memo,
)


def approved_validation():
    return {"approved": True, "reasons": []}


def test_invalid_agent_payment_is_blocked():
    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value={
                "approved": False,
                "reasons": ["Invalid agent signature"],
            },
        ),
        patch("rules_server.execution.record_audit") as audit,
        patch("rules_server.execution.authorize_invoice") as reserve,
        patch("rules_server.execution.submit_signed_blob") as submit,
        patch(
            "rules_server.execution.verify_transaction_freshness"
        ) as freshness,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert "Invalid agent signature" in result["reasons"]
    audit.assert_called_once()
    reserve.assert_not_called()
    submit.assert_not_called()
    freshness.assert_not_called()


def test_live_execution_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_TESTNET_PAYMENTS", raising=False)

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.authorize_invoice") as reserve,
        patch("rules_server.execution.submit_signed_blob") as submit,
        patch(
            "rules_server.execution.verify_transaction_freshness"
        ) as freshness,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert "disabled" in result["reasons"][0].lower()
    reserve.assert_not_called()
    submit.assert_not_called()
    freshness.assert_not_called()


def test_duplicate_invoice_cannot_submit(monkeypatch):
    monkeypatch.setenv("ENABLE_TESTNET_PAYMENTS", "true")
    monkeypatch.setenv("XRPL_RPC_URL", "https://example.invalid")
    monkeypatch.setenv("DEMO_TREASURY_ADDRESS", "rTestTreasury")

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch("rules_server.execution.check_treasury_signers"),
        patch(
            "rules_server.execution.verify_transaction_freshness",
            return_value=(True, "Transaction is fresh"),
        ) as freshness,
        patch(
            "rules_server.execution.authorize_invoice",
            return_value={
                "authorized": False,
                "reason": "Invoice already reserved or authorized",
            },
        ),
        patch("rules_server.execution.submit_signed_blob") as submit,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert "already reserved" in result["reasons"][0]
    freshness.assert_called_once()
    submit.assert_not_called()


def test_signer_mismatch_blocks_before_reservation(monkeypatch):
    monkeypatch.setenv("ENABLE_TESTNET_PAYMENTS", "true")
    monkeypatch.setenv("XRPL_RPC_URL", "https://example.invalid")

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch(
            "rules_server.execution.check_treasury_signers",
            side_effect=ValueError("Signer list mismatch"),
        ),
        patch(
            "rules_server.execution.verify_transaction_freshness"
        ) as freshness,
        patch("rules_server.execution.record_audit"),
        patch("rules_server.execution.authorize_invoice") as reserve,
        patch("rules_server.execution.submit_signed_blob") as submit,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert "Treasury signer verification failed" in result["reasons"]
    freshness.assert_not_called()
    reserve.assert_not_called()
    submit.assert_not_called()


def test_uncertain_submission_requires_reconciliation(monkeypatch):
    monkeypatch.setenv("ENABLE_TESTNET_PAYMENTS", "true")
    monkeypatch.setenv("XRPL_RPC_URL", "https://example.invalid")
    monkeypatch.setenv("DEMO_TREASURY_ADDRESS", "rTestTreasury")

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch("rules_server.execution.check_treasury_signers"),
        patch(
            "rules_server.execution.verify_transaction_freshness",
            return_value=(True, "Transaction is fresh"),
        ),
        patch(
            "rules_server.execution.authorize_invoice",
            return_value={
                "authorized": True,
                "reason": "Invoice reserved",
            },
        ),
        patch(
            "rules_server.execution.prepare_cosigned_payment",
            return_value={
                "approved": True,
                "reasons": [],
                "transaction": {"TransactionType": "Payment"},
            },
        ),
        patch(
            "rules_server.execution.encode",
            return_value="DEADBEEF",
        ),
        patch(
            "rules_server.execution.submit_signed_blob",
            side_effect=TimeoutError("Simulated timeout"),
        ),
        patch("rules_server.execution.update_payment_status") as status,
        patch("rules_server.execution.record_audit") as audit,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert result["reconciliation_required"] is True
    assert result["transaction_hash"]
    status.assert_called()
    audit.assert_called()


def test_successful_validated_payment(monkeypatch):
    monkeypatch.setenv("ENABLE_TESTNET_PAYMENTS", "true")
    monkeypatch.setenv("XRPL_RPC_URL", "https://example.invalid")
    monkeypatch.setenv("DEMO_TREASURY_ADDRESS", "rTestTreasury")

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch("rules_server.execution.check_treasury_signers"),
        patch(
            "rules_server.execution.verify_transaction_freshness",
            return_value=(True, "Transaction is fresh"),
        ) as freshness,
        patch(
            "rules_server.execution.authorize_invoice",
            return_value={
                "authorized": True,
                "reason": "Invoice reserved",
            },
        ),
        patch(
            "rules_server.execution.prepare_cosigned_payment",
            return_value={
                "approved": True,
                "reasons": [],
                "transaction": {"TransactionType": "Payment"},
            },
        ),
        patch("rules_server.execution.encode", return_value="DEADBEEF"),
        patch(
            "rules_server.execution.submit_signed_blob",
            return_value=MagicMock(),
        ) as submit,
        patch(
            "rules_server.execution.check_validated_payment",
            return_value="tesSUCCESS",
        ),
        patch("rules_server.execution.update_payment_status") as status,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is True
    assert result["validated"] is True
    assert result["transaction_hash"]

    freshness.assert_called_once()
    submit.assert_called_once()

    assert any(
        call.args[1] == "validated"
        for call in status.call_args_list
    )


def test_expired_payment_is_blocked_before_reservation(monkeypatch):
    monkeypatch.setenv("ENABLE_TESTNET_PAYMENTS", "true")
    monkeypatch.setenv("XRPL_RPC_URL", "https://example.invalid")
    monkeypatch.setenv("DEMO_TREASURY_ADDRESS", "rTestTreasury")

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch("rules_server.execution.check_treasury_signers"),
        patch(
            "rules_server.execution.verify_transaction_freshness",
            return_value=(False, "Transaction has expired"),
        ) as freshness,
        patch("rules_server.execution.record_audit") as audit,
        patch("rules_server.execution.authorize_invoice") as reserve,
        patch("rules_server.execution.submit_signed_blob") as submit,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert result["reasons"] == ["Transaction has expired"]

    freshness.assert_called_once()
    audit.assert_called_once()
    reserve.assert_not_called()
    submit.assert_not_called()


# ---------------------------------------------------------
# Validated XRPL ledger verification tests
# ---------------------------------------------------------


def ledger_response(
    tx_hash="ABC123",
    treasury="rTestTreasury",
    supplier="rTestSupplier",
    amount="10000000",
    validated=True,
    outcome="tesSUCCESS",
):
    response = MagicMock()
    response.is_successful.return_value = True
    response.result = {
        "validated": validated,
        "hash": tx_hash,
        "tx_json": {
            "TransactionType": "Payment",
            "Account": treasury,
            "Destination": supplier,
            "Amount": amount,
            "Memos": [
                {
                    "Memo": {
                        "MemoData": "494E562D323032362D30303031",
                    }
                }
            ],
        },
        "meta": {
            "TransactionResult": outcome,
        },
    }
    return response


def configure_ledger_environment(monkeypatch):
    monkeypatch.setenv("DEMO_TREASURY_ADDRESS", "rTestTreasury")
    monkeypatch.setenv("HONEST_SUPPLIER_ADDRESS", "rTestSupplier")


def test_validated_ledger_payment_is_accepted(monkeypatch):
    configure_ledger_environment(monkeypatch)

    client = MagicMock()
    client.request.return_value = ledger_response()

    result = check_validated_payment(client, "ABC123")

    assert result == "tesSUCCESS"
    client.request.assert_called_once()


def test_unvalidated_ledger_payment_is_not_accepted(monkeypatch):
    configure_ledger_environment(monkeypatch)

    client = MagicMock()
    client.request.return_value = ledger_response(validated=False)

    result = check_validated_payment(client, "ABC123")

    assert result is None


def test_wrong_payment_destination_is_rejected(monkeypatch):
    configure_ledger_environment(monkeypatch)

    client = MagicMock()
    client.request.return_value = ledger_response(
        supplier="rWrongSupplier"
    )

    with pytest.raises(ValueError, match="destination"):
        check_validated_payment(client, "ABC123")


def test_wrong_payment_amount_is_rejected(monkeypatch):
    configure_ledger_environment(monkeypatch)

    client = MagicMock()
    client.request.return_value = ledger_response(
        amount="20000000"
    )

    with pytest.raises(ValueError, match="amount"):
        check_validated_payment(client, "ABC123")


def test_wrong_transaction_hash_is_rejected(monkeypatch):
    configure_ledger_environment(monkeypatch)

    client = MagicMock()
    client.request.return_value = ledger_response(
        tx_hash="WRONG_HASH"
    )

    with pytest.raises(ValueError, match="hash"):
        check_validated_payment(client, "ABC123")


def test_failed_ledger_result_is_not_success(monkeypatch):
    configure_ledger_environment(monkeypatch)

    client = MagicMock()
    client.request.return_value = ledger_response(
        outcome="tecUNFUNDED_PAYMENT"
    )

    result = check_validated_payment(client, "ABC123")

    assert result == "tecUNFUNDED_PAYMENT"
    assert result != "tesSUCCESS"


def test_correct_invoice_memo_is_accepted():
    transaction = {
        "Memos": [{"Memo": {"MemoData": "494E562D323032362D30303031"}}]
    }
    assert verify_invoice_memo(transaction) is None


def test_missing_invoice_memo_is_rejected():
    with pytest.raises(ValueError, match="memo"):
        verify_invoice_memo({})


def test_wrong_invoice_memo_is_rejected():
    transaction = {
        "Memos": [{"Memo": {"MemoData": "494E562D323032362D39393939"}}]
    }
    with pytest.raises(ValueError, match="Invoice memo mismatch"):
        verify_invoice_memo(transaction)


def test_invalid_invoice_memo_encoding_is_rejected():
    transaction = {"Memos": [{"Memo": {"MemoData": "NOT_HEX"}}]}
    with pytest.raises(ValueError, match="encoding"):
        verify_invoice_memo(transaction)


def test_multiple_invoice_memos_are_rejected():
    transaction = {
        "Memos": [
            {"Memo": {"MemoData": "494E562D323032362D30303031"}},
            {"Memo": {"MemoData": "494E562D323032362D30303031"}},
        ]
    }
    with pytest.raises(ValueError, match="memo"):
        verify_invoice_memo(transaction)
