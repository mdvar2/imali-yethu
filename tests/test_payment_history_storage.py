"""Isolated SQLite tests for payment history."""

import sqlite3

import pytest

from rules_server import authorization


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    database = tmp_path / "history_test.db"
    monkeypatch.setattr(authorization, "DB_PATH", database)
    return database


def test_history_returns_invoice_and_events(isolated_database):
    result = authorization.authorize_invoice(
        "TEST-INV-001",
        "TEST-SUP-001",
        "15000.00",
    )
    assert result["authorized"] is True

    authorization.update_payment_status(
        "TEST-INV-001",
        "validated",
        "TEST-TX-HASH",
    )

    history = authorization.list_payment_history()

    assert len(history) == 1
    assert history[0]["invoice_number"] == "TEST-INV-001"
    assert history[0]["supplier_id"] == "TEST-SUP-001"
    assert history[0]["amount"] == "15000.00"
    assert history[0]["status"] == "validated"

    events = history[0]["events"]
    assert [event["event_type"] for event in events] == [
        "RESERVED",
        "VALIDATED",
    ]
    assert events[-1]["transaction_hash"] == "TEST-TX-HASH"


def test_history_returns_empty_list(isolated_database):
    assert authorization.list_payment_history() == []


def test_history_respects_limit(isolated_database):
    for number in range(3):
        authorization.authorize_invoice(
            f"TEST-INV-{number}",
            "TEST-SUP-001",
            "100.00",
        )

    history = authorization.list_payment_history(limit=2)

    assert len(history) == 2
    assert history[0]["invoice_number"] == "TEST-INV-2"
    assert history[1]["invoice_number"] == "TEST-INV-1"


@pytest.mark.parametrize("limit", [0, -1, 101, True, "10"])
def test_history_rejects_invalid_limits(isolated_database, limit):
    with pytest.raises(ValueError):
        authorization.list_payment_history(limit=limit)
