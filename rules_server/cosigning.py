
"""Independent payment verification for Imali Yethu.

This stage validates an agent-signed transaction.
It does not cosign or submit payments yet.
"""

import os
from typing import Any

from rules_server.signature_verification import verify_agent_signature
from rules_server.xrpl_verification import verify_xrpl_transaction


def validate_agent_payment(
    transaction: dict[str, Any],
) -> dict[str, Any]:
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

    # Inspect the exact transaction signed by the agent.
    proposal = {
        key: value
        for key, value in transaction.items()
        if key != "Signers"
    }

    if proposal.get("Account") != expected_treasury:
        return {
            "approved": False,
            "reasons": ["Incorrect demo Treasury"],
        }

    # The legacy verifier uses TREASURY_ADDRESS.
    # Pass a separately configured expectation instead of
    # modifying process-wide environment variables.
    verification = verify_xrpl_transaction(
        proposal,
        expected_treasury=expected_treasury,
    )

    return {
        "approved": verification["verified"],
        "reasons": verification["reasons"],
    }
