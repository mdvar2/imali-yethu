"""Independent, persistent spending policy for Imali Yethu."""

import sqlite3
from decimal import Decimal, InvalidOperation

from rules_server.authorization import get_connection

DEFAULT_LIMIT = Decimal("50000.00")


def initialize_spending_policy():
    """Create policy storage without changing existing invoices."""

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spending_policy (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                max_payment TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO spending_policy (id, max_payment)
            VALUES (1, ?)
            """,
            (str(DEFAULT_LIMIT),),
        )


def get_spending_limit() -> Decimal:
    """Read the independent spending limit."""

    initialize_spending_policy()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT max_payment
            FROM spending_policy
            WHERE id = 1
            """
        ).fetchone()

    if row is None:
        raise RuntimeError("Spending policy is unavailable")

    try:
        limit = Decimal(row[0])
    except (InvalidOperation, TypeError):
        raise RuntimeError("Invalid stored spending limit")

    if not limit.is_finite() or limit <= 0:
        raise RuntimeError("Invalid stored spending limit")

    return limit


def set_spending_limit(amount: Decimal) -> Decimal:
    """Update the limit. Caller must enforce human authorization."""

    amount = Decimal(str(amount))

    if (
        not amount.is_finite()
        or amount <= 0
        or amount.as_tuple().exponent < -2
    ):
        raise ValueError("Invalid spending limit")

    initialize_spending_policy()

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spending_policy_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                previous_limit TEXT NOT NULL,
                new_limit TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        row = conn.execute(
            "SELECT max_payment FROM spending_policy WHERE id = 1"
        ).fetchone()

        if row is None:
            raise RuntimeError("Spending policy is unavailable")

        previous_limit = row[0]

        conn.execute(
            """
            UPDATE spending_policy
            SET max_payment = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (str(amount),),
        )

        conn.execute(
            """
            INSERT INTO spending_policy_audit (
                previous_limit,
                new_limit,
                changed_by
            )
            VALUES (?, ?, ?)
            """,
            (
                previous_limit,
                str(amount),
                "authenticated_admin",
            ),
        )

    return amount


def check_spending_limit(amount: Decimal) -> dict:
    """Reject amounts exceeding the independent policy."""

    limit = get_spending_limit()
    amount = Decimal(str(amount))

    if not amount.is_finite() or amount <= 0:
        return {
            "approved": False,
            "reasons": ["Invalid payment amount"],
        }

    if amount > limit:
        return {
            "approved": False,
            "reasons": ["Payment exceeds the spending limit"],
        }

    return {
        "approved": True,
        "reasons": [],
    }
