"""CFO policy endpoint: admin-only, validated, audited, and enforced."""
import json

import pytest
from fastapi.testclient import TestClient

from rules_server import policy
from rules_server.main import app

client = TestClient(app)
ADMIN = {"X-Admin-Key": "cfo-secret"}
SERVICE = {"X-Service-Key": "agent-secret"}
PAYMENT = {"invoice_number": "INV-2026-0001", "supplier_id": "SUP-001", "amount": 15000}
NEW_POLICY = {"max_payment_zar": "10000.00", "weekly_cap_zar": "100000.00",
              "approved_suppliers": ["SUP-001", "SUP-002"]}


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("RULES_ADMIN_KEY", "cfo-secret")
    monkeypatch.setenv("RULES_SERVER_API_KEY", "agent-secret")


def test_root_describes_service():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_get_policy_returns_defaults():
    response = client.get("/policy", headers=ADMIN)
    assert response.status_code == 200
    body = response.json()
    assert body["max_payment_zar"] == "50000.00"
    assert body["spent_last_7_days_zar"] == "0.00"


@pytest.mark.parametrize("headers", [{}, {"X-Admin-Key": "wrong"}, {"X-Admin-Key": "agent-secret"}])
def test_policy_rejects_missing_wrong_or_agent_key(headers):
    assert client.get("/policy", headers=headers).status_code == 401
    assert client.put("/policy", json=NEW_POLICY, headers=headers).status_code == 401


def test_policy_fails_closed_when_admin_key_equals_agent_key(monkeypatch):
    monkeypatch.setenv("RULES_ADMIN_KEY", "agent-secret")
    assert client.get("/policy", headers={"X-Admin-Key": "agent-secret"}).status_code == 503


def test_policy_fails_closed_when_admin_key_unset(monkeypatch):
    monkeypatch.delenv("RULES_ADMIN_KEY")
    assert client.get("/policy", headers=ADMIN).status_code == 503


def test_put_policy_saves_audits_and_is_enforced():
    response = client.put("/policy", json=NEW_POLICY, headers=ADMIN)
    assert response.status_code == 200
    assert client.get("/policy", headers=ADMIN).json()["max_payment_zar"] == "10000.00"

    audit = [json.loads(line) for line in policy.AUDIT_PATH.read_text().splitlines()]
    assert audit[-1]["old"]["max_payment_zar"] == "50000.00"
    assert audit[-1]["new"]["max_payment_zar"] == "10000.00"

    result = client.post("/validate-payment", json=PAYMENT).json()
    assert result["approved"] is False
    assert "Payment exceeds the spending limit" in result["reasons"]


def test_removing_supplier_blocks_payment():
    client.put("/policy", json={**NEW_POLICY, "max_payment_zar": "50000.00",
                                "approved_suppliers": ["SUP-002"]}, headers=ADMIN)
    assert "Supplier is not approved" in client.post("/validate-payment", json=PAYMENT).json()["reasons"]


def test_weekly_cap_counts_reserved_invoices():
    client.put("/policy", json={**NEW_POLICY, "max_payment_zar": "15000.00",
                                "weekly_cap_zar": "20000.00"}, headers=ADMIN)
    assert client.post("/authorize-payment", json=PAYMENT, headers=SERVICE).json()["authorized"] is True
    # R15,000 already reserved this week; another R15,000 would pass the R20,000 cap
    result = client.post("/validate-payment", json=PAYMENT).json()
    assert "Payment would exceed the weekly spending cap" in result["reasons"]


@pytest.mark.parametrize("bad", [
    {**NEW_POLICY, "max_payment_zar": "-5"},
    {**NEW_POLICY, "weekly_cap_zar": "5000.00"},              # below single-payment max
    {**NEW_POLICY, "approved_suppliers": ["SUP-001; DROP"]},
])
def test_put_policy_rejects_invalid_values(bad):
    assert client.put("/policy", json=bad, headers=ADMIN).status_code == 422
    assert not policy.POLICY_PATH.exists()


def test_old_database_without_timestamp_is_migrated(tmp_path):
    import sqlite3
    from rules_server import authorization

    with sqlite3.connect(authorization.DB_PATH) as conn:
        conn.execute("CREATE TABLE authorizations (invoice_number TEXT PRIMARY KEY, supplier_id TEXT NOT NULL,"
                     " amount TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'reserved')")
        conn.execute("INSERT INTO authorizations VALUES ('INV-OLD', 'SUP-001', '1000.00', 'reserved')")
    assert authorization.reserved_total_last_7_days() == 1000
