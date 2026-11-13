
"""Guarded XRPL Testnet execution for Imali Yethu."""

import hashlib
import os
import time
from typing import Any

from xrpl.clients import JsonRpcClient
from xrpl.core.binarycodec import encode
from xrpl.models.requests import AccountInfo, SubmitOnly, Tx
from xrpl.wallet import Wallet

from rules_server.authorization import (
    authorize_invoice,
    record_audit,
    update_payment_status,
)
from rules_server.cosigning import (
    prepare_cosigned_payment,
    validate_agent_payment,
)
from rules_server.transaction_freshness import (
    verify_transaction_freshness,
)

INVOICE = "INV-2026-0001"
SUPPLIER_ID = "SUP-001"
INVOICE_AMOUNT = "15000.00"
PAYMENT_AMOUNT_DROPS = "10000000"


def transaction_hash(blob: str) -> str:
    """Compute the XRPL transaction ID from its signed blob."""
    payload = bytes.fromhex("54584E00") + bytes.fromhex(blob)
    return hashlib.sha512(payload).digest()[:32].hex().upper()


def check_treasury_signers(client):
    """Verify the expected Treasury multisigning configuration."""
    treasury = os.environ["DEMO_TREASURY_ADDRESS"]
    agent = os.environ["AGENT_ADDRESS"]
    rules = Wallet.from_seed(os.environ["RULES_SERVER_SEED"])

    if len({treasury, agent, rules.address}) != 3:
        raise ValueError("Signing accounts must be distinct")

    response = client.request(
        AccountInfo(
            account=treasury,
            signer_lists=True,
            ledger_index="validated",
        )
    )

    if not response.is_successful():
        raise RuntimeError("Treasury lookup failed")

    result = response.result
    account = result.get("account_data", {})

    signer_lists = result.get("signer_lists")
    if signer_lists is None:
        signer_lists = account.get("signer_lists", [])

    if not isinstance(signer_lists, list) or len(signer_lists) != 1:
        raise ValueError("Unexpected signer-list response")

    signer_list = signer_lists[0]

    if signer_list.get("SignerQuorum") != 3:
        raise ValueError("Unexpected signer quorum")

    actual = {
        entry["SignerEntry"]["Account"]:
        entry["SignerEntry"]["SignerWeight"]
        for entry in signer_list.get("SignerEntries", [])
    }

    expected = {
        agent: 1,
        rules.address: 2,
    }

    if actual != expected:
        raise ValueError("Treasury signer list mismatch")


def submit_signed_blob(client, blob):
    """Submit the exact signed transaction without modifying it."""
    return client.request(
        SubmitOnly(
            tx_blob=blob,
            fail_hard=True,
        )
    )


def inspect_submission_response(response):
    """Classify the preliminary XRPL submission response.

    This is not a settlement decision. Even tesSUCCESS must
    be confirmed independently on the validated ledger.
    """
    result = getattr(response, "result", None)

    if not isinstance(result, dict):
        return "unknown", "Missing XRPL submission response"

    engine_result = result.get("engine_result")

    if not isinstance(engine_result, str) or not engine_result:
        return "unknown", "Missing XRPL engine result"

    if engine_result == "tesSUCCESS":
        return "provisional", engine_result

    if engine_result.startswith("ter"):
        return "provisional", engine_result

    if engine_result.startswith(("tec", "tem", "tef", "tel")):
        return "rejected", engine_result

    return "unknown", engine_result


def verify_invoice_memo(transaction):
    """Verify that the payment contains the expected invoice memo."""
    memos = transaction.get("Memos")

    if not isinstance(memos, list) or len(memos) != 1:
        raise ValueError("Missing or unexpected invoice memo")

    entry = memos[0]

    if not isinstance(entry, dict):
        raise ValueError("Invalid invoice memo structure")

    memo = entry.get("Memo")

    if not isinstance(memo, dict):
        raise ValueError("Invalid invoice memo structure")

    memo_data = memo.get("MemoData")

    if not isinstance(memo_data, str):
        raise ValueError("Missing invoice memo data")

    try:
        decoded = bytes.fromhex(memo_data).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Invalid invoice memo encoding") from None

    if decoded != INVOICE:
        raise ValueError("Invoice memo mismatch")


