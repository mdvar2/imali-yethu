"""Deterministic price check: no LLM involved."""
import json
from decimal import Decimal
from pathlib import Path

PRICES_PATH = Path(__file__).resolve().parent.parent / "data" / "prices.json"
MAX_MARKUP = Decimal("0.20")  # block anything >20% above market price


def load_prices() -> dict[str, Decimal]:
    raw = json.loads(PRICES_PATH.read_text())
    return {k: Decimal(str(v)) for k, v in raw.items() if not k.startswith("_")}


def check_prices(invoice, prices: dict[str, Decimal] | None = None) -> list[str]:
    """Return a list of reasons to block. Empty list means prices are fine."""
    prices = prices if prices is not None else load_prices()
    reasons = []
    computed_total = Decimal("0")

    for item in invoice.line_items:
        unit = Decimal(str(item.unit_price_zar))
        computed_total += unit * item.quantity

        market = prices.get(item.catalog_item or "")
        if market is None:
            reasons.append(f"No market price for '{item.description}'")
            continue

        limit = market * (1 + MAX_MARKUP)
        if unit > limit:
            pct = (unit / market - 1) * 100
            reasons.append(
                f"'{item.description}' costs R{unit:,.2f}, "
                f"{pct:.0f}% above market price R{market:,.2f}"
            )

    if computed_total != Decimal(str(invoice.total_zar)):
        reasons.append(
            f"Line items add up to R{computed_total:,.2f}, "
            f"but invoice total is R{Decimal(str(invoice.total_zar)):,.2f}"
        )

    return reasons
