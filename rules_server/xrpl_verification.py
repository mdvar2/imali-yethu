"""Checks an XRPL transaction against the invoice register before approval or co-signing."""
import os
from typing import Any

from rules_server.registers import load_invoices, supplier_wallet, zar_to_drops

INVOICE_MEMO_TYPE = "invoice".encode().hex().upper()

# Fields allowed in the agent's unsigned payment proposal.
BASE_FIELDS = {"TransactionType", "Account", "Destination", "Amount", "Memos"}
# Extra fields xrpl autofill adds; only accepted on the co-signing path.
AUTOFILL_FIELDS = {"Fee", "Sequence", "LastLedgerSequence", "SigningPubKey", "Flags", "NetworkID"}
# A multisigned payment costs base fee x (1 + signers): about 36 drops on Testnet.
# Anything far above that would quietly drain the Treasury through fees.
MAX_FEE_DROPS = 1000


def _invoice_from_memos(memos: Any) -> str | None:
    """The invoice number, if the transaction carries exactly one invoice memo."""
    if not isinstance(memos, list) or len(memos) != 1:
        return None
    memo = memos[0].get("Memo") if isinstance(memos[0], dict) else None
    if not isinstance(memo, dict) or set(memo) != {"MemoType", "MemoData"}:
        return None
    if str(memo["MemoType"]).upper() != INVOICE_MEMO_TYPE:
        return None
    try:
        return bytes.fromhex(memo["MemoData"]).decode("utf-8")
    except (ValueError, TypeError):
        return None


def verify_xrpl_transaction(transaction: dict[str, Any], *, autofilled: bool = False) -> dict[str, Any]:
    reasons = []
    treasury_address = os.getenv("TREASURY_ADDRESS")

    invoice_number = _invoice_from_memos(transaction.get("Memos"))
    invoice = load_invoices().get(invoice_number or "")
    expected_destination = supplier_wallet(invoice["supplier_id"]) if invoice else None

    if not treasury_address or (invoice and not expected_destination):
        return {"verified": False, "invoice_number": invoice_number,
                "reasons": ["XRPL wallet policy is not configured"]}

    if transaction.get("TransactionType") != "Payment":
        reasons.append("Unsupported transaction type")

    if transaction.get("Account") != treasury_address:
        reasons.append("Treasury account mismatch")

    if invoice is None:
        reasons.append("Invoice memo mismatch")
    else:
        if transaction.get("Destination") != expected_destination:
            reasons.append("Supplier destination mismatch")
        if transaction.get("Amount") != zar_to_drops(invoice["amount"]):
            reasons.append("Payment amount mismatch")

    allowed = BASE_FIELDS | (AUTOFILL_FIELDS if autofilled else set())
    if set(transaction) - allowed:
        reasons.append("Unexpected transaction fields")

    if autofilled:
        if transaction.get("SigningPubKey", "") != "":
            reasons.append("Transaction must be multisigned (empty SigningPubKey)")
        if transaction.get("Flags", 0) not in (0, "0"):
            reasons.append("Payment flags are not allowed")  # blocks partial payments
        try:
            if int(transaction.get("Fee", "0")) > MAX_FEE_DROPS:
                reasons.append("Transaction fee is too high")
        except (TypeError, ValueError):
            reasons.append("Transaction fee is invalid")
        if "LastLedgerSequence" not in transaction:
            reasons.append("Transaction must expire (LastLedgerSequence missing)")

    return {
        "verified": len(reasons) == 0,
        "invoice_number": invoice_number,
        "reasons": reasons,
    }
