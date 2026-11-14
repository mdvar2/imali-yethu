"""
One-time setup of the agent's Privy wallet.

1. Creates a Privy policy: only Payments to approved supplier wallets, max PRIVY_MAX_XRP.
2. Creates a Privy XRPL server wallet with that policy.
3. Sets the Privy wallet as the Treasury's regular key (signed with TREASURY_SEED),
   so the agent can sign for the Treasury but the CFO can revoke it on-ledger.
4. Saves PRIVY_WALLET_ID / ADDRESS / PUBLIC_KEY / POLICY_ID to .env.

Needs in .env: PRIVY_APP_ID, PRIVY_APP_SECRET (from dashboard.privy.io), plus the
wallets from setup_wallets.py.

Run once:  python scripts/setup_privy_wallet.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import SetRegularKey
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet

from agent.privy_wallet import PrivyWallet

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def main() -> None:
    load_dotenv(ENV_PATH)

    if os.getenv("PRIVY_WALLET_ID"):
        print(".env already has a Privy wallet. Remove the PRIVY_WALLET_* lines to create a new one.")
        return
    if not (os.getenv("PRIVY_APP_ID") and os.getenv("PRIVY_APP_SECRET")):
        sys.exit("Add PRIVY_APP_ID and PRIVY_APP_SECRET to .env first (dashboard.privy.io → App settings).")

    max_xrp = int(os.getenv("PRIVY_MAX_XRP", "20"))
    approved = [os.environ["HONEST_SUPPLIER_ADDRESS"]]
    privy = PrivyWallet()

    print(f"Creating Privy policy: Payments only to {approved}, max {max_xrp} XRP...")
    policy_id = privy.create_policy(approved, max_drops=max_xrp * 1_000_000)

    print("Creating Privy XRPL wallet for the agent...")
    wallet = privy.create_wallet(policy_id)
    print(f"  {wallet['address']}  (id {wallet['id']})")

    print("Setting it as the Treasury's regular key...")
    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
    treasury = Wallet.from_seed(os.environ["TREASURY_SEED"])
    result = submit_and_wait(
        SetRegularKey(account=treasury.address, regular_key=wallet["address"]), client, treasury
    )
    status = result.result["meta"]["TransactionResult"]
    print(f"  {status}: https://testnet.xrpl.org/transactions/{result.result['hash']}")
    if status != "tesSUCCESS":
        sys.exit("SetRegularKey failed; .env not updated.")

    with ENV_PATH.open("a", encoding="utf-8") as f:
        f.write(
            f"\n# Privy agent wallet (Treasury regular key)\n"
            f"PRIVY_POLICY_ID={policy_id}\n"
            f"PRIVY_WALLET_ID={wallet['id']}\n"
            f"PRIVY_WALLET_ADDRESS={wallet['address']}\n"
            f"PRIVY_WALLET_PUBLIC_KEY={wallet['public_key']}\n"
        )
    print(f"\nSaved to {ENV_PATH}. The agent now signs through Privy.")


if __name__ == "__main__":
    main()
