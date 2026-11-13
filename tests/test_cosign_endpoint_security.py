"""Security tests for the /cosign HTTP endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from rules_server.main import app


SERVICE_KEY = "test-agent-service-key"
ADMIN_KEY = "test-independent-admin-key"
URL = "/cosign"

TRANSACTION = {
    "TransactionType": "Payment",
    "Account": "rTestTreasuryPlaceholder",
    "Destination": "rTestSupplierPlaceholder",
    "Amount": "10000000",
}


def test_cosign_rejects_missing_service_key():
    with (
        patch.dict("os.environ", {
            "RULES_SERVER_API_KEY": SERVICE_KEY,
            "RULES_ADMIN_API_KEY": ADMIN_KEY,
        }),
        patch("rules_server.main.execute_agent_payment") as execute,
        TestClient(app) as client,
    ):
        response = client.post(URL, json=TRANSACTION)

        assert response.status_code == 401
        execute.assert_not_called()


def test_cosign_rejects_invalid_service_key():
    with (
        patch.dict("os.environ", {
            "RULES_SERVER_API_KEY": SERVICE_KEY,
            "RULES_ADMIN_API_KEY": ADMIN_KEY,
        }),
        patch("rules_server.main.execute_agent_payment") as execute,
        TestClient(app) as client,
    ):
        response = client.post(
            URL,
            headers={"X-Service-Key": "incorrect-key"},
            json=TRANSACTION,
        )

        assert response.status_code == 401
        execute.assert_not_called()


def test_admin_key_cannot_access_cosign():
    with (
        patch.dict("os.environ", {
            "RULES_SERVER_API_KEY": SERVICE_KEY,
            "RULES_ADMIN_API_KEY": ADMIN_KEY,
        }),
        patch("rules_server.main.execute_agent_payment") as execute,
        TestClient(app) as client,
    ):
        response = client.post(
            URL,
            headers={"X-Service-Key": ADMIN_KEY},
            json=TRANSACTION,
        )

        assert response.status_code == 401
        execute.assert_not_called()


def test_cosign_accepts_valid_service_key():
    expected = {
        "approved": False,
        "reasons": ["Mock execution only"],
    }

    with (
        patch.dict("os.environ", {
            "RULES_SERVER_API_KEY": SERVICE_KEY,
            "RULES_ADMIN_API_KEY": ADMIN_KEY,
        }),
        patch(
            "rules_server.main.execute_agent_payment",
            return_value=expected,
        ) as execute,
        TestClient(app) as client,
    ):
        response = client.post(
            URL,
            headers={"X-Service-Key": SERVICE_KEY},
            json=TRANSACTION,
        )

        assert response.status_code == 200
        assert response.json() == expected
        execute.assert_called_once_with(TRANSACTION)


def test_cosign_fails_closed_without_service_key_configuration():
    with (
        patch.dict("os.environ", {
            "RULES_SERVER_API_KEY": "",
            "RULES_ADMIN_API_KEY": ADMIN_KEY,
        }),
        patch("rules_server.main.execute_agent_payment") as execute,
        TestClient(app) as client,
    ):
        response = client.post(
            URL,
            headers={"X-Service-Key": SERVICE_KEY},
            json=TRANSACTION,
        )

        assert response.status_code == 503
        execute.assert_not_called()
