"""
Privy server wallet for the agent (Privy is the hackathon's suggested agent wallet).

The agent's signing key lives inside Privy, not in .env. Privy only signs
transactions that pass the wallet's policy (allowed destinations, max
amount), so even a compromised agent can't get anything else signed.

The Privy wallet is set as the Treasury account's *regular key*:
transactions still come from the Treasury address, the CFO can revoke
the agent's key on-ledger at any time, and the master key stays with humans.

Docs: https://docs.privy.io/wallets/using-wallets/xrpl/overview
"""
import os

import requests
from xrpl.core.binarycodec import encode_for_signing

PRIVY_API = "https://api.privy.io"


class PrivyError(RuntimeError):
    pass


class PrivyWallet:
    def __init__(self, app_id: str | None = None, app_secret: str | None = None):
        self.app_id = app_id or os.environ["PRIVY_APP_ID"]
        self.app_secret = app_secret or os.environ["PRIVY_APP_SECRET"]

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        response = requests.request(
            method,
            f"{PRIVY_API}{path}",
            json=body,
            auth=(self.app_id, self.app_secret),
            headers={"privy-app-id": self.app_id},
            timeout=30,
        )
        if not response.ok:
            # Policy denials come back here too, e.g. destination not allowed
            raise PrivyError(f"Privy {method} {path} -> {response.status_code}: {response.text}")
        return response.json()

    # ------------------------------------------------------------ setup
    def create_policy(self, allowed_destinations: list[str], max_drops: int) -> str:
        policy = self._request("POST", "/v1/policies", {
            "version": "1.0",
            "name": "Imali Yethu agent: approved suppliers only",
            "chain_type": "xrpl",
            "rules": [{
                "name": "Payments to approved suppliers under the cap",
                "method": "xrpl_signTransaction",
                "conditions": [
                    {"field_source": "xrpl_transaction", "field": "TransactionType",
                     "operator": "eq", "value": "Payment"},
                    {"field_source": "xrpl_transaction", "field": "Payment.Destination",
                     "operator": "in", "value": allowed_destinations},
                    {"field_source": "xrpl_transaction", "field": "Payment.Amount.drops",
                     "operator": "lt", "value": str(max_drops + 1)},
                ],
                "action": "ALLOW",
            }],
        })
        return policy["id"]

    def create_wallet(self, policy_id: str) -> dict:
        return self._request("POST", "/v1/wallets", {
            "chain_type": "xrpl",
            "display_name": "Imali Yethu payment agent",
            "policy_ids": [policy_id],
        })

    # ------------------------------------------------------------ signing
    def sign_transaction(self, wallet_id: str, tx_json: dict) -> str:
        """Sign an autofilled transaction. Returns the signed blob (hex)."""
        result = self._request("POST", f"/v1/wallets/{wallet_id}/rpc", {
            "method": "xrpl_signTransaction",
            "params": {"transaction": encode_for_signing(tx_json), "encoding": "hex"},
        })
        return result["data"]["signed_transaction"].removeprefix("0x").upper()
