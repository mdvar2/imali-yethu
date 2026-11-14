"""Multisig co-signing: the rules server signs only reserved, exactly-matching payments.

Uses real XRPL keys and signatures, generated offline (no network needed).
"""
import pytest
from fastapi.testclient import TestClient
from xrpl.core.binarycodec import encode_for_multisigning
from xrpl.core.keypairs import is_valid_message
from xrpl.models.transactions import Payment
from xrpl.wallet import Wallet

from agent.xrpl_payments import CosignRefused, cosign_and_combine
from rules_server.main import app

client = TestClient(app)
SERVICE = {"X-Service-Key": "agent-secret"}
ADMIN = {"X-Admin-Key": "cfo-secret"}

TREASURY = Wallet.create()
SUPPLIER = Wallet.create()
RULES = Wallet.create()
AGENT = Wallet.create()
PAYMENT = {"invoice_number": "INV-2026-0001", "supplier_id": "SUP-001", "amount": "15000.00"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("RULES_SERVER_API_KEY", "agent-secret")
    monkeypatch.setenv("RULES_ADMIN_KEY", "cfo-secret")
    monkeypatch.setenv("TREASURY_ADDRESS", TREASURY.classic_address)
    monkeypatch.setenv("HONEST_SUPPLIER_ADDRESS", SUPPLIER.classic_address)
    monkeypatch.setenv("RULES_SERVER_SEED", RULES.seed)


def autofilled(**overrides):
    tx = {
        "TransactionType": "Payment",
        "Account": TREASURY.classic_address,
        "Destination": SUPPLIER.classic_address,
        "Amount": "10000000",
        "Memos": [{"Memo": {"MemoType": "696E766F696365", "MemoData": b"INV-2026-0001".hex().upper()}}],
        "Fee": "36",
        "Sequence": 7,
        "LastLedgerSequence": 1000,
        "SigningPubKey": "",
        "Flags": 0,
    }
    tx.update(overrides)
    return tx


def reserve():
    assert client.post("/authorize-payment", json=PAYMENT, headers=SERVICE).json()["authorized"] is True


def cosign(tx):
    return client.post("/cosign", json={"tx_json": tx}, headers=SERVICE).json()


def signature_is_valid(tx_json: dict, signer: dict) -> bool:
    entry = signer["Signer"]
    unsigned = {k: v for k, v in tx_json.items() if k != "Signers"}
    message = bytes.fromhex(encode_for_multisigning(unsigned, entry["Account"]))
    return is_valid_message(message, bytes.fromhex(entry["TxnSignature"]), entry["SigningPubKey"])


def test_reserved_invoice_is_cosigned_with_a_valid_signature():
    reserve()
    result = cosign(autofilled())
    assert result["signed"] is True
    signers = result["tx_json"]["Signers"]
    assert signers[0]["Signer"]["Account"] == RULES.classic_address
    assert signature_is_valid(result["tx_json"], signers[0])


def test_cosign_is_single_use():
    reserve()
    assert cosign(autofilled())["signed"] is True
    second = cosign(autofilled())
    assert second["signed"] is False
    assert "already co-signed" in second["reasons"][0]


def test_unreserved_invoice_is_not_cosigned():
    result = cosign(autofilled())
    assert result["signed"] is False


@pytest.mark.parametrize("override, reason", [
    ({"Destination": Wallet.create().classic_address}, "Supplier destination mismatch"),
    ({"Amount": "20000000"}, "Payment amount mismatch"),
    ({"Flags": 131072}, "Payment flags are not allowed"),          # tfPartialPayment
    ({"Fee": "5000000"}, "Transaction fee is too high"),
    ({"SigningPubKey": TREASURY.public_key}, "Transaction must be multisigned (empty SigningPubKey)"),
    ({"SendMax": "20000000"}, "Unexpected transaction fields"),
])
def test_tampered_transaction_is_refused(override, reason):
    reserve()
    result = cosign(autofilled(**override))
    assert result["signed"] is False
    assert reason in result["reasons"]


def test_missing_expiry_is_refused():
    reserve()
    tx = autofilled()
    del tx["LastLedgerSequence"]
    assert "Transaction must expire (LastLedgerSequence missing)" in cosign(tx)["reasons"]


def test_presigned_transaction_is_refused():
    reserve()
    assert cosign(autofilled(Signers=[]))["signed"] is False


def test_paused_rules_server_refuses_everything():
    reserve()
    assert client.post("/pause", json={"paused": True}, headers=ADMIN).json()["paused"] is True
    assert cosign(autofilled())["reasons"] == ["Payments are paused by the CFO"]
    validation = client.post("/validate-payment", json=PAYMENT).json()
    assert "Payments are paused by the CFO" in validation["reasons"]

    client.post("/pause", json={"paused": False}, headers=ADMIN)
    assert cosign(autofilled())["signed"] is True


def test_pause_requires_admin_key():
    assert client.post("/pause", json={"paused": True}, headers=SERVICE).status_code == 401


def test_missing_signing_key_fails_closed(monkeypatch):
    reserve()
    monkeypatch.delenv("RULES_SERVER_SEED")
    assert client.post("/cosign", json={"tx_json": autofilled()}, headers=SERVICE).status_code == 503


class InProcessRules:
    def cosign(self, tx_json):
        return cosign(tx_json)


def test_agent_combines_both_signatures_into_a_valid_multisigned_payment():
    reserve()
    combined = cosign_and_combine(Payment.from_xrpl(autofilled()), AGENT, InProcessRules()).to_xrpl()
    accounts = {s["Signer"]["Account"] for s in combined["Signers"]}
    assert accounts == {AGENT.classic_address, RULES.classic_address}
    assert all(signature_is_valid(combined, s) for s in combined["Signers"])


def test_agent_gets_nothing_without_rules_server_signature():
    with pytest.raises(CosignRefused):
        cosign_and_combine(Payment.from_xrpl(autofilled()), AGENT, InProcessRules())
