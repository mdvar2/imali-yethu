"""Security tests for human-controlled spending policies."""

from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from rules_server.main import app


ADMIN_KEY = "test-human-admin-secret"
SERVICE_KEY = "test-agent-service-secret"
URL = "/admin/spending-limit"


def test_admin_spending_limit_access_control():
    with (
        patch.dict(
            "os.environ",
            {
                "RULES_ADMIN_API_KEY": ADMIN_KEY,
                "RULES_SERVER_API_KEY": SERVICE_KEY,
                "ENABLE_TESTNET_PAYMENTS": "false",
            },
        ),
        patch(
            "rules_server.main.get_spending_limit",
            return_value=Decimal("50000.00"),
        ),
        TestClient(app) as client,
    ):
        assert client.get(URL).status_code == 401

        assert client.get(
            URL,
            headers={"X-Admin-Key": SERVICE_KEY},
        ).status_code == 401

        response = client.get(
            URL,
            headers={"X-Admin-Key": ADMIN_KEY},
        )
        assert response.status_code == 200
        assert response.json()["max_payment"] == "50000.00"


def test_agent_cannot_change_spending_limit():
    with (
        patch.dict(
            "os.environ",
            {
                "RULES_ADMIN_API_KEY": ADMIN_KEY,
                "RULES_SERVER_API_KEY": SERVICE_KEY,
            },
        ),
        patch("rules_server.main.set_spending_limit") as update,
        TestClient(app) as client,
    ):
        response = client.put(
            URL,
            headers={"X-Admin-Key": SERVICE_KEY},
            json={"max_payment": "1000.00"},
        )

        assert response.status_code == 401
        update.assert_not_called()


def test_authorized_human_can_change_spending_limit():
    with (
        patch.dict(
            "os.environ",
            {
                "RULES_ADMIN_API_KEY": ADMIN_KEY,
                "RULES_SERVER_API_KEY": SERVICE_KEY,
            },
        ),
        patch(
            "rules_server.main.set_spending_limit",
            return_value=Decimal("1000.00"),
        ) as update,
        TestClient(app) as client,
    ):
        response = client.put(
            URL,
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"max_payment": "1000.00"},
        )

        assert response.status_code == 200
        assert response.json()["max_payment"] == "1000.00"
        update.assert_called_once_with(Decimal("1000.00"))


def test_admin_key_must_differ_from_service_key():
    with (
        patch.dict(
            "os.environ",
            {
                "RULES_ADMIN_API_KEY": SERVICE_KEY,
                "RULES_SERVER_API_KEY": SERVICE_KEY,
            },
        ),
        TestClient(app) as client,
    ):
        response = client.get(
            URL,
            headers={"X-Admin-Key": SERVICE_KEY},
        )

        assert response.status_code == 503
