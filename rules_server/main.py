import os
import secrets

from fastapi import Depends, Header, HTTPException
from rules_server.authorization import authorize_invoice
from decimal import Decimal
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Imali Yethu Rules Server")

# Demonstration policy only.
# Production policies must be stored securely and managed
# by authorised human operators, never by the AI agent.
APPROVED_SUPPLIERS = {"SUP-001", "SUP-002"}
MAX_PAYMENT = Decimal("50000.00")
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


@app.get("/health")
def health():
    return {"status": "healthy", "service": "rules-server"}


@app.post("/validate-payment")
def validate_payment(payment: PaymentRequest):
    reasons = []

    if payment.supplier_id not in APPROVED_SUPPLIERS:
        reasons.append("Supplier is not approved")

    if payment.amount > MAX_PAYMENT:
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

