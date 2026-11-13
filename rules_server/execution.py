
"""Controlled XRPL Testnet payment execution for Imali Yethu."""

import os
from typing import Any

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo
from xrpl.models.transactions import Transaction
from xrpl.transaction import submit_and_wait
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
APPROVED_INVOICE_AMOUNT = "15000.00"


def check_treasury_signers(client: JsonRpcClient) -> None:
    """Require the expected two-signer quorum on the ledger."""

    treasury = os.environ["DEMO_TREASURY_ADDRESS"]
    agent = os.environ["AGENT_ADDRESS"]
    rules_wallet = Wallet.from_seed(
        os.environ["RULES_SERVER_SEED"]
    )

    if agent == rules_wallet.address:
        raise ValueError("Agent and Rules Server must differ")

    response = client.request(
        AccountInfo(
            account=treasury,
            signer_lists=True,
            ledger_index="validated",
        )
    )

    if not response.is_successful():
        raise RuntimeError("Treasury account lookup failed")

    account_data = response.result.get("account_data", {})

    signer_lists = response.result.get("signer_lists")

    if signer_lists is None:
        signer_lists = account_data.get("signer_lists", [])

    if not isinstance(signer_lists, list):
        raise ValueError("Invalid Treasury signer-list response")

    if len(signer_lists) != 1:
        raise ValueError("Expected one Treasury signer list")

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
        rules_wallet.address: 2,
    }

    if actual != expected:
        raise ValueError("Treasury signer list mismatch")


def execute_agent_payment(
    transaction: dict[str, Any],
) -> dict[str, Any]:
    """Validate, reserve, cosign and submit one demo payment.

    A reserved invoice is never automatically retried.
    """

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
    except (ValueError, RuntimeError, KeyError) as exc:
        record_audit(
            INVOICE,
            "BLOCKED",
            f"Signer verification: {type(exc).__name__}",
        )
        return {
            "approved": False,
            "reasons": ["Treasury signer verification failed"],
        }

    # Reserve before creating the second signature.
    reservation = authorize_invoice(
        invoice_number=INVOICE,
        supplier_id=SUPPLIER_ID,
        amount=APPROVED_INVOICE_AMOUNT,
    )

    if not reservation["authorized"]:
        return {
            "approved": False,
            "reasons": [reservation["reason"]],
        }

    # From this point onward, failures require reconciliation.
    # Do not automatically release the reservation.
    try:
        prepared = prepare_cosigned_payment(transaction)

        if not prepared["approved"]:
            update_payment_status(INVOICE, "failed")
            return {
                "approved": False,
                "reasons": prepared["reasons"],
            }

        combined = Transaction.from_xrpl(
            prepared["transaction"]
        )

        update_payment_status(INVOICE, "submitting")

        response = submit_and_wait(
            combined,
            client,
            wallet=None,
            autofill=False,
            check_fee=True,
        )

        result = response.result
        tx_hash = result.get("hash") or result.get("tx_json", {}).get("hash")
        validated = result.get("validated") is True
        metadata = result.get("meta", {})
        engine_result = (
            metadata.get("TransactionResult")
            if isinstance(metadata, dict)
            else None
        )

        if (
            response.is_successful()
            and validated
            and engine_result == "tesSUCCESS"
        ):
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

        # An unexpected response is not proof that payment failed.
        record_audit(
            INVOICE,
            "RECONCILIATION_REQUIRED",
            "Ledger result not confirmed as tesSUCCESS",
            tx_hash,
        )

        return {
            "approved": False,
            "validated": False,
            "transaction_hash": tx_hash,
            "reconciliation_required": True,
        }

    except Exception as exc:
        # Do not expose exception details or signing material.
        record_audit(
            INVOICE,
            "RECONCILIATION_REQUIRED",
            f"Execution exception: {type(exc).__name__}",
        )
        return {
            "approved": False,
            "reconciliation_required": True,
            "reasons": [
                "Execution outcome uncertain; inspect the ledger"
            ],
        }
