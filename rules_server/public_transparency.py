"""Restricted public projection of demonstration payment records."""

import re

from rules_server.authorization import list_payment_history


XRPL_HASH_PATTERN = re.compile(r"^[0-9A-Fa-f]{64}$")


def list_public_payments(limit: int = 100) -> list[dict]:
    """Return public-safe payment summaries, without internal audit data."""

    history = list_payment_history(limit=limit)
    public_records = []

    for payment in history:
        status = payment["status"]

        record = {
            "invoice_number": payment["invoice_number"],
            "supplier_id": payment["supplier_id"],
            "amount": payment["amount"],
            "status": status,
            "network": "XRPL Testnet",
            "transaction_hash": None,
            "explorer_url": None,
            "verification_status": "not_confirmed",
        }

        if status == "validated":
            for event in reversed(payment.get("events", [])):
                if event["event_type"] != "VALIDATED":
                    continue

                tx_hash = event.get("transaction_hash")

                if not isinstance(tx_hash, str):
                    continue

                if not XRPL_HASH_PATTERN.fullmatch(tx_hash):
                    continue

                tx_hash = tx_hash.upper()

                record["transaction_hash"] = tx_hash
                record["explorer_url"] = (
                    "https://testnet.xrpl.org/transactions/"
                    + tx_hash
                )
                record["verification_status"] = "recorded_validated"
                break

        public_records.append(record)

    return public_records
