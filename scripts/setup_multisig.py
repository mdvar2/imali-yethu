"""
Put the Treasury under multisig control on XRPL Testnet.

    python scripts/setup_multisig.py                          # show the plan, change nothing
    python scripts/setup_multisig.py --apply                  # add the signer list
    python scripts/setup_multisig.py --apply --disable-master # ...and disable the master key

Signer list (quorum 3):
    AI agent           weight 1
    Rules server       weight 2   (the agent never holds this key)
    CFO                weight 1   (emergency)
    Municipal Manager  weight 1   (emergency)

Normal payments need agent + rules server (1 + 2 = 3). No single party, and
not the agent alone, can move money. Two humans plus the agent can act in an
emergency, for example scripts/emergency_restore_master.py.

Run scripts/setup_governance_wallets.py first if CFO/MUNICIPAL_MANAGER wallets
are not in .env yet. Never prints seeds.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
QUORUM = 3
SIGNERS = [("AGENT_ADDRESS", "AI agent", 1), ("RULES_SERVER_ADDRESS", "Rules server", 2),
           ("CFO_ADDRESS", "CFO", 1), ("MUNICIPAL_MANAGER_ADDRESS", "Municipal Manager", 1)]


def set_env_value(key: str, value: str) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not line.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Submit the transactions (default: plan only)")
    parser.add_argument("--disable-master", action="store_true", help="Also disable the Treasury master key")
    args = parser.parse_args()
    load_dotenv(ENV_PATH)

    missing = [key for key, _, _ in SIGNERS if not os.getenv(key)]
    for key in ("TREASURY_ADDRESS", "TREASURY_SEED", "XRPL_RPC_URL"):
        if not os.getenv(key):
            missing.append(key)
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}. "
                 "Run scripts/setup_governance_wallets.py for the CFO and Municipal Manager wallets.")

    treasury = os.environ["TREASURY_ADDRESS"]
    print(f"Treasury: {treasury}\nQuorum:   {QUORUM}")
    for key, role, weight in SIGNERS:
        print(f"  {role:<18} weight {weight}  {os.environ[key]}")
    print(f"Master key: {'will be DISABLED' if args.disable_master else 'stays enabled (not fully enforced)'}")

    if not args.apply:
        print("\nPlan only. Re-run with --apply to submit.")
        return

    from xrpl.clients import JsonRpcClient
    from xrpl.models.transactions import AccountSet, AccountSetAsfFlag, SignerListSet
    from xrpl.models.transactions.signer_list_set import SignerEntry
    from xrpl.transaction import submit_and_wait
    from xrpl.wallet import Wallet

    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
    master = Wallet.from_seed(os.environ["TREASURY_SEED"])
    if master.classic_address != treasury:
        sys.exit("TREASURY_SEED does not belong to TREASURY_ADDRESS. No changes made.")

    signer_list = SignerListSet(
        account=treasury,
        signer_quorum=QUORUM,
        signer_entries=[SignerEntry(account=os.environ[key], signer_weight=weight) for key, _, weight in SIGNERS],
    )
    result = submit_and_wait(signer_list, client, master)
    code = result.result["meta"]["TransactionResult"]
    print(f"\nSignerListSet: {code}  https://testnet.xrpl.org/transactions/{result.result['hash']}")
    if code != "tesSUCCESS":
        sys.exit("Signer list was not set. Stopping.")

    if args.disable_master:
        disable = AccountSet(account=treasury, set_flag=AccountSetAsfFlag.ASF_DISABLE_MASTER)
        result = submit_and_wait(disable, client, master)
        code = result.result["meta"]["TransactionResult"]
        print(f"Disable master key: {code}  https://testnet.xrpl.org/transactions/{result.result['hash']}")
        if code != "tesSUCCESS":
            sys.exit("Master key is still enabled.")

    set_env_value("SIGNING_MODE", "multisig")
    print("\nSIGNING_MODE=multisig saved to .env. Restart the rules server and dashboard.")


if __name__ == "__main__":
    main()
