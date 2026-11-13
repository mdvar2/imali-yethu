
"""Verify the existing Imali Yethu Testnet Treasury signer list."""

import os
from pathlib import Path

from dotenv import load_dotenv
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo
from xrpl.wallet import Wallet

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

client = JsonRpcClient(os.environ["XRPL_RPC_URL"])

treasury_address = os.environ["DEMO_TREASURY_ADDRESS"]

agent = Wallet.from_seed(os.environ["AGENT_SEED"])
rules_server = Wallet.from_seed(
    os.environ["RULES_SERVER_SEED"]
)

response = client.request(
    AccountInfo(
        account=treasury_address,
        ledger_index="validated",
        signer_lists=True,
    )
)

if not response.is_successful():
    raise RuntimeError("Treasury account lookup failed.")

result = response.result
signer_lists = result.get("signer_lists", [])

if len(signer_lists) != 1:
    raise RuntimeError(
        f"Expected one signer list, found {len(signer_lists)}."
    )

signer_list = signer_lists[0]

actual_signers = {
    entry["SignerEntry"]["Account"]:
    entry["SignerEntry"]["SignerWeight"]
    for entry in signer_list["SignerEntries"]
}

expected_signers = {
    agent.address: 1,
    rules_server.address: 2,
}

quorum = signer_list["SignerQuorum"]

print("\n--- IMALI YETHU DEMO TREASURY ---")
print("Treasury:", treasury_address)
print("Signer quorum:", quorum)
print("Agent signer weight:", actual_signers.get(agent.address))
print(
    "Rules Server signer weight:",
    actual_signers.get(rules_server.address),
)
print("Account flags:", result["account_data"]["Flags"])

if quorum != 3:
    raise RuntimeError("Unexpected signer quorum.")

if actual_signers != expected_signers:
    raise RuntimeError("Signer list does not match policy.")

print("\nSUCCESS: Signer list matches the intended configuration.")
print("Master key has not been disabled.")
