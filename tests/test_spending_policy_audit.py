"""Tests for persistent spending-policy audit logging."""

import sqlite3
from decimal import Decimal
from unittest.mock import patch

from rules_server import authorization
from rules_server.spending_policy import (
    get_spending_limit,
    set_spending_limit,
)


def test_spending_limit_update_creates_audit_record(tmp_path):
    database = tmp_path / "isolated_policy.db"

    with patch.object(authorization, "DB_PATH", database):
        assert get_spending_limit() == Decimal("50000.00")

        updated = set_spending_limit(Decimal("1000.00"))

        assert updated == Decimal("1000.00")
        assert get_spending_limit() == Decimal("1000.00")

        with sqlite3.connect(database) as conn:
            rows = conn.execute(
                """
                SELECT
                    previous_limit,
                    new_limit,
                    changed_by,
                    created_at
                FROM spending_policy_audit
                ORDER BY id
                """
            ).fetchall()

        assert len(rows) == 1

        previous, current, actor, timestamp = rows[0]

        assert Decimal(previous) == Decimal("50000.00")
        assert Decimal(current) == Decimal("1000.00")
        assert actor == "authenticated_admin"
        assert timestamp


def test_invalid_limit_creates_no_audit_record(tmp_path):
    database = tmp_path / "invalid_policy.db"

    with patch.object(authorization, "DB_PATH", database):
        assert get_spending_limit() == Decimal("50000.00")

        try:
            set_spending_limit(Decimal("-100.00"))
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid spending limit was accepted")

        assert get_spending_limit() == Decimal("50000.00")

        with sqlite3.connect(database) as conn:
            table = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'spending_policy_audit'
                """
            ).fetchone()

            if table:
                count = conn.execute(
                    "SELECT COUNT(*) FROM spending_policy_audit"
                ).fetchone()[0]
                assert count == 0
