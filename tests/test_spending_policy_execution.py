"""Regression tests for autonomous spending-policy enforcement."""

import os
from unittest.mock import patch

from rules_server.execution import execute_agent_payment


def test_over_limit_payment_never_reaches_submission():
    environment = {
        "ENABLE_TESTNET_PAYMENTS": "true",
        "XRPL_RPC_URL": "https://example.invalid",
        "DEMO_TREASURY_ADDRESS": "rTestTreasuryPlaceholder",
    }

    with (
        patch.dict(os.environ, environment),
        patch(
            "rules_server.execution.validate_agent_payment",
            return_value={"approved": True, "reasons": []},
        ),
        patch("rules_server.execution.JsonRpcClient"),
        patch("rules_server.execution.check_treasury_signers"),
        patch(
            "rules_server.execution.verify_transaction_freshness",
            return_value=(True, "Valid"),
        ) as freshness,
        patch(
            "rules_server.execution.check_spending_limit",
            return_value={
                "approved": False,
                "reasons": ["Payment exceeds the spending limit"],
            },
        ) as policy,
        patch("rules_server.execution.authorize_invoice") as reserve,
        patch("rules_server.execution.prepare_cosigned_payment") as cosign,
        patch("rules_server.execution.record_audit") as audit,
        patch("rules_server.execution.update_payment_status"),
        patch("rules_server.execution.SubmitOnly") as submit,
    ):
        result = execute_agent_payment({})

        assert result == {
            "approved": False,
            "reasons": ["Payment exceeds the spending limit"],
        }

        freshness.assert_called_once()
        policy.assert_called_once()
        reserve.assert_not_called()
        cosign.assert_not_called()
        submit.assert_not_called()
        audit.assert_called_once()
