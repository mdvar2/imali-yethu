import os
import secrets

from rules_server.cosigning import validate_agent_payment
from dotenv import load_dotenv
from rules_server.authorization import authorize_invoice, list_payment_history
from rules_server.xrpl_verification import verify_xrpl_transaction
from fastapi import Depends, Header, HTTPException
from decimal import Decimal
from fastapi import FastAPI
from pydantic import BaseModel, Field
from rules_server.spending_policy import (
    get_spending_limit,
    set_spending_limit,
)

from pathlib import Path

RULES_ENV = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "rules_server.env"
)

if not RULES_ENV.is_file():
    raise RuntimeError(
        "Missing config/rules_server.env"
    )

load_dotenv(dotenv_path=RULES_ENV, override=False)

app = FastAPI(title="Imali Yethu Rules Server")

# Demonstration policy only.
# Production policies must be stored securely and managed
# by authorised human operators, never by the AI agent.
APPROVED_SUPPLIERS = {"SUP-001", "SUP-002"}
APPROVED_INVOICES = {
    "INV-2026-0001": {
        "supplier_id": "SUP-001",
        "amount": Decimal("15000.00"),
    }
}


class PaymentRequest(BaseModel):
    invoice_number: str
    supplier_id: str
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


def require_service_key(
    x_service_key: str | None = Header(default=None),
):
    expected_key = os.getenv("RULES_SERVER_API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Rules server authentication is not configured",
        )

    if not x_service_key or not secrets.compare_digest(
        x_service_key, expected_key
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid service credentials",
        )



class SpendingLimitUpdate(BaseModel):
    max_payment: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


def require_admin_key(
    x_admin_key: str | None = Header(default=None),
):
    expected = os.getenv("RULES_ADMIN_API_KEY")
    service_key = os.getenv("RULES_SERVER_API_KEY")

    if not expected or not service_key or expected == service_key:
        raise HTTPException(
            status_code=503,
            detail="Independent administrator authentication is unavailable",
        )

    if not x_admin_key or not secrets.compare_digest(
        x_admin_key, expected
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid administrator credentials",
        )


@app.get(
    "/admin/spending-limit",
    dependencies=[Depends(require_admin_key)],
)
def read_spending_limit():
    return {"max_payment": str(get_spending_limit())}


@app.put(
    "/admin/spending-limit",
    dependencies=[Depends(require_admin_key)],
)
def update_spending_limit(request: SpendingLimitUpdate):
    limit = set_spending_limit(request.max_payment)

    return {
        "updated": True,
        "max_payment": str(limit),
    }


@app.get(
    "/admin/payment-history",
    dependencies=[Depends(require_admin_key)],
)
def read_payment_history():
    return {
        "payments": list_payment_history(limit=100),
    }


@app.get("/health")
def health():
    return {"status": "healthy", "service": "rules-server"}


@app.post("/validate-payment")
def validate_payment(payment: PaymentRequest):
    reasons = []

    if payment.supplier_id not in APPROVED_SUPPLIERS:
        reasons.append("Supplier is not approved")

    if payment.amount > get_spending_limit():
        reasons.append("Payment exceeds the spending limit")

    invoice = APPROVED_INVOICES.get(payment.invoice_number)

    if invoice is None:
        reasons.append("Invoice is not registered")
    else:
        if invoice["supplier_id"] != payment.supplier_id:
            reasons.append("Supplier does not match approved invoice")

        if invoice["amount"] != payment.amount:
            reasons.append("Amount does not match approved invoice")

    return {
        "approved": len(reasons) == 0,
        "invoice_number": payment.invoice_number,
        "reasons": reasons,
    }

@app.post(
    "/authorize-payment",
    dependencies=[Depends(require_service_key)],
)
def authorize_payment(payment: PaymentRequest):
    validation = validate_payment(payment)

    if not validation["approved"]:
        return {
            "authorized": False,
            "reasons": validation["reasons"],
        }

    result = authorize_invoice(
        invoice_number=payment.invoice_number,
        supplier_id=payment.supplier_id,
        amount=str(payment.amount),
    )

    return result


@app.post(
    "/verify-xrpl-transaction",
    dependencies=[Depends(require_service_key)],
)
def verify_transaction(transaction: dict):
    return verify_xrpl_transaction(transaction)

@app.post(
    "/validate-agent-payment",
    dependencies=[Depends(require_service_key)],
)
def validate_agent_transaction(transaction: dict):
    return validate_agent_payment(transaction)


from rules_server.execution import execute_agent_payment


@app.post(
    "/cosign",
    dependencies=[Depends(require_service_key)],
)
def cosign_agent_payment(transaction: dict):
    return execute_agent_payment(transaction)