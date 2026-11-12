
import os
from typing import Any

INVOICE_NUMBER = "INV-2026-0001"
APPROVED_AMOUNT_DROPS = "10000000"  # 10 XRP


def verify_xrpl_transaction(
    transaction: dict[str, Any],
) -> dict[str, Any]:
    reasons = []

    treasury_address = os.getenv("TREASURY_ADDRESS")
    supplier_address = os.getenv("HONEST_SUPPLIER_ADDRESS")

    if not treasury_address or not supplier_address:
        return {
            "verified": False,
            "reasons": ["XRPL wallet policy is not configured"],
        }

    if transaction.get("TransactionType") != "Payment":
        reasons.append("Unsupported transaction type")

    if transaction.get("Account") != treasury_address:
        reasons.append("Treasury account mismatch")

    if transaction.get("Destination") != supplier_address:
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

    # Demo policy: only basic direct XRP payments are accepted.
    # Reject additional transaction fields that could change
    # payment behaviour or signing semantics.
    allowed_fields = {
        "TransactionType",
        "Account",
        "Destination",
        "Amount",
        "Memos",
    }

    unexpected_fields = set(transaction) - allowed_fields

    if unexpected_fields:
        reasons.append("Unexpected transaction fields")

    return {
        "verified": len(reasons) == 0,
        "invoice_number": INVOICE_NUMBER,
        "reasons": reasons,
    }
