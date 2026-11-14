import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "authorizations.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS authorizations (
            invoice_number TEXT PRIMARY KEY,
            supplier_id TEXT NOT NULL,
            amount TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'reserved',
            created_at TEXT
        )
    """)
    # Older databases were created without created_at: add it, and date
    # existing rows to now so they count towards the current week.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(authorizations)")}
    if "created_at" not in columns:
        conn.execute("ALTER TABLE authorizations ADD COLUMN created_at TEXT")
        conn.execute("UPDATE authorizations SET created_at = ? WHERE created_at IS NULL", (_now(),))
        conn.commit()
    return conn


def authorize_invoice(invoice_number: str, supplier_id: str, amount: str):
    with _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO authorizations
                    (invoice_number, supplier_id, amount, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (invoice_number, supplier_id, amount, _now()),
            )
            conn.commit()
            return {"authorized": True, "reason": "Invoice reserved"}
        except sqlite3.IntegrityError:
            return {
                "authorized": False,
                "reason": "Invoice already reserved or authorized",
            }


def mark_signed(invoice_number: str) -> bool:
    """Move a reserved invoice to 'signed'. False if it was never reserved or is already signed.

    The UPDATE is conditional, so two co-sign requests for one invoice can never both succeed.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE authorizations SET status = 'signed' WHERE invoice_number = ? AND status = 'reserved'",
            (invoice_number,),
        )
        conn.commit()
        return cursor.rowcount == 1


def release_signature(invoice_number: str) -> None:
    """Undo mark_signed if signing failed, so the invoice is not burned by a server error."""
    with _connect() as conn:
        conn.execute(
            "UPDATE authorizations SET status = 'reserved' WHERE invoice_number = ? AND status = 'signed'",
            (invoice_number,),
        )
        conn.commit()


def reserved_total_last_7_days() -> Decimal:
    """Sum of invoices reserved in the last 7 days (counts towards the weekly cap)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT amount FROM authorizations WHERE created_at >= ?", (cutoff,)
        ).fetchall()
    return sum((Decimal(r[0]) for r in rows), Decimal("0"))
