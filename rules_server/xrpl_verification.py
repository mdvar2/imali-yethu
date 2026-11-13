
"""Strict payment-intent validation for Imali Yethu.

Accepts basic payment proposals and prepared XRPL payments.
This function does NOT verify cryptographic signatures.
"""

import os
from typing import Any

INVOICE_NUMBER = "INV-2026-0001"
APPROVED_AMOUNT_DROPS = "10000000"  # 10 XRP demo settlement

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

MAX_FEE_DROPS = 1000


def verify_xrpl_transaction(
    transaction: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []

    treasury = os.getenv("TREASURY_ADDRESS")
    supplier = os.getenv("HONEST_SUPPLIER_ADDRESS")

    if not treasury or not supplier:
        return {
            "verified": False,
            "reasons": ["XRPL wallet policy is not configured"],
        }

    if transaction.get("TransactionType") != "Payment":
        reasons.append("Unsupported transaction type")

    if transaction.get("Account") != treasury:
        reasons.append("Treasury account mismatch")

    if transaction.get("Destination") != supplier:
        reasons.append("Supplier destination mismatch")

    if transaction.get("Amount") != APPROVED_AMOUNT_DROPS:
        reasons.append("Payment amount mismatch")

    expected_memo = {
        "Memo": {
            "MemoType": "invoice".encode().hex().upper(),
            "MemoData": INVOICE_NUMBER.encode().hex().upper(),
        }
    }

    if transaction.get("Memos") != [expected_memo]:
        reasons.append("Invoice memo mismatch")

    unexpected = set(transaction) - ALLOWED_FIELDS

    if unexpected:
        reasons.append("Unexpected transaction fields")

    if "Fee" in transaction:
        fee = transaction["Fee"]
        if (
            not isinstance(fee, str)
            or not fee.isdecimal()
            or not 0 < int(fee) <= MAX_FEE_DROPS
        ):
            reasons.append("Invalid or excessive transaction fee")

    for field in ("Sequence", "LastLedgerSequence"):
        if field in transaction:
            value = transaction[field]
            if (
                type(value) is not int
                or value <= 0
                or value > 0xFFFFFFFF
            ):
                reasons.append(f"Invalid {field}")

    if "Flags" in transaction:
        if type(transaction["Flags"]) is not int or transaction["Flags"] != 0:
            reasons.append("Unsupported transaction flags")

    if "SigningPubKey" in transaction:
        if transaction["SigningPubKey"] != "":
            reasons.append("Multisignature SigningPubKey must be empty")

    prepared_fields = {
        "Fee",
        "Sequence",
        "LastLedgerSequence",
        "SigningPubKey",
    }
    if any(field in transaction for field in prepared_fields):
        if not prepared_fields.issubset(transaction):
            reasons.append("Incomplete prepared transaction")

        if (
            type(transaction.get("Sequence")) is int
            and type(transaction.get("LastLedgerSequence")) is int
            and transaction["LastLedgerSequence"]
            <= transaction["Sequence"]
        ):
            # Sequence and ledger index are different concepts;
            # this is intentionally NOT used as a validity test.
            pass

    return {
        "verified": not reasons,
        "invoice_number": INVOICE_NUMBER,
        "reasons": reasons,
    }
