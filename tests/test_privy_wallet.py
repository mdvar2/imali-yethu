"""
Privy wallet tests. Privy's HTTP API is mocked with a local secp256k1 key
that signs exactly like Privy's xrpl_signTransaction, so the signed blob
can be checked cryptographically.
"""
import pytest
from xrpl.core import keypairs
from xrpl.core.binarycodec import decode, encode, encode_for_signing
from xrpl.wallet import Wallet

from agent import privy_wallet, xrpl_payments
from agent.privy_wallet import PrivyError, PrivyWallet

AGENT_KEY = Wallet.create(algorithm=__import__("xrpl").CryptoAlgorithm.SECP256K1)
TREASURY = Wallet.create()
SUPPLIER = Wallet.create()


class FakePrivyHTTP:
    """Stands in for requests.request against api.privy.io."""

    def __init__(self, deny_destinations=()):
        self.calls = []
        self.deny = set(deny_destinations)

    def __call__(self, method, url, json=None, auth=None, headers=None, timeout=None):
        self.calls.append({"method": method, "url": url, "json": json, "auth": auth, "headers": headers})
        path = url.removeprefix(privy_wallet.PRIVY_API)

        if path == "/v1/policies":
            return FakeResponse(200, {"id": "policy123"})
        if path == "/v1/wallets":
            return FakeResponse(200, {"id": "wallet123", "address": AGENT_KEY.address,
                                      "public_key": AGENT_KEY.public_key})
        if path.endswith("/rpc"):
            signing_hex = json["params"]["transaction"]
            tx = decode(signing_hex.removeprefix("53545800"))
            if tx.get("Destination") in self.deny:
                return FakeResponse(403, {"error": "Policy violation"})
            tx["TxnSignature"] = keypairs.sign(bytes.fromhex(signing_hex), AGENT_KEY.private_key)
            return FakeResponse(200, {"method": "xrpl_signTransaction",
                                      "data": {"signed_transaction": encode(tx), "encoding": "hex"}})
        return FakeResponse(404, {})


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body, self.ok = status, body, 200 <= status < 300
        self.text = str(body)

    def json(self):
        return self._body


@pytest.fixture
def privy_http(monkeypatch):
    fake = FakePrivyHTTP()
    monkeypatch.setattr(privy_wallet.requests, "request", fake)
    return fake


def autofilled_payment(destination=None):
    tx = xrpl_payments.build_payment(TREASURY.address, destination or SUPPLIER.address,
                                     "10000000", "INV-2026-0001")
    tx.update(Fee="12", Sequence=5, LastLedgerSequence=1000, SigningPubKey=AGENT_KEY.public_key)
    return tx


def test_requests_carry_privy_auth(privy_http):
    PrivyWallet("app", "secret").create_policy([SUPPLIER.address], max_drops=20_000_000)
    call = privy_http.calls[0]
    assert call["auth"] == ("app", "secret")
    assert call["headers"]["privy-app-id"] == "app"


def test_policy_restricts_destination_and_amount(privy_http):
    PrivyWallet("app", "secret").create_policy([SUPPLIER.address], max_drops=20_000_000)
    rule = privy_http.calls[0]["json"]["rules"][0]
    conditions = {c["field"]: c for c in rule["conditions"]}
    assert rule["method"] == "xrpl_signTransaction"
    assert conditions["Payment.Destination"]["value"] == [SUPPLIER.address]
    assert conditions["Payment.Amount.drops"] == {
        "field_source": "xrpl_transaction", "field": "Payment.Amount.drops",
        "operator": "lt", "value": "20000001"}


def test_signed_blob_is_valid_treasury_payment(privy_http):
    tx = autofilled_payment()
    blob = PrivyWallet("app", "secret").sign_transaction("wallet123", tx)

    signed = decode(blob)
    assert signed["Account"] == TREASURY.address          # pays from Treasury
    assert signed["Destination"] == SUPPLIER.address
    assert signed["SigningPubKey"] == AGENT_KEY.public_key  # signed by agent's regular key
    unsigned = {k: v for k, v in signed.items() if k != "TxnSignature"}
    assert keypairs.is_valid_message(bytes.fromhex(encode_for_signing(unsigned)),
                                     bytes.fromhex(signed["TxnSignature"]), AGENT_KEY.public_key)

    sent = privy_http.calls[0]["json"]
    assert sent["method"] == "xrpl_signTransaction"
    assert sent["params"]["transaction"].startswith("53545800")


def test_policy_denial_raises(monkeypatch):
    monkeypatch.setattr(privy_wallet.requests, "request", FakePrivyHTTP(deny_destinations={SUPPLIER.address}))
    with pytest.raises(PrivyError, match="403"):
        PrivyWallet("app", "secret").sign_transaction("wallet123", autofilled_payment())


def test_submit_payment_uses_privy_when_configured(monkeypatch, privy_http):
    monkeypatch.setenv("XRPL_RPC_URL", "http://unused")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    monkeypatch.setenv("PRIVY_WALLET_ID", "wallet123")
    monkeypatch.setenv("PRIVY_WALLET_PUBLIC_KEY", AGENT_KEY.public_key)
    monkeypatch.delenv("TREASURY_SEED", raising=False)  # must not be needed

    import xrpl.transaction as xt

    def fake_autofill(tx, client):
        d = tx.to_xrpl()
        d.update(Fee="12", Sequence=5, LastLedgerSequence=1000)
        return type(tx).from_xrpl(d)

    submitted = {}

    def fake_submit(tx, client, wallet=None, **kw):
        submitted["tx"], submitted["wallet"] = tx, wallet

        class R:
            result = {"meta": {"TransactionResult": "tesSUCCESS"}, "hash": "HASH1"}
        return R()

    monkeypatch.setattr(xt, "autofill", fake_autofill)
    monkeypatch.setattr(xt, "submit_and_wait", fake_submit)

    code, tx_hash = xrpl_payments.submit_payment(autofilled_payment())
    assert (code, tx_hash) == ("tesSUCCESS", "HASH1")
    assert submitted["wallet"] is None                       # no local key used
    assert submitted["tx"].is_signed()
    assert submitted["tx"].signing_pub_key == AGENT_KEY.public_key
