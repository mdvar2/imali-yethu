"""Data and formatting helpers for the Imali Yethu dashboard.

Pure Python (no Streamlit) so it can be unit tested.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_PATH = DATA_DIR / "payments.jsonl"
CONTROL_PATH = DATA_DIR / "agent_control.json"
AUDIT_PATH = DATA_DIR / "dashboard_audit.jsonl"
SUPPLIERS_PATH = DATA_DIR / "suppliers.json"
PRICES_PATH = DATA_DIR / "prices.json"

SAST = timezone(timedelta(hours=2), "SAST")  # South Africa has no daylight saving
EXPLORER_TX = "https://testnet.xrpl.org/transactions/"
BLOCKED = {"blocked_by_agent", "blocked_by_rules_server"}


# ------------------------------------------------------------------ statuses
@dataclass(frozen=True)
class Status:
    label: str
    tone: str  # ok | bad | warn | info | muted
    description: str


STATUSES = {
    "paid": Status("Paid", "ok", "Passed every check and settled on the XRP Ledger."),
    "approved_dry_run": Status(
        "Approved, not sent", "info",
        "Passed every check but was not sent to the ledger (dry run)."),
    "blocked_by_agent": Status(
        "Blocked by agent", "bad", "The AI agent stopped this invoice before payment."),
    "blocked_by_rules_server": Status(
        "Blocked by rules server", "bad",
        "The independent rules server refused to approve this payment."),
    "paused": Status(
        "Held: agent paused", "muted", "The agent was paused by the CFO, so nothing was processed."),
    "failed": Status(
        "Failed", "warn", "Approved, but the ledger submission did not succeed."),
}


def status_of(code: str | None) -> Status:
    code = code or "unknown"
    return STATUSES.get(code, Status(code.replace("_", " ").capitalize(), "muted", ""))


# ---------------------------------------------------------------- formatting
def amount(record: dict) -> Decimal:
    try:
        return Decimal(str(record.get("amount_zar") or "0"))
    except InvalidOperation:
        return Decimal("0")


def fmt_zar(value: Decimal | float | int) -> str:
    return f"R{Decimal(str(value)):,.2f}"


def parse_time(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone(SAST)
    except ValueError:
        return None


def fmt_time(iso: str | None) -> str:
    dt = parse_time(iso)
    return dt.strftime("%d %b %Y, %H:%M") if dt else "-"


def pretty_item(key: str) -> str:
    return key.replace("_", " ").capitalize()


# --------------------------------------------------------------- data access
def load_records(path: Path | None = None) -> list[dict]:
    """Agent decision log, oldest first. Malformed lines are skipped."""
    path = path or LOG_PATH
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


def load_suppliers(path: Path | None = None) -> dict[str, str]:
    """supplier_id -> registered company name."""
    path = path or SUPPLIERS_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {k: v.get("name", k) for k, v in raw.items() if not k.startswith("_")}


def load_prices(path: Path | None = None) -> dict[str, Decimal]:
    path = path or PRICES_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {k: Decimal(str(v)) for k, v in raw.items() if not k.startswith("_")}


def supplier_name(record: dict, suppliers: dict[str, str] | None = None) -> str:
    suppliers = suppliers or {}
    sid = record.get("supplier_id") or ""
    return record.get("supplier_name") or suppliers.get(sid) or sid or "Unknown supplier"


# ---------------------------------------------------------------- agent pause
def agent_paused(path: Path | None = None) -> bool:
    path = path or CONTROL_PATH
    try:
        return bool(json.loads(path.read_text()).get("paused"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def set_agent_paused(paused: bool, path: Path | None = None, audit_path: Path | None = None) -> None:
    path = path or CONTROL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"paused": paused}))
    append_audit("Agent paused" if paused else "Agent resumed",
                 "Kill switch changed from the dashboard", path=audit_path)


# ---------------------------------------------------------------------- audit
def append_audit(action: str, detail: str = "", actor: str = "CFO dashboard",
                 path: Path | None = None) -> None:
    path = path or AUDIT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": actor,
        "action": action,
        "detail": detail,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_audit(path: Path | None = None) -> list[dict]:
    return load_records(path or AUDIT_PATH)


# -------------------------------------------------------------------- reasons
INJECTION = "Hidden instructions in invoice"
WRONG_WALLET = "Wrong destination wallet"

# Order matters: the first match wins.
_REASON_RULES: list[tuple[str, tuple[str, ...]]] = [
    (INJECTION, ("instructions aimed at the payment system",)),
    (WRONG_WALLET, ("destination mismatch",)),
    ("Inflated price", ("above market price",)),
    ("Totals do not add up", ("line items add up",)),
    ("No market price on file", ("no market price",)),
    ("Duplicate invoice", ("already reserved", "already paid", "already authorized")),
    ("Unregistered invoice", ("invoice is not registered",)),
    ("Unapproved supplier", ("supplier is not approved", "is not registered")),
    ("Spending limit exceeded", ("spending limit", "exceeds")),
    ("Amount or memo mismatch", ("amount mismatch", "does not match", "memo mismatch")),
    ("Agent paused", ("paused",)),
]


def categorise_reason(reason: str) -> str:
    text = reason.lower()
    for category, needles in _REASON_RULES:
        if any(n in text for n in needles):
            return category
    return "Other"


def record_categories(record: dict) -> set[str]:
    return {categorise_reason(r) for r in record.get("reasons") or []}


def block_reason_counts(records: list[dict]) -> dict[str, int]:
    """How many blocked invoices hit each category (an invoice can hit several)."""
    counts: dict[str, int] = {}
    for rec in records:
        if rec.get("status") in BLOCKED:
            for cat in record_categories(rec):
                counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


# -------------------------------------------------------------------- summary
def summarise(records: list[dict]) -> dict:
    paid = [r for r in records if r.get("status") == "paid"]
    blocked = [r for r in records if r.get("status") in BLOCKED]
    reviewed = [r for r in records if r.get("status") != "paused"]
    tampering = [r for r in blocked if record_categories(r) & {INJECTION, WRONG_WALLET}]
    return {
        "reviewed": len(reviewed),
        "paid_count": len(paid),
        "paid_value": sum((amount(r) for r in paid), Decimal("0")),
        "blocked_count": len(blocked),
        "blocked_value": sum((amount(r) for r in blocked), Decimal("0")),
        "block_rate": (len(blocked) / len(reviewed)) if reviewed else 0.0,
        "tampering": len(tampering),
    }


def outcome_counts(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in records:
        code = rec.get("status") or "unknown"
        counts[code] = counts.get(code, 0) + 1
    return counts


# -------------------------------------------------------------- decision trail
def decision_trail(record: dict) -> list[tuple[str, str, str]]:
    """Steps an invoice went through: (step, state, detail).

    state is one of: pass, fail, skip, na.
    """
    status = record.get("status")
    reasons = "; ".join(record.get("reasons") or [])

    if status == "paused":
        return [("Agent paused by the CFO", "fail", reasons or "No invoices are processed while paused")]

    invoice = record.get("invoice_number") or "unknown invoice"
    trail = [("Invoice read by the AI agent", "pass",
              f"{invoice} from {supplier_name(record)}, {fmt_zar(amount(record))}")]

    not_reached = ""  # the step state already says "Not reached"
    if status == "blocked_by_agent":
        trail.append(("Agent safety checks", "fail", reasons))
        trail.append(("Independent rules server", "na", not_reached))
        trail.append(("XRP Ledger settlement", "na", not_reached))
        return trail

    if record.get("simulated_compromise"):
        trail.append(("Agent safety checks", "skip",
                      "Bypassed: demo of a compromised agent ignoring its own checks"))
    else:
        trail.append(("Agent safety checks", "pass",
                      "Prices, totals and hidden instructions checked"))

    if status == "blocked_by_rules_server":
        trail.append(("Independent rules server", "fail", reasons))
        trail.append(("XRP Ledger settlement", "na", not_reached))
        return trail

    trail.append(("Independent rules server", "pass",
                  "Supplier, limits, exact transaction and single-use invoice approved"))

    if status == "paid":
        tx = record.get("tx_hash", "")
        trail.append(("XRP Ledger settlement", "pass",
                      f"Settled in transaction {tx[:10]}…" if tx else "Settled"))
    elif status == "failed":
        trail.append(("XRP Ledger settlement", "fail", reasons or "Submission failed"))
    else:
        trail.append(("XRP Ledger settlement", "na", "Not submitted (dry run)"))
    return trail


def explorer_link(record: dict) -> str:
    if record.get("explorer"):
        return record["explorer"]
    if record.get("tx_hash"):
        return EXPLORER_TX + record["tx_hash"]
    return ""


# ------------------------------------------------------------ policy checklist
_POLICY_CHECKS = [
    ("Supplier is on the approved register", "Supplier is not approved"),
    ("Amount is within the per-payment limit", "Payment exceeds the spending limit"),
    ("Invoice is registered against a purchase order", "Invoice is not registered"),
    ("Supplier matches the registered invoice", "Supplier does not match approved invoice"),
    ("Amount matches the registered invoice", "Amount does not match approved invoice"),
]


def policy_checklist(reasons: list[str]) -> list[tuple[str, str]]:
    """Turn the rules server's failure reasons into a full pass/fail checklist."""
    failed = set(reasons)
    unregistered = "Invoice is not registered" in failed
    out = []
    for i, (label, failure) in enumerate(_POLICY_CHECKS):
        if i >= 3 and unregistered:
            out.append((label, "na"))
        else:
            out.append((label, "fail" if failure in failed else "pass"))
    known = {f for _, f in _POLICY_CHECKS}
    out += [(reason, "fail") for reason in reasons if reason not in known]
    return out


