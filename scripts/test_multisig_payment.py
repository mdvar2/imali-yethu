
"""Test a 1 XRP multisigned payment on XRPL Testnet.

Integration test only. Not yet an autonomous agent or
independent Rules Server enforcement.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo
from xrpl.models.transactions import Memo, Payment
from xrpl.transaction import autofill, multisign, sign, submit_and_wait
from xrpl.utils import str_to_hex, xrp_to_drops
from xrpl.wallet import Wallet

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

INVOICE = "INV-2026-MULTISIG-TEST-001"


def main() -> None:
    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])

    treasury = os.environ["DEMO_TREASURY_ADDRESS"]
    supplier = os.environ["HONEST_SUPPLIER_ADDRESS"]

    agent = Wallet.from_seed(os.environ["AGENT_SEED"])
    rules = Wallet.from_seed(os.environ["RULES_SERVER_SEED"])

    account = client.request(
        AccountInfo(
            account=treasury,
            ledger_index="validated",
            signer_lists=True,
        )
    )

    if not account.is_successful():
        raise RuntimeError("Treasury account lookup failed.")

    signer_lists = account.result.get("signer_lists", [])

    if len(signer_lists) != 1:
        raise RuntimeError("Expected exactly one signer list.")

    signer_list = signer_lists[0]

    actual = {
        entry["SignerEntry"]["Account"]:
        entry["SignerEntry"]["SignerWeight"]
        for entry in signer_list["SignerEntries"]
    }

    if signer_list["SignerQuorum"] != 3 or actual != {
        agent.address: 1,
        rules.address: 2,
    }:
        raise RuntimeError("Unexpected signer configuration.")

    transaction = Payment(
        account=treasury,
        destination=supplier,
        amount=xrp_to_drops(1),
        memos=[
            Memo(
                memo_type=str_to_hex("invoice"),
                memo_data=str_to_hex(INVOICE),
            )
        ],
    )

    prepared = autofill(
        transaction,
        client,
        signers_count=2,
    )

    print("Treasury:", treasury)
    print("Destination:", supplier)
    print("Amount: 1 XRP")
    print("Invoice:", INVOICE)
    print("Fee (drops):", prepared.fee)

    # This script holds both signer keys in one process.
    # It proves XRPL multisigning, NOT independent custody.
    agent_signed = sign(
        prepared,
        agent,
        multisign=True,
    )

    rules_signed = sign(
        prepared,
        rules,
        multisign=True,
    )

    combined = multisign(
        prepared,
        [agent_signed, rules_signed],
    )

    print("Submitting multisigned payment...")

    response = submit_and_wait(combined, client)

    result = response.result
    status = result.get("meta", {}).get("TransactionResult")

    if status != "tesSUCCESS":
        raise RuntimeError(f"Payment failed: {status}")

    tx_hash = result["hash"]

    print("\nSUCCESS: Multisigned payment validated.")
    print("Transaction hash:", tx_hash)
    print(
        "Explorer:",
        f"https://testnet.xrpl.org/transactions/{tx_hash}",
    )


if __name__ == "__main__":
    main()
