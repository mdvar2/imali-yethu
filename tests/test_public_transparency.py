"""Security tests for public payment projections."""

import pytest

from rules_server import public_transparency


VALID_HASH = "A" * 64
FAILED_HASH = "B" * 64

PUBLIC_FIELDS = {
    "invoice_number",
    "supplier_id",
    "amount",
    "status",
    "network",
    "transaction_hash",
    "explorer_url",
    "verification_status",
}


def payment_record(status, events):
    return {
        "invoice_number": "TEST-INV-001",
        "supplier_id": "TEST-SUP-001",
        "amount": "15000.00",
        "status": status,
        "events": events,
    }


def audit_event(event_type, tx_hash=None):
    return {
        "event_type": event_type,
        "reason": "PRIVATE INTERNAL FAILURE DETAILS",
        "transaction_hash": tx_hash,
        "created_at": "2026-11-13 12:00:00",
    }


def test_validated_payment_exposes_only_approved_fields(monkeypatch):
    record = payment_record(
        "validated",
        [
            audit_event("SUBMITTING", FAILED_HASH),
            audit_event("VALIDATED", VALID_HASH),
        ],
    )

    monkeypatch.setattr(
        public_transparency,
        "list_payment_history",
        lambda limit=100: [record],
    )

    result = public_transparency.list_public_payments()

    assert len(result) == 1
    assert set(result[0]) == PUBLIC_FIELDS
    assert result[0]["transaction_hash"] == VALID_HASH
    assert result[0]["verification_status"] == "recorded_validated"
    assert result[0]["explorer_url"] == (
        "https://testnet.xrpl.org/transactions/" + VALID_HASH
    )
    assert "PRIVATE INTERNAL FAILURE DETAILS" not in str(result)


@pytest.mark.parametrize(
    "status",
    ["reserved", "submitting", "submitted", "failed"],
)
def test_nonvalidated_payment_hides_transaction_hash(monkeypatch, status):
    record = payment_record(
        status,
        [
            audit_event("SUBMITTING", FAILED_HASH),
            audit_event("SUBMISSION_RESPONSE", FAILED_HASH),
        ],
    )

    monkeypatch.setattr(
        public_transparency,
        "list_payment_history",
        lambda limit=100: [record],
    )

    result = public_transparency.list_public_payments()[0]

    assert result["transaction_hash"] is None
    assert result["explorer_url"] is None
    assert result["verification_status"] == "not_confirmed"
    assert "PRIVATE INTERNAL FAILURE DETAILS" not in str(result)


@pytest.mark.parametrize(
    "tx_hash",
    [None, "", "not-a-real-hash", "G" * 64],
)
def test_invalid_validated_hash_is_not_published(monkeypatch, tx_hash):
    record = payment_record(
        "validated",
        [audit_event("VALIDATED", tx_hash)],
    )

    monkeypatch.setattr(
        public_transparency,
        "list_payment_history",
        lambda limit=100: [record],
    )

    result = public_transparency.list_public_payments()[0]

    assert result["transaction_hash"] is None
    assert result["explorer_url"] is None
    assert result["verification_status"] == "not_confirmed"


def test_validated_status_without_validated_event_is_unconfirmed(monkeypatch):
    record = payment_record(
        "validated",
        [audit_event("SUBMISSION_RESPONSE", VALID_HASH)],
    )

    monkeypatch.setattr(
        public_transparency,
        "list_payment_history",
        lambda limit=100: [record],
    )

    result = public_transparency.list_public_payments()[0]

    assert result["transaction_hash"] is None
    assert result["verification_status"] == "not_confirmed"


def test_public_history_respects_requested_limit(monkeypatch):
    observed = []

    def fake_history(limit=100):
        observed.append(limit)
        return []

    monkeypatch.setattr(
        public_transparency,
        "list_payment_history",
        fake_history,
    )

    assert public_transparency.list_public_payments(limit=5) == []
    assert observed == [5]
