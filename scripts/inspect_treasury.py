
import os

from dotenv import load_dotenv
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo, ServerState

load_dotenv()


def main():
    client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
    treasury = os.environ["TREASURY_ADDRESS"]

    account_response = client.request(
        AccountInfo(
            account=treasury,
            ledger_index="validated",
            signer_lists=True,
        )
    )

    if not account_response.is_successful():
        raise RuntimeError("Treasury account lookup failed")

    account = account_response.result["account_data"]

    print("\nTREASURY ACCOUNT INSPECTION")
    print("=" * 40)
    print("Balance (XRP):", int(account["Balance"]) / 1_000_000)
    print("Sequence:", account["Sequence"])
    print("OwnerCount:", account.get("OwnerCount", 0))
    print("Flags:", account.get("Flags", 0))

    signer_lists = account_response.result.get(
        "signer_lists", []
    )

    if signer_lists:
        known_roles = {
            os.getenv("AGENT_ADDRESS"): "AI Agent",
            os.getenv("RULES_SERVER_ADDRESS"): "Rules Server",
            os.getenv("CFO_ADDRESS"): "CFO",
            os.getenv("MUNICIPAL_MANAGER_ADDRESS"): "Municipal Manager",
        }

        for signer_list in signer_lists:
            print("\nEXISTING SIGNER CONFIGURATION")
            print(
                "Signer quorum:",
                signer_list.get("SignerQuorum"),
            )

            for entry in signer_list.get("SignerEntries", []):
                signer = entry["SignerEntry"]
                address = signer["Account"]
                weight = signer["SignerWeight"]

                role = known_roles.get(
                    address, "Unknown signer"
                )

                if role == "Unknown signer":
                    print(
                        "Unknown signer address:",
                        address,
                    )

                print(
                    f"Role: {role} | Weight: {weight}"
                )
    else:
        print("No signer list returned")

    state_response = client.request(ServerState())

    if state_response.is_successful():
        state = state_response.result.get("state", {})
        validated = state.get("validated_ledger", {})

        print("\nNETWORK RESERVE INFORMATION")
        print(
            "Base reserve:",
            validated.get("reserve_base"),
        )
        print(
            "Owner reserve increment:",
            validated.get("reserve_inc"),
        )


if __name__ == "__main__":
    main()
