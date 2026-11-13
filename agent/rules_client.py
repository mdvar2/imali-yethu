"""HTTP client for the independent rules server (owned by the security side)."""
import os

import requests


class RulesServerClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.getenv("RULES_SERVER_URL", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.getenv("RULES_SERVER_API_KEY", "")

    def _post(self, path: str, body: dict) -> dict:
        response = requests.post(
            f"{self.base_url}{path}",
            json=body,
            headers={"X-Service-Key": self.api_key},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def validate_payment(self, invoice_number: str, supplier_id: str, amount_zar: str) -> dict:
        return self._post("/validate-payment", {
            "invoice_number": invoice_number,
            "supplier_id": supplier_id,
            "amount": amount_zar,
        })

    def verify_transaction(self, tx: dict) -> dict:
        return self._post("/verify-xrpl-transaction", tx)

    def authorize_payment(self, invoice_number: str, supplier_id: str, amount_zar: str) -> dict:
        return self._post("/authorize-payment", {
            "invoice_number": invoice_number,
            "supplier_id": supplier_id,
            "amount": amount_zar,
        })

    def cosign(self, tx_json: dict) -> dict:
        return self._post("/cosign", {"tx_json": tx_json})
