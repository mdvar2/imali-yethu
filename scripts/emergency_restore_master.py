"""
Emergency: re-enable the Treasury master key using the human signers.

    python scripts/emergency_restore_master.py           # plan only
    python scripts/emergency_restore_master.py --apply

Signed by CFO (1) + Municipal Manager (1) + AI agent (1) = quorum 3. This is
the "two humans must agree" path from the security model. It does not need
the rules server. After this, set SIGNING_MODE=master (or remove it) in .env.
"""
import argparse
import os
import sys

from dotenv import load_dotenv

SIGNER_SEEDS = ["CFO_SEED", "MUNICIPAL_MANAGER_SEED", "AGENT_SEED"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv()

    missing = [k for k in [*SIGNER_SEEDS, "TREASURY_ADDRESS", "XRPL_RPC_URL"] if not os.getenv(k)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")

    print(f"Re-enable master key on {os.environ['TREASURY_ADDRESS']}, signed by CFO + Municipal Manager + agent.")
    if not args.apply:
        print("Plan only. Re-run with --apply to submit.")
        return

    from xrpl.clients import JsonRpcClient
    from xrpl.models.transactions import AccountSet, AccountSetAsfFlag
    from xrpl.transaction import autofill, multisign, sign, submit_and_wait
    from xrpl.wallet import Wallet

    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
    tx = autofill(AccountSet(account=os.environ["TREASURY_ADDRESS"], clear_flag=AccountSetAsfFlag.ASF_DISABLE_MASTER),
                  client, signers_count=len(SIGNER_SEEDS))
    signed = [sign(tx, Wallet.from_seed(os.environ[k]), multisign=True) for k in SIGNER_SEEDS]
    result = submit_and_wait(multisign(tx, signed), client, autofill=False)
    print(f"{result.result['meta']['TransactionResult']}  "
          f"https://testnet.xrpl.org/transactions/{result.result['hash']}")


if __name__ == "__main__":
    main()
