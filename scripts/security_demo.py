
"""
Imali Yethu security demonstration.

Simulates legitimate and tampered XRPL transaction
proposals without signing or sending XRP.
"""

import os
from unittest.mock import patch

from rules_server.xrpl_verification import verify_xrpl_transaction


TREASURY = "rDemoTreasury"
SUPPLIER = "rDemoApprovedSupplier"
ATTACKER = "rDemoAttacker"


def create_transaction(destination):
    return {
        "TransactionType": "Payment",
        "Account": TREASURY,
        "Destination": destination,
        "Amount": "10000000",
        "Memos": [
            {
                "Memo": {
                    "MemoType": "invoice".encode().hex().upper(),
                    "MemoData": "INV-2026-0001".encode().hex().upper(),
                }
            }
        ],
    }


def main():
    print("\nIMALI YETHU - SECURITY DEMONSTRATION")
    print("=" * 45)

    # Patch wallet policy only for this isolated demo.
    # Never overwrite real wallet configuration.
    with patch.dict(
        os.environ,
        {
            "TREASURY_ADDRESS": TREASURY,
            "HONEST_SUPPLIER_ADDRESS": SUPPLIER,
        },
    ):
        legitimate = verify_xrpl_transaction(
            create_transaction(SUPPLIER)
        )

        fraudulent = verify_xrpl_transaction(
            create_transaction(ATTACKER)
        )

    print("\nSCENARIO 1: LEGITIMATE PAYMENT")
    print("Destination:", SUPPLIER)
    print("Verified:", legitimate["verified"])
    print("Reasons:", legitimate["reasons"])

    print("\nSCENARIO 2: TAMPERED PAYMENT")
    print("Destination:", ATTACKER)
    print("Verified:", fraudulent["verified"])
    print("Reasons:", fraudulent["reasons"])

    assert legitimate["verified"] is True
    assert fraudulent["verified"] is False

    print("\nDEMO RESULT: BOTH SCENARIOS PASSED")


if __name__ == "__main__":
    main()
