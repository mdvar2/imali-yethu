"""Registers the rules server trusts: approved invoices and supplier wallets.

The agent never supplies these values. Supplier wallets come from the
supplier register (addresses held in the server's environment), and
invoice amounts come from approved purchase orders.
"""
from __future__ import annotations

import json
import os
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INVOICES_PATH = DATA_DIR / "invoices.json"
SUPPLIERS_PATH = DATA_DIR / "suppliers.json"

# Demo conversion only. Production settlement would be in a rand stablecoin.
# Must match agent/xrpl_payments.py (a test checks this).
DEMO_ZAR_PER_XRP = Decimal("1500")


def load_invoices() -> dict[str, dict]:
    try:
        raw = json.loads(INVOICES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {
        number: {**entry, "amount": Decimal(str(entry["amount_zar"]))}
        for number, entry in raw.items()
        if not number.startswith("_")
    }


def supplier_wallet(supplier_id: str) -> str | None:
    try:
        suppliers = json.loads(SUPPLIERS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    entry = suppliers.get(supplier_id)
    if not isinstance(entry, dict):
        return None
    return os.getenv(entry.get("wallet_env", "")) or None


def zar_to_drops(amount_zar: Decimal) -> str:
    drops = (amount_zar / DEMO_ZAR_PER_XRP * 1_000_000).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return str(drops)
