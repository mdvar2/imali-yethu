
"""Tests for guarded XRPL Testnet execution."""

from unittest.mock import MagicMock, patch

from rules_server.execution import execute_agent_payment


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
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert "Invalid agent signature" in result["reasons"]
    audit.assert_called_once()
    reserve.assert_not_called()
    submit.assert_not_called()


def test_live_execution_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_TESTNET_PAYMENTS", raising=False)

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.authorize_invoice") as reserve,
        patch("rules_server.execution.submit_signed_blob") as submit,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert "disabled" in result["reasons"][0].lower()
    reserve.assert_not_called()
    submit.assert_not_called()


def test_duplicate_invoice_cannot_submit(monkeypatch):
    monkeypatch.setenv("ENABLE_TESTNET_PAYMENTS", "true")
    monkeypatch.setenv("XRPL_RPC_URL", "https://example.invalid")

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch("rules_server.execution.check_treasury_signers"),
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
        patch("rules_server.execution.record_audit"),
        patch("rules_server.execution.authorize_invoice") as reserve,
        patch("rules_server.execution.submit_signed_blob") as submit,
    ):
        result = execute_agent_payment({})

    assert result["approved"] is False
    assert "Treasury signer verification failed" in result["reasons"]
    reserve.assert_not_called()
    submit.assert_not_called()


def test_uncertain_submission_requires_reconciliation(monkeypatch):
    monkeypatch.setenv("ENABLE_TESTNET_PAYMENTS", "true")
    monkeypatch.setenv("XRPL_RPC_URL", "https://example.invalid")

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch("rules_server.execution.check_treasury_signers"),
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

    with (
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value=approved_validation(),
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch("rules_server.execution.check_treasury_signers"),
        patch(
            "rules_server.execution.authorize_invoice",
            return_value={"authorized": True, "reason": "Invoice reserved"},
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
        patch("rules_server.execution.submit_signed_blob", return_value=MagicMock()),
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
    assert any(
        call.args[1] == "validated"
        for call in status.call_args_list
    )
