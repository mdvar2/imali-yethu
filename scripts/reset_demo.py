"""
Reset local demo state before presenting, so every scenario runs fresh.

    python scripts/reset_demo.py          # show what would be removed
    python scripts/reset_demo.py --yes    # remove it

Clears invoice reservations, the agent's decision log, the pause switch,
dashboard and policy audit logs, and any CFO policy changes (back to defaults).
Ledger transactions are permanent and are not touched.
"""
import argparse
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FILES = [
    "authorizations.db",     # invoice reservations (otherwise INV-2026-0001 stays "already reserved")
    "payments.jsonl",        # agent decision log
    "agent_control.json",    # pause switch
    "dashboard_audit.jsonl",
    "policy.json",           # CFO limits, back to defaults
    "policy_audit.jsonl",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="Actually delete the files")
    args = parser.parse_args()

    present = [DATA / name for name in FILES if (DATA / name).exists()]
    if not present:
        print("Demo state is already clean.")
        return
    for path in present:
        if args.yes:
            path.unlink()
        print(f"{'Removed' if args.yes else 'Would remove'}: data/{path.name}")
    if not args.yes:
        print("\nRe-run with --yes to remove. Restart the rules server afterwards.")


if __name__ == "__main__":
    main()
