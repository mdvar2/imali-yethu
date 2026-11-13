
"""Create an isolated Imali Yethu multisignature Testnet Treasury.

Does not modify the existing Treasury or disable its master key.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo
from xrpl.models.transactions import SignerEntry, SignerListSet
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet, generate_faucet_wallet

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH)

RPC_URL = os.getenv(
    "XRPL_RPC_URL",
    "https://s.altnet.rippletest.net:51234",
)


def append_environment(values: dict[str, str]) -> None:
    """Add new keys without replacing existing environment data."""
    existing = ENV_PATH.read_text() if ENV_PATH.exists() else ""

    for name in values:
        if any(
            line.strip().startswith(f"{name}=")
            for line in existing.splitlines()
        ):
            raise RuntimeError(
                f"{name} already exists. Refusing to overwrite it."
            )

    with ENV_PATH.open("a", encoding="utf-8") as file:
        if existing and not existing.endswith("\n"):
            file.write("\n")

        for name, value in values.items():
            file.write(f"{name}={value}\n")


def main() -> None:
    if not ENV_PATH.exists():
        raise RuntimeError("Missing .env file.")

    existing = ENV_PATH.read_text(encoding="utf-8")
    if "DEMO_TREASURY_SEED=" in existing:
        raise RuntimeError(
            "Demo Treasury already exists. Refusing to recreate it."
        )

    agent_seed = os.getenv("AGENT_SEED")
    rules_seed = os.getenv("RULES_SERVER_SEED")

    if not agent_seed or not rules_seed:
        raise RuntimeError("Agent and Rules Server seeds are required.")

    agent = Wallet.from_seed(agent_seed)
    rules = Wallet.from_seed(rules_seed)

    if agent.address == rules.address:
        raise RuntimeError("Agent and Rules Server must be distinct.")

    client = JsonRpcClient(RPC_URL)

    print("Creating a fresh XRPL Testnet Treasury...")
    treasury = generate_faucet_wallet(client)

    # Save recovery information immediately after creation.
    append_environment(
        {
            "DEMO_TREASURY_ADDRESS": treasury.address,
            "DEMO_TREASURY_SEED": treasury.seed,
        }
    )

    print(f"Demo Treasury: {treasury.address}")

    transaction = SignerListSet(
        account=treasury.address,
        signer_quorum=3,
        signer_entries=[
            SignerEntry(
                account=agent.address,
                signer_weight=1,
            ),
            SignerEntry(
                account=rules.address,
                signer_weight=2,
            ),
        ],
    )

    print("Configuring multisignature authorization...")

    response = submit_and_wait(
        transaction,
        client,
        treasury,
    )

    result = response.result
    status = result.get("meta", {}).get("TransactionResult")

    if status != "tesSUCCESS":
        raise RuntimeError(
            f"Signer list configuration failed: {status}"
        )

    print("Signer list transaction succeeded.")
    print(
        "Explorer:",
        f"https://testnet.xrpl.org/transactions/{result['hash']}",
    )

    account_response = client.request(
        AccountInfo(
            account=treasury.address,
            ledger_index="validated",
            signer_lists=True,
        )
    )

    signer_lists = account_response.result.get(
        "account_data", {}
    ).get("signer_lists", [])

    if not signer_lists:
        raise RuntimeError("No signer list found on the ledger.")

    signer_list = signer_lists[0]
    entries = {
        item["SignerEntry"]["Account"]:
        item["SignerEntry"]["SignerWeight"]
        for item in signer_list["SignerEntries"]
    }

    expected = {
        agent.address: 1,
        rules.address: 2,
    }

    if (
        signer_list["SignerQuorum"] != 3
        or entries != expected
    ):
        raise RuntimeError(
            "Ledger signer configuration does not match policy."
        )

    print("Verified quorum: 3")
    print("Verified Agent weight: 1")
    print("Verified Rules Server weight: 2")
    print("Master key remains enabled pending recovery testing.")
    print("Demo Treasury configuration complete.")


if __name__ == "__main__":
    main()
