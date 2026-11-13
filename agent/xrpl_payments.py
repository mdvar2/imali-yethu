"""Builds and submits XRPL transactions for approved invoices."""
import os
from decimal import ROUND_DOWN, Decimal

from xrpl.utils import str_to_hex

TESTNET_EXPLORER = "https://testnet.xrpl.org/transactions/"

# Demo conversion only: in production settlement would be in a rand
# stablecoin or RLUSD. Chosen so the registered R15,000 invoice = 10 XRP,
# which is what the rules server currently approves.
DEMO_ZAR_PER_XRP = Decimal("1500")


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


def submit_payment(tx_json: dict) -> tuple[str, str]:
    """Autofill, sign and submit. Returns (result_code, tx_hash).

    With PRIVY_WALLET_ID set, the agent signs through its Privy wallet
    (the Treasury's regular key) and Privy's policy must allow the payment.
    Otherwise it falls back to TREASURY_SEED, like scripts/first_payment.py.
    """
    from xrpl.clients import JsonRpcClient
    from xrpl.models.transactions import Payment, Transaction
    from xrpl.transaction import autofill, submit_and_wait
    from xrpl.wallet import Wallet

    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
    tx = Payment.from_xrpl(tx_json)

    if os.getenv("PRIVY_WALLET_ID"):
        from agent.privy_wallet import PrivyWallet

        filled = autofill(tx, client).to_xrpl()
        filled["SigningPubKey"] = os.environ["PRIVY_WALLET_PUBLIC_KEY"].upper()
        blob = PrivyWallet().sign_transaction(os.environ["PRIVY_WALLET_ID"], filled)
        result = submit_and_wait(Transaction.from_blob(blob), client, autofill=False)
    else:
        signer = Wallet.from_seed(os.environ["TREASURY_SEED"])
        result = submit_and_wait(tx, client, signer)

    return result.result["meta"]["TransactionResult"], result.result["hash"]