def check_validated_payment(client, tx_hash):
    """Verify the intended payment on the validated XRPL ledger."""
    response = client.request(
        Tx(transaction=tx_hash, binary=False)
    )

    if not response.is_successful():
        return None

    result = response.result

    if result.get("validated") is not True:
        return None

    transaction = result.get("tx_json", result)

    if not isinstance(transaction, dict):
        raise ValueError("Invalid ledger transaction response")

    actual_hash = result.get("hash") or transaction.get("hash")

    if actual_hash != tx_hash:
        raise ValueError("Ledger transaction hash mismatch")

    if transaction.get("TransactionType") != "Payment":
        raise ValueError("Unexpected transaction type")

    if transaction.get("Account") != os.environ["DEMO_TREASURY_ADDRESS"]:
        raise ValueError("Unexpected Treasury account")

    if transaction.get("Destination") != os.environ["HONEST_SUPPLIER_ADDRESS"]:
        raise ValueError("Unexpected payment destination")

    # XRPL may return Amount or DeliverMax.
    # If both are present, both must match the expected amount.
    amount = transaction.get("Amount")
    deliver_max = transaction.get("DeliverMax")

    if amount is None and deliver_max is None:
        raise ValueError("Missing payment amount")

    if amount is not None and amount != PAYMENT_AMOUNT_DROPS:
        raise ValueError("Unexpected payment amount")

    if deliver_max is not None and deliver_max != PAYMENT_AMOUNT_DROPS:
        raise ValueError("Unexpected payment amount")

    # Reject transactions that enable partial payments.
    flags = transaction.get("Flags", 0)

    if (
        not isinstance(flags, int)
        or isinstance(flags, bool)
        or flags & 0x00020000
    ):
        raise ValueError("Partial payment is not permitted")

    verify_invoice_memo(transaction)

    metadata = result.get("meta", {})

    if not isinstance(metadata, dict):
        raise ValueError("Invalid transaction metadata")

    outcome = metadata.get("TransactionResult")

    if not isinstance(outcome, str):
        raise ValueError("Missing ledger transaction result")

    # A successful transaction must deliver exactly 10 XRP.
    if outcome == "tesSUCCESS":
        if metadata.get("delivered_amount") != PAYMENT_AMOUNT_DROPS:
            raise ValueError("Unexpected delivered payment amount")

    return outcome


def execute_agent_payment(
    transaction: dict[str, Any],
) -> dict[str, Any]:
    """Validate, cosign, submit and reconcile an agent payment."""

    validation = validate_agent_payment(transaction)

    if not validation["approved"]:
        record_audit(
            INVOICE,
            "BLOCKED",
            "; ".join(validation["reasons"]),
        )
        return {
            "approved": False,
            "reasons": validation["reasons"],
        }

    if os.getenv("ENABLE_TESTNET_PAYMENTS") != "true":
        return {
            "approved": False,
            "reasons": ["Live Testnet execution is disabled"],
        }

    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])

    try:
        check_treasury_signers(client)
    except Exception:
        record_audit(
            INVOICE,
            "BLOCKED",
            "Treasury signer verification failed",
        )
        return {
            "approved": False,
            "reasons": ["Treasury signer verification failed"],
        }

    try:
        fresh, reason = verify_transaction_freshness(
            client,
            transaction,
            os.environ["DEMO_TREASURY_ADDRESS"],
        )
    except Exception:
        fresh = False
        reason = "Ledger freshness verification failed"

    if not fresh:
        record_audit(INVOICE, "BLOCKED", reason)
        return {
            "approved": False,
            "reasons": [reason],
        }

    reservation = authorize_invoice(
        invoice_number=INVOICE,
        supplier_id=SUPPLIER_ID,
        amount=INVOICE_AMOUNT,
    )

    if not reservation["authorized"]:
        return {
            "approved": False,
            "reasons": [reservation["reason"]],
        }

    tx_hash = None

    try:
        prepared = prepare_cosigned_payment(transaction)

        if not prepared["approved"]:
            update_payment_status(INVOICE, "failed")
            return {
                "approved": False,
                "reasons": prepared["reasons"],
            }

        blob = encode(prepared["transaction"])
        tx_hash = transaction_hash(blob)

        # Persist the transaction ID before network submission.
        update_payment_status(
            INVOICE,
            "submitting",
            tx_hash,
        )

        # Submit exactly once. Never automatically resubmit.
        response = submit_signed_blob(client, blob)

        submission_status, engine_result = (
            inspect_submission_response(response)
        )

        record_audit(
            INVOICE,
            "SUBMISSION_RESPONSE",
            f"{submission_status}: {engine_result}",
            tx_hash,
        )

        # The submission response is preliminary.
        # Only validated ledger evidence confirms settlement.
        for _ in range(12):
            outcome = check_validated_payment(client, tx_hash)

            if outcome == "tesSUCCESS":
                update_payment_status(
                    INVOICE,
                    "validated",
                    tx_hash,
                )
                return {
                    "approved": True,
                    "validated": True,
                    "transaction_hash": tx_hash,
                    "submission_result": engine_result,
                }

            if outcome is not None:
                record_audit(
                    INVOICE,
                    "LEDGER_REJECTED",
                    outcome,
                    tx_hash,
                )
                return {
                    "approved": False,
                    "validated": True,
                    "transaction_hash": tx_hash,
                    "ledger_result": outcome,
                    "submission_result": engine_result,
                }

            time.sleep(2)

        # Do not release the invoice reservation if the
        # final ledger outcome remains unknown.
        record_audit(
            INVOICE,
            "RECONCILIATION_REQUIRED",
            (
                "No validated ledger outcome; "
                f"submission result: {engine_result}"
            ),
            tx_hash,
        )

        return {
            "approved": False,
            "validated": False,
            "transaction_hash": tx_hash,
            "submission_result": engine_result,
            "reconciliation_required": True,
            "reasons": [
                "Ledger outcome unconfirmed; do not retry"
            ],
        }

    except Exception as exc:
        record_audit(
            INVOICE,
            "RECONCILIATION_REQUIRED",
            f"Execution exception: {type(exc).__name__}",
            tx_hash,
        )

        return {
            "approved": False,
            "transaction_hash": tx_hash,
            "reconciliation_required": True,
            "reasons": [
                "Execution outcome uncertain; do not retry"
            ],
        }
