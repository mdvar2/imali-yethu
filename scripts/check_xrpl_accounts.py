
import os

from dotenv import load_dotenv
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo

load_dotenv()

ROLES = [
    "TREASURY",
    "AGENT",
    "RULES_SERVER",
    "CFO",
    "MUNICIPAL_MANAGER",
]


def main():
    client = JsonRpcClient(
        os.getenv(
            "XRPL_RPC_URL",
            "https://s.altnet.rippletest.net:51234",
        )
    )

    for role in ROLES:
        address = os.getenv(f"{role}_ADDRESS")

        if not address:
            print(f"{role}: ADDRESS NOT CONFIGURED")
            continue

        try:
            response = client.request(
                AccountInfo(
                    account=address,
                    ledger_index="validated",
                )
            )

            if not response.is_successful():
                print(f"{role}: ACCOUNT LOOKUP FAILED")
                continue

            account = response.result["account_data"]
            balance_xrp = int(account["Balance"]) / 1_000_000

            print(
                f"{role}: ACTIVE | "
                f"Balance: {balance_xrp} XRP | "
                f"Sequence: {account['Sequence']}"
            )

        except Exception as error:
            print(f"{role}: ERROR - {type(error).__name__}")


if __name__ == "__main__":
    main()
