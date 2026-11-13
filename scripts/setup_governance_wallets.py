
"""
Create CFO and Municipal Manager wallets on XRPL Testnet.

Preserves existing wallet credentials.
Never prints seeds or private keys.
"""

from pathlib import Path

from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
RPC_URL = "https://s.altnet.rippletest.net:51234"

ROLES = ["CFO", "MUNICIPAL_MANAGER"]


def main():
    if not ENV_PATH.exists():
        raise RuntimeError(
            ".env does not exist. Existing wallet setup is required."
        )

    existing = ENV_PATH.read_text(encoding="utf-8")

    # Fail closed if any governance wallet field already exists.
    # Never overwrite or partially replace existing credentials.
    for role in ROLES:
        for suffix in ("ADDRESS", "SEED"):
            key = f"{role}_{suffix}"
            if any(
                line.strip().startswith(f"{key}=")
                for line in existing.splitlines()
            ):
                raise RuntimeError(
                    f"{key} already exists. No changes made."
                )

    client = JsonRpcClient(RPC_URL)

    new_lines = []

    for role in ROLES:
        print(f"Creating {role} Testnet wallet...")
        wallet = generate_faucet_wallet(client)

        new_lines.append(f"{role}_ADDRESS={wallet.address}")
        new_lines.append(f"{role}_SEED={wallet.seed}")

        print(f"{role} wallet created successfully.")
        print("Address:", wallet.address)

    with ENV_PATH.open("a", encoding="utf-8") as file:
        file.write("\n" + "\n".join(new_lines) + "\n")

    print("\nGovernance wallets saved to .env.")
    print("Existing wallet credentials preserved.")


if __name__ == "__main__":
    main()
