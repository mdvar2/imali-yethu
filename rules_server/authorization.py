
"""Invoice authorization and payment audit storage."""

import sqlite3
from pathlib import Path

DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "authorizations.db"
)


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS authorizations (
            invoice_number TEXT PRIMARY KEY,
            supplier_id TEXT NOT NULL,
            amount TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'reserved'
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT NOT NULL,
            event_type TEXT NOT NULL,
            reason TEXT,
            transaction_hash TEXT,
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    return conn


def record_audit(
    invoice_number: str,
    event_type: str,
    reason: str | None = None,
    transaction_hash: str | None = None,
):
    """Record a payment decision without storing credentials."""

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO payment_audit (
                invoice_number,
                event_type,
                reason,
                transaction_hash
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                invoice_number,
                event_type,
                reason,
                transaction_hash,
            ),
        )


def authorize_invoice(
    invoice_number: str,
    supplier_id: str,
    amount: str,
):
    """Atomically reserve an invoice once."""

    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO authorizations (
                    invoice_number,
                    supplier_id,
                    amount
                )
                VALUES (?, ?, ?)
                """,
                (
                    invoice_number,
                    supplier_id,
                    amount,
                ),
            )

            conn.execute(
                """
                INSERT INTO payment_audit (
                    invoice_number,
                    event_type,
                    reason
                )
                VALUES (?, 'RESERVED', 'Invoice reserved')
                """,
                (invoice_number,),
            )

            conn.commit()

            return {
                "authorized": True,
                "reason": "Invoice reserved",
            }

        except sqlite3.IntegrityError:
            conn.rollback()

            record_audit(
                invoice_number,
                "BLOCKED",
                "Invoice already reserved or authorized",
            )

            return {
                "authorized": False,
                "reason": (
                    "Invoice already reserved or authorized"
                ),
            }


def update_payment_status(
    invoice_number: str,
    status: str,
    transaction_hash: str | None = None,
):
    """Update an existing invoice after settlement checks."""

    allowed_statuses = {
        "reserved",
        "submitting",
        "submitted",
        "validated",
        "failed",
    }

    if status not in allowed_statuses:
        raise ValueError("Unsupported payment status")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE authorizations
            SET status = ?
            WHERE invoice_number = ?
            """,
            (status, invoice_number),
        )

        if cursor.rowcount != 1:
            raise ValueError("Invoice reservation not found")

        conn.execute(
            """
            INSERT INTO payment_audit (
                invoice_number,
                event_type,
                transaction_hash
            )
            VALUES (?, ?, ?)
            """,
            (
                invoice_number,
                status.upper(),
                transaction_hash,
            ),
        )

        conn.commit()


def get_payment_audit(invoice_number: str):
    """Retrieve the audit history for one invoice."""

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                event_type,
                reason,
                transaction_hash,
                created_at
            FROM payment_audit
            WHERE invoice_number = ?
            ORDER BY id ASC
            """,
            (invoice_number,),
        ).fetchall()

    return [
        {
            "event_type": row[0],
            "reason": row[1],
            "transaction_hash": row[2],
            "created_at": row[3],
        }
        for row in rows
    ]
