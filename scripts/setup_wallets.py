"""
Create the 5 Imali Yethu Testnet wallets from the XRPL faucet
and save their addresses + seeds to .env (which is git-ignored).

Run once:  python scripts/setup_wallets.py
"""
from pathlib import Path

from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet

RPC_URL = "https://s.altnet.rippletest.net:51234"
ROLES = ["TREASURY", "AGENT", "RULES_SERVER", "HONEST_SUPPLIER", "FAKE_SUPPLIER"]
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def main() -> None:
    if ENV_PATH.exists() and "TREASURY_SEED=s" in ENV_PATH.read_text():
        print(".env already has wallets. Delete it first if you want new ones.")
        return

    client = JsonRpcClient(RPC_URL)
    lines = [f"XRPL_RPC_URL={RPC_URL}"]

    for role in ROLES:
        print(f"Funding {role} wallet from the Testnet faucet...")
        wallet = generate_faucet_wallet(client)
        lines.append(f"{role}_ADDRESS={wallet.address}")
        lines.append(f"{role}_SEED={wallet.seed}")
        print(f"  {role}: {wallet.address}")
        print(f"  https://testnet.xrpl.org/accounts/{wallet.address}")

    lines.append("LLM_API_KEY=")
    ENV_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nSaved to {ENV_PATH}  (git-ignored - never commit it)")


if __name__ == "__main__":
    main()
