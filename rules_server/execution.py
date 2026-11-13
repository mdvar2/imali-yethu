
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

INVOICE = "INV-2026-0001"
SUPPLIER_ID = "SUP-001"
INVOICE_AMOUNT = "15000.00"


def transaction_hash(blob: str) -> str:
    """Compute the XRPL transaction ID from its signed blob."""
    payload = bytes.fromhex("54584E00") + bytes.fromhex(blob)
    return hashlib.sha512(payload).digest()[:32].hex().upper()


def check_treasury_signers(client):
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
    """Submit the exact signed transaction blob."""


    return client.request(
        SubmitOnly(
            tx_blob=blob,
            fail_hard=True,
        )
    )


def check_validated_payment(client, tx_hash):
    """Check whether the transaction is validated on-ledger."""
    response = client.request(
        Tx(transaction=tx_hash, binary=False)
    )

    if not response.is_successful():
        return None

    result = response.result

    if result.get("validated") is not True:
        return None

    meta = result.get("meta", {})
    outcome = (
        meta.get("TransactionResult")
        if isinstance(meta, dict)
        else None
    )

    return outcome


def execute_agent_payment(
    transaction: dict[str, Any],
) -> dict[str, Any]:
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

        update_payment_status(
            INVOICE,
            "submitting",
            tx_hash,
        )

        response = submit_signed_blob(client, blob)

        # A submission response alone is not proof of settlement.
        # Poll the validated ledger for a bounded period.
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
                }

            time.sleep(2)

        record_audit(
            INVOICE,
            "RECONCILIATION_REQUIRED",
            "Ledger confirmation timed out",
            tx_hash,
        )

        return {
            "approved": False,
            "validated": False,
            "transaction_hash": tx_hash,
            "reconciliation_required": True,
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
