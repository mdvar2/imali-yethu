"""
First Imali Yethu Testnet transaction:
Treasury pays the Honest Supplier 10 XRP with the invoice number in Memos.

Run after setup_wallets.py:  python scripts/first_payment.py
Copy the printed explorer link into the README as proof.
"""
import os

from dotenv import load_dotenv
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import Memo, Payment
from xrpl.transaction import submit_and_wait
from xrpl.utils import str_to_hex, xrp_to_drops
from xrpl.wallet import Wallet

load_dotenv()

INVOICE_NUMBER = "INV-2026-0001"
AMOUNT_XRP = 10


def main() -> None:
    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
    treasury = Wallet.from_seed(os.environ["TREASURY_SEED"])
    supplier_address = os.environ["HONEST_SUPPLIER_ADDRESS"]

    tx = Payment(
        account=treasury.address,
        destination=supplier_address,
        amount=xrp_to_drops(AMOUNT_XRP),
        memos=[
            Memo(
                memo_type=str_to_hex("invoice"),
                memo_data=str_to_hex(INVOICE_NUMBER),
            )
        ],
    )

    print(f"Paying {AMOUNT_XRP} XRP to {supplier_address} for {INVOICE_NUMBER}...")
    result = submit_and_wait(tx, client, treasury)

    status = result.result["meta"]["TransactionResult"]
    tx_hash = result.result["hash"]
    print(f"Result: {status}")
    print(f"Explorer: https://testnet.xrpl.org/transactions/{tx_hash}")


if __name__ == "__main__":
    main()
