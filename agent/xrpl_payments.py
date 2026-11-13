"""Builds and submits XRPL transactions for approved invoices."""
import os
from decimal import ROUND_DOWN, Decimal

from xrpl.utils import str_to_hex

TESTNET_EXPLORER = "https://testnet.xrpl.org/transactions/"

# Demo conversion only: in production settlement would be in a rand
# stablecoin or RLUSD. Chosen so the registered R15,000 invoice = 10 XRP.
# Must match rules_server/registers.py (a test checks this).
DEMO_ZAR_PER_XRP = Decimal("1500")


class CosignRefused(Exception):
    """The rules server refused to add its signature."""


def zar_to_drops(amount_zar: Decimal) -> str:
    xrp = amount_zar / DEMO_ZAR_PER_XRP
    drops = (xrp * 1_000_000).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return str(drops)


def build_payment(treasury: str, destination: str, amount_drops: str, invoice_number: str) -> dict:
    """The exact transaction JSON the rules server verifies (before autofill)."""
    return {
        "TransactionType": "Payment",
        "Account": treasury,
        "Destination": destination,
        "Amount": amount_drops,
        "Memos": [{
            "Memo": {
                "MemoType": str_to_hex("invoice").upper(),
                "MemoData": str_to_hex(invoice_number).upper(),
            }
        }],
    }


def signing_mode() -> str:
    """multisig: agent + rules server must both sign (Treasury master key disabled).
    privy:    agent signs through its policy-limited Privy wallet (Treasury regular key).
    master:   demo fallback, the Treasury seed signs alone."""
    mode = os.getenv("SIGNING_MODE", "").strip().lower()
    if mode in {"multisig", "privy", "master"}:
        return mode
    return "privy" if os.getenv("PRIVY_WALLET_ID") else "master"


def cosign_and_combine(filled_tx, agent_wallet, rules):
    """Get the rules server's signature, add the agent's, and combine them.

    `filled_tx` must already be autofilled for 2 signers. Raises CosignRefused.
    """
    from xrpl.models.transactions import Payment
    from xrpl.transaction import multisign, sign

    unsigned = filled_tx.to_xrpl()
    result = rules.cosign(unsigned)
    if not result.get("signed"):
        raise CosignRefused("; ".join(result.get("reasons", [])) or "Rules server refused to co-sign")

    rules_signed = result["tx_json"]
    # The rules server must have signed exactly what we sent, nothing else.
    if {k: v for k, v in rules_signed.items() if k != "Signers"} != unsigned:
        raise CosignRefused("Rules server returned a different transaction")

    agent_signed = sign(filled_tx, agent_wallet, multisign=True)
    return multisign(filled_tx, [agent_signed, Payment.from_xrpl(rules_signed)])


def submit_payment(tx_json: dict, rules=None) -> tuple[str, str]:
    """Autofill, sign and submit. Returns (result_code, tx_hash)."""
    from xrpl.clients import JsonRpcClient
    from xrpl.models.transactions import Payment, Transaction
    from xrpl.transaction import autofill, submit_and_wait
    from xrpl.wallet import Wallet

    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
    tx = Payment.from_xrpl(tx_json)
    mode = signing_mode()

    if mode == "multisig":
        from agent.rules_client import RulesServerClient

        filled = autofill(tx, client, signers_count=2)
        combined = cosign_and_combine(filled, Wallet.from_seed(os.environ["AGENT_SEED"]),
                                      rules or RulesServerClient())
        result = submit_and_wait(combined, client, autofill=False)
    elif mode == "privy":
        from agent.privy_wallet import PrivyWallet

        filled = autofill(tx, client).to_xrpl()
        filled["SigningPubKey"] = os.environ["PRIVY_WALLET_PUBLIC_KEY"].upper()
        blob = PrivyWallet().sign_transaction(os.environ["PRIVY_WALLET_ID"], filled)
        result = submit_and_wait(Transaction.from_blob(blob), client, autofill=False)
    else:
        signer = Wallet.from_seed(os.environ["TREASURY_SEED"])
        result = submit_and_wait(tx, client, signer)

    return result.result["meta"]["TransactionResult"], result.result["hash"]
