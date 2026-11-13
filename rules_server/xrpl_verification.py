
"""Strict XRPL payment-intent validation for Imali Yethu.

Accepts basic payment proposals and prepared XRPL payments.

Security:
- Validates the Treasury, supplier, amount, and invoice.
- Rejects unexpected transaction fields.
- Restricts transaction fees and flags.
- Checks prepared multisignature transaction fields.

IMPORTANT:
This function does NOT verify cryptographic signatures.
Signature verification is handled separately.
"""

import os
from typing import Any


# ---------------------------------------------------------
# Approved demo payment policy
# ---------------------------------------------------------

INVOICE_NUMBER = "INV-2026-0001"

# 10 XRP = 10,000,000 drops
APPROVED_AMOUNT_DROPS = "10000000"

MAX_FEE_DROPS = 1000

ALLOWED_FIELDS = {
    "TransactionType",
    "Account",
    "Destination",
    "Amount",
    "Memos",
    "Fee",
    "Sequence",
    "LastLedgerSequence",
    "SigningPubKey",
    "Flags",
}


# ---------------------------------------------------------
# XRPL transaction validation
# ---------------------------------------------------------

def verify_xrpl_transaction(
    transaction: dict[str, Any],
    expected_treasury: str | None = None,
) -> dict[str, Any]:
    """Validate an XRPL payment against approved demo policy."""

    reasons: list[str] = []

    treasury = expected_treasury or os.getenv("TREASURY_ADDRESS")
    supplier = os.getenv("HONEST_SUPPLIER_ADDRESS")

    if not treasury or not supplier:
        return {
            "verified": False,
            "invoice_number": INVOICE_NUMBER,
            "reasons": ["XRPL wallet policy is not configured"],
        }

    # -----------------------------------------------------
    # 1. Transaction type
    # -----------------------------------------------------

    if transaction.get("TransactionType") != "Payment":
        reasons.append("Unsupported transaction type")

    # -----------------------------------------------------
    # 2. Treasury account
    # -----------------------------------------------------

    if transaction.get("Account") != treasury:
        reasons.append("Treasury account mismatch")

    # -----------------------------------------------------
    # 3. Approved supplier
    # -----------------------------------------------------

    if transaction.get("Destination") != supplier:
        reasons.append("Supplier destination mismatch")

    # -----------------------------------------------------
    # 4. Approved payment amount
    # -----------------------------------------------------

    if transaction.get("Amount") != APPROVED_AMOUNT_DROPS:
        reasons.append("Payment amount mismatch")


    # -----------------------------------------------------
    # 5. Invoice memo validation
    # -----------------------------------------------------

    expected_memo_type = "invoice".encode().hex().upper()
    expected_memo_data = INVOICE_NUMBER.encode().hex().upper()

    memos = transaction.get("Memos")

    if (
        not isinstance(memos, list)
        or len(memos) != 1
        or not isinstance(memos[0], dict)
        or not isinstance(memos[0].get("Memo"), dict)
    ):
        reasons.append("Invoice memo mismatch")

    else:
        actual_memo = memos[0]["Memo"]

        memo_type = actual_memo.get("MemoType")
        memo_data = actual_memo.get("MemoData")

        allowed_memo_fields = {
            "MemoType",
            "MemoData",
            "MemoFormat",
        }

        unexpected_memo_fields = (
            set(actual_memo) - allowed_memo_fields
        )

        if (
            not isinstance(memo_type, str)
            or not isinstance(memo_data, str)
            or memo_type.upper() != expected_memo_type
            or memo_data.upper() != expected_memo_data
            or unexpected_memo_fields
        ):
            reasons.append("Invoice memo mismatch")

    # -----------------------------------------------------
    # 6. Reject unexpected transaction fields
    # -----------------------------------------------------

    unexpected_fields = set(transaction) - ALLOWED_FIELDS

    if unexpected_fields:
        reasons.append("Unexpected transaction fields")

    # -----------------------------------------------------
    # 7. Transaction fee validation
    # -----------------------------------------------------

    if "Fee" in transaction:
        fee = transaction["Fee"]

        if (
            not isinstance(fee, str)
            or not fee.isdecimal()
            or not 0 < int(fee) <= MAX_FEE_DROPS
        ):
            reasons.append(
                "Invalid or excessive transaction fee"
            )

    # -----------------------------------------------------
    # 8. Sequence and ledger fields
    # -----------------------------------------------------

    for field in ("Sequence", "LastLedgerSequence"):

        if field in transaction:
            value = transaction[field]

            if (
                type(value) is not int
                or value <= 0
                or value > 0xFFFFFFFF
            ):
                reasons.append(f"Invalid {field}")

    # -----------------------------------------------------
    # 9. Transaction flags
    # -----------------------------------------------------

    if "Flags" in transaction:

        flags = transaction["Flags"]

        if type(flags) is not int or flags != 0:
            reasons.append(
                "Unsupported transaction flags"
            )

    # -----------------------------------------------------
    # 10. Multisignature SigningPubKey
    # -----------------------------------------------------

    if "SigningPubKey" in transaction:

        if transaction["SigningPubKey"] != "":
            reasons.append(
                "Multisignature SigningPubKey must be empty"
            )

    # -----------------------------------------------------
    # 11. Prepared transaction completeness
    # -----------------------------------------------------

    prepared_fields = {
        "Fee",
        "Sequence",
        "LastLedgerSequence",
        "SigningPubKey",
    }

    if any(
        field in transaction
        for field in prepared_fields
    ):
        if not prepared_fields.issubset(transaction):
            reasons.append(
                "Incomplete prepared transaction"
            )

    # -----------------------------------------------------
    # 12. Final verification result
    # -----------------------------------------------------

    return {
        "verified": not reasons,
        "invoice_number": INVOICE_NUMBER,
        "reasons": reasons,
    }
