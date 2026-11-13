"""
Imali Yethu payment agent.

    python -m agent.run_agent data/sample_invoices/honest.txt            # dry run
    python -m agent.run_agent data/sample_invoices/honest.txt --submit   # pay on Testnet
    python -m agent.run_agent data/sample_invoices/hacked.txt --simulate-compromised

Flow: read invoice (Claude) -> agent checks -> rules server validate,
verify transaction, reserve invoice -> submit to XRPL -> log decision.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from agent.invoice_reader import read_invoice
from agent.price_check import check_prices
from agent.rules_client import RulesServerClient
from agent.xrpl_payments import TESTNET_EXPLORER, build_payment, submit_payment, zar_to_drops

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_PATH = DATA_DIR / "payments.jsonl"
CONTROL_PATH = DATA_DIR / "agent_control.json"
SUPPLIERS_PATH = DATA_DIR / "suppliers.json"


def agent_paused() -> bool:
    try:
        return bool(json.loads(CONTROL_PATH.read_text()).get("paused"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def log_decision(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def run_invoice(
    invoice_text: str,
    *,
    reader=read_invoice,
    rules: RulesServerClient | None = None,
    submitter=submit_payment,
    submit: bool = False,
    simulate_compromised: bool = False,
) -> dict:
    rules = rules or RulesServerClient()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": None,
        "reasons": [],
        "simulated_compromise": simulate_compromised,
    }

    def finish(status: str, reasons: list[str] | None = None) -> dict:
        record["status"] = status
        record["reasons"] = reasons or []
        log_decision(record)
        return record

    if agent_paused():
        return finish("paused", ["Agent paused by CFO"])

    # 1. Read the invoice (untrusted input)
    invoice = reader(invoice_text)
    amount_zar = Decimal(str(invoice.total_zar)).quantize(Decimal("0.01"))
    record.update(
        invoice_number=invoice.invoice_number,
        supplier_id=invoice.supplier_id,
        supplier_name=invoice.supplier_name,
        amount_zar=str(amount_zar),
    )

    # 2. Agent-side checks. A compromised agent skips its own safeguards,
    #    which is exactly why the rules server must check independently.
    if not simulate_compromised:
        reasons = []
        if invoice.embedded_instructions:
            reasons.append("Invoice contains instructions aimed at the payment system: "
                           + " | ".join(invoice.embedded_instructions))
        reasons += check_prices(invoice)
        if reasons:
            return finish("blocked_by_agent", reasons)

    # 3. Destination comes from the supplier register, never from the invoice
    suppliers = json.loads(SUPPLIERS_PATH.read_text())
    supplier = suppliers.get(invoice.supplier_id or "")
    if supplier is None:
        return finish("blocked_by_agent", [f"Supplier {invoice.supplier_id!r} is not registered"])

    destination = os.getenv(supplier["wallet_env"], "")
    if simulate_compromised:
        destination = os.getenv("FAKE_SUPPLIER_ADDRESS", "rFakeSupplierWalletXXXXXXXXXXXXX")

    tx = build_payment(
        treasury=os.getenv("TREASURY_ADDRESS", ""),
        destination=destination,
        amount_drops=zar_to_drops(amount_zar),
        invoice_number=invoice.invoice_number,
    )
    record.update(destination=destination, amount_drops=tx["Amount"])

    # 4. Independent rules server: validate, verify the exact tx, then reserve
    validation = rules.validate_payment(invoice.invoice_number, invoice.supplier_id, str(amount_zar))
    if not validation.get("approved"):
        return finish("blocked_by_rules_server", validation.get("reasons", []))

    verification = rules.verify_transaction(tx)
    if not verification.get("verified"):
        return finish("blocked_by_rules_server", verification.get("reasons", []))

    authorization = rules.authorize_payment(invoice.invoice_number, invoice.supplier_id, str(amount_zar))
    if not authorization.get("authorized"):
        reason = authorization.get("reason") or "; ".join(authorization.get("reasons", []))
        return finish("blocked_by_rules_server", [reason])

    # 5. Submit
    if not submit:
        return finish("approved_dry_run")

    try:
        result_code, tx_hash = submitter(tx)
    except Exception as exc:  # network, signing, ledger errors
        return finish("failed", [f"{type(exc).__name__}: {exc}"])

    record.update(tx_hash=tx_hash, explorer=TESTNET_EXPLORER + tx_hash, result=result_code)
    return finish("paid" if result_code == "tesSUCCESS" else "failed",
                  [] if result_code == "tesSUCCESS" else [f"Ledger result {result_code}"])


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Imali Yethu payment agent")
    parser.add_argument("invoice", type=Path, help="Path to an invoice text file")
    parser.add_argument("--submit", action="store_true", help="Submit approved payments to XRPL Testnet")
    parser.add_argument("--simulate-compromised", action="store_true",
                        help="Demo: agent ignores its own checks and pays the fake supplier")
    args = parser.parse_args()

    record = run_invoice(
        args.invoice.read_text(encoding="utf-8"),
        submit=args.submit,
        simulate_compromised=args.simulate_compromised,
    )

    print(f"\nInvoice {record.get('invoice_number', '?')}: {record['status'].upper()}")
    for reason in record["reasons"]:
        print(f"  - {reason}")
    if record.get("explorer"):
        print(f"  {record['explorer']}")


if __name__ == "__main__":
    main()
