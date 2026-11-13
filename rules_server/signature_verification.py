
"""Verify an XRPL multisignature from the authorized agent."""

from typing import Any

from xrpl.core.binarycodec import encode_for_multisigning
from xrpl.core.keypairs import derive_classic_address, is_valid_message


def verify_agent_signature(
    transaction: dict[str, Any],
    expected_agent_address: str,
) -> tuple[bool, str]:
    """Verify the authorized agent signed this exact transaction."""

    try:
        signers = transaction.get("Signers")

        if not isinstance(signers, list) or len(signers) != 1:
            return False, "Exactly one agent signature is required"

        signer_wrapper = signers[0]

        if not isinstance(signer_wrapper, dict):
            return False, "Invalid signer structure"

        signer = signer_wrapper.get("Signer")

        if not isinstance(signer, dict):
            return False, "Invalid signer structure"

        account = signer.get("Account")
        public_key = signer.get("SigningPubKey")
        signature = signer.get("TxnSignature")

        if account != expected_agent_address:
            return False, "Unauthorized agent signer"

        if not isinstance(public_key, str) or not public_key:
            return False, "Missing signer public key"

        if not isinstance(signature, str) or not signature:
            return False, "Missing signer signature"

        if derive_classic_address(public_key) != account:
            return False, "Signer public key does not match account"

        # The signing payload must not include the signature
        # envelope itself.
        unsigned = {
            key: value
            for key, value in transaction.items()
            if key not in {"Signers", "TxnSignature"}
        }

        if unsigned.get("SigningPubKey") != "":
            return False, "Invalid multisigning public key"

        signing_hex = encode_for_multisigning(
            unsigned,
            account,
        )

        valid = is_valid_message(
            bytes.fromhex(signing_hex),
            bytes.fromhex(signature),
            public_key,
        )

        if not valid:
            return False, "Invalid agent signature"

        return True, "Agent signature verified"

    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return False, f"Signature verification failed: {type(exc).__name__}"
