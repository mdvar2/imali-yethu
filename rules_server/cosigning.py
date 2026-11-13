
"""Independent XRPL cosigning for Imali Yethu.

Verifies the agent's signed payment before adding the
Rules Server signature.

This module does not submit transactions to XRPL.
"""

import os
from typing import Any

from xrpl.models.transactions import Transaction
from xrpl.transaction import multisign, sign
from xrpl.wallet import Wallet

from rules_server.signature_verification import verify_agent_signature
from rules_server.xrpl_verification import verify_xrpl_transaction


def validate_agent_payment(
    transaction: dict[str, Any],
) -> dict[str, Any]:
    """Validate an agent-signed payment without signing it."""

    expected_agent = os.getenv("AGENT_ADDRESS")
    expected_treasury = os.getenv("DEMO_TREASURY_ADDRESS")

    if not expected_agent or not expected_treasury:
        return {
            "approved": False,
            "reasons": ["Demo signing policy is not configured"],
        }

    valid_signature, reason = verify_agent_signature(
        transaction,
        expected_agent,
    )

    if not valid_signature:
        return {
            "approved": False,
            "reasons": [reason],
        }

    proposal = {
        key: value
        for key, value in transaction.items()
        if key != "Signers"
    }

    verification = verify_xrpl_transaction(
        proposal,
        expected_treasury=expected_treasury,
    )

    return {
        "approved": verification["verified"],
        "reasons": verification["reasons"],
    }


def prepare_cosigned_payment(
    transaction: dict[str, Any],
) -> dict[str, Any]:
    """Validate and multisign a payment without broadcasting it.

    IMPORTANT:
    The resulting transaction is sensitive authorization material.
    Do not log it or expose it through a public API.

    This function does not reserve an invoice or submit to XRPL.
    It must not be used as an independent settlement authorization
    until reservation and policy enforcement are integrated.
    """

    validation = validate_agent_payment(transaction)

    if not validation["approved"]:
        return {
            "approved": False,
            "reasons": validation["reasons"],
        }

    rules_seed = os.getenv("RULES_SERVER_SEED")

    if not rules_seed:
        return {
            "approved": False,
            "reasons": ["Rules Server signing key is not configured"],
        }

    try:
        rules_wallet = Wallet.from_seed(rules_seed)

        agent_address = os.getenv("AGENT_ADDRESS")

        if rules_wallet.address == agent_address:
            return {
                "approved": False,
                "reasons": [
                    "Agent and Rules Server signers must be different"
                ],
            }

        unsigned_dict = {
            key: value
            for key, value in transaction.items()
            if key != "Signers"
        }

        unsigned_payment = Transaction.from_xrpl(unsigned_dict)

        rules_signed = sign(
            unsigned_payment,
            rules_wallet,
            multisign=True,
        )

        agent_signed = Transaction.from_xrpl(transaction)

        combined = multisign(
            unsigned_payment,
            [agent_signed, rules_signed],
        )

        return {
            "approved": True,
            "reasons": [],
            "transaction": combined.to_xrpl(),
        }

    except (ValueError, TypeError, KeyError) as exc:
        return {
            "approved": False,
            "reasons": [
                f"Cosigning preparation failed: {type(exc).__name__}"
            ],
        }
