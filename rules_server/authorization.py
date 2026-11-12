
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "authorizations.db"


def authorize_invoice(invoice_number: str, supplier_id: str, amount: str):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS authorizations (
                invoice_number TEXT PRIMARY KEY,
                supplier_id TEXT NOT NULL,
                amount TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'reserved'
            )
        """)

        try:
            conn.execute(
                """
                INSERT INTO authorizations
                    (invoice_number, supplier_id, amount)
                VALUES (?, ?, ?)
                """,
                (invoice_number, supplier_id, amount),
            )
            conn.commit()
            return {"authorized": True, "reason": "Invoice reserved"}
        except sqlite3.IntegrityError:
            return {
                "authorized": False,
                "reason": "Invoice already reserved or authorized",
            }