# ------------------------------------------------------------- ledger history
DEMO_ZAR_PER_XRP = Decimal("1500")  # same demo rate as agent/xrpl_payments.py


def supplier_wallets(path: Path | None = None) -> dict[str, str]:
    """wallet address -> registered supplier name (addresses come from the environment)."""
    import os

    path = path or SUPPLIERS_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    out = {}
    for sid, entry in raw.items():
        if sid.startswith("_") or not isinstance(entry, dict):
            continue
        address = os.getenv(entry.get("wallet_env", ""))
        if address:
            out.setdefault(address, entry.get("name", sid))
    return out


def _memo_invoice(tx: dict) -> str | None:
    for item in tx.get("Memos") or []:
        memo = item.get("Memo", {}) if isinstance(item, dict) else {}
        if str(memo.get("MemoType", "")).upper() == "invoice".encode().hex().upper():
            try:
                return bytes.fromhex(memo.get("MemoData", "")).decode("utf-8")
            except ValueError:
                return None
    return None


def parse_ledger_payments(transactions: list[dict], treasury: str,
                          wallet_names: dict[str, str] | None = None) -> list[dict]:
    """Successful Treasury payments that carry an invoice memo, newest first.

    `transactions` is the `transactions` list from an XRPL account_tx response.
    """
    wallet_names = wallet_names or {}
    rows = []
    for entry in transactions:
        tx = entry.get("tx_json") or entry.get("tx") or {}
        meta = entry.get("meta") or {}
        if tx.get("TransactionType") != "Payment" or tx.get("Account") != treasury:
            continue
        if meta.get("TransactionResult") != "tesSUCCESS":
            continue
        invoice = _memo_invoice(tx)
        if not invoice:
            continue
        delivered = meta.get("delivered_amount") or tx.get("DeliverMax") or tx.get("Amount")
        if not isinstance(delivered, str):  # issued currencies are out of scope for the demo
            continue
        xrp = Decimal(delivered) / Decimal(1_000_000)
        destination = tx.get("Destination", "")
        rows.append({
            "timestamp": entry.get("close_time_iso"),
            "invoice_number": invoice,
            "supplier": wallet_names.get(destination, destination),
            "destination": destination,
            "xrp": xrp,
            "zar": xrp * DEMO_ZAR_PER_XRP,
            "hash": entry.get("hash") or tx.get("hash", ""),
            "multisigned": bool(tx.get("Signers")),
        })
    rows.sort(key=lambda r: r["timestamp"] or "", reverse=True)
    return rows
