
"""Imali Yethu autonomous XRPL Testnet agent.

Reads a demo invoice, prepares and signs an XRPL payment,
then requests independent Rules Server authorization.

Default mode: validation only, no payment submission.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import Memo, Payment
from xrpl.transaction import autofill, sign
from xrpl.utils import str_to_hex
from xrpl.wallet import Wallet

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config" / "agent.env"

INVOICE = {
    "invoice_number": "INV-2026-0001",
    "supplier_id": "SUP-001",
    "invoice_amount_zar": "15000.00",
    "testnet_amount_drops": "10000000",
}


def load_config():
    config = dotenv_values(CONFIG_FILE)

    required = (
        "XRPL_RPC_URL",
        "DEMO_TREASURY_ADDRESS",
        "AGENT_SEED",
        "HONEST_SUPPLIER_ADDRESS",
        "RULES_SERVER_API_KEY",
    )

    missing = [
        name for name in required
        if not config.get(name)
    ]

    if missing:
        raise RuntimeError(
            "Missing agent configuration: "
            + ", ".join(missing)
        )

    if config.get("RULES_SERVER_SEED"):
        raise RuntimeError(
            "Agent configuration must not contain "
            "the Rules Server private key"
        )

    return config


def prepare_payment(config):
    """Prepare a transaction and sign it as the agent."""

    wallet = Wallet.from_seed(config["AGENT_SEED"])

    client = JsonRpcClient(config["XRPL_RPC_URL"])

    payment = Payment(
        account=config["DEMO_TREASURY_ADDRESS"],
        destination=config["HONEST_SUPPLIER_ADDRESS"],
        amount=INVOICE["testnet_amount_drops"],
        fee="30",
        signing_pub_key="",
        memos=[
            Memo(
                memo_type=str_to_hex("invoice"),
                memo_data=str_to_hex(
                    INVOICE["invoice_number"]
                ),
            )
        ],
    )

    prepared = autofill(payment, client)

    # The signed transaction must contain an explicit fee,
    # sequence and ledger expiry.
    if (
        prepared.fee is None
        or prepared.sequence is None
        or prepared.last_ledger_sequence is None
    ):
        raise RuntimeError(
            "XRPL transaction preparation incomplete"
        )

    # Do not authorize an unexpectedly high fee.
    if int(prepared.fee) > 1000:
        raise RuntimeError(
            "Transaction fee exceeds safety limit"
        )

    signed = sign(
        prepared,
        wallet,
        multisign=True,
    )

    return signed.to_xrpl()


def send_proposal(transaction, config, execute=False):
    """Send a signed proposal to the local Rules Server."""

    endpoint = (
        "/cosign" if execute
        else "/validate-agent-payment"
    )

    url = "http://127.0.0.1:8000" + endpoint

    response = httpx.post(
        url,
        headers={
            "X-Service-Key":
                config["RULES_SERVER_API_KEY"]
        },
        json=transaction,
        timeout=30.0 if not execute else 120.0,
    )

    response.raise_for_status()

    return response.json()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Request actual Testnet execution",
    )

    args = parser.parse_args()

    config = load_config()

    wallet = Wallet.from_seed(
        config["AGENT_SEED"]
    )

    print("Imali Yethu Agent")
    print("Agent address:", wallet.address)
    print("Invoice:", INVOICE["invoice_number"])
    print("Supplier:", INVOICE["supplier_id"])
    print(
        "Testnet payment:",
        INVOICE["testnet_amount_drops"],
        "drops",
    )
    print(
        "Mode:",
        "EXECUTE" if args.execute
        else "VALIDATION ONLY",
    )

    if args.execute:
        print(
            "Live execution requested. "
            "The Rules Server must independently "
            "authorize the payment."
        )

    transaction = prepare_payment(config)

    print("Agent signature created.")

    result = send_proposal(
        transaction,
        config,
        execute=args.execute,
    )

    print(
        "Rules Server response:",
        json.dumps(result, indent=2),
    )

    if args.execute:
        tx_hash = result.get("transaction_hash")

        if result.get("validated") and tx_hash:
            print(
                "Explorer:",
                "https://testnet.xrpl.org/transactions/"
                + tx_hash,
            )
        elif result.get("reconciliation_required"):
            print(
                "Payment outcome uncertain. "
                "Do not retry automatically."
            )

    return 0 if (
        result.get("approved") is True
    ) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        RuntimeError,
        ValueError,
        httpx.HTTPError,
    ) as exc:
        print(
            "Agent execution failed:",
            type(exc).__name__,
            file=sys.stderr,
        )
        sys.exit(1)
