import os
import secrets
from decimal import Decimal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from rules_server import policy
from rules_server.authorization import (
    authorize_invoice,
    mark_signed,
    release_signature,
    reserved_total_last_7_days,
)
from rules_server.registers import load_invoices
from rules_server.xrpl_verification import verify_xrpl_transaction

load_dotenv()

app = FastAPI(
    title="Imali Yethu Rules Server",
    description="Independent co-signer: approves a payment only if every rule passes. "
                "Spending limits are set by the CFO, never by the AI agent.",
)

class PaymentRequest(BaseModel):
    invoice_number: str
    supplier_id: str
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class PauseRequest(BaseModel):
    paused: bool


class CosignRequest(BaseModel):
    tx_json: dict


class PolicyUpdate(BaseModel):
    max_payment_zar: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    weekly_cap_zar: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    approved_suppliers: list[str] = Field(max_length=500)

    @field_validator("approved_suppliers")
    @classmethod
    def clean_suppliers(cls, value: list[str]) -> list[str]:
        cleaned = sorted({s.strip().upper() for s in value if s.strip()})
        for supplier_id in cleaned:
            if len(supplier_id) > 32 or not supplier_id.replace("-", "").isalnum():
                raise ValueError(f"Invalid supplier ID: {supplier_id!r}")
        return cleaned

    @model_validator(mode="after")
    def cap_not_below_single_payment(self):
        if self.weekly_cap_zar < self.max_payment_zar:
            raise ValueError("Weekly cap cannot be lower than the maximum single payment")
        return self


def _check_key(provided: str | None, env_name: str, label: str) -> None:
    expected = os.getenv(env_name)
    if not expected:
        raise HTTPException(status_code=503, detail=f"{label} authentication is not configured")
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail=f"Invalid {label.lower()} credentials")


def require_service_key(x_service_key: str | None = Header(default=None)):
    _check_key(x_service_key, "RULES_SERVER_API_KEY", "Service")


def require_admin_key(x_admin_key: str | None = Header(default=None)):
    """CFO-only. The agent holds RULES_SERVER_API_KEY, never this key."""
    admin_key = os.getenv("RULES_ADMIN_KEY")
    if admin_key and admin_key == os.getenv("RULES_SERVER_API_KEY"):
        # Fail closed: if the agent's key could change limits, the limits mean nothing.
        raise HTTPException(status_code=503, detail="Admin key must differ from the agent's service key")
    _check_key(x_admin_key, "RULES_ADMIN_KEY", "Admin")


@app.get("/")
def root():
    return {
        "service": "Imali Yethu Rules Server",
        "status": "running",
        "endpoints": {
            "health": "GET /health",
            "docs": "GET /docs",
            "validate": "POST /validate-payment",
            "authorize": "POST /authorize-payment (service key)",
            "verify": "POST /verify-xrpl-transaction (service key)",
            "cosign": "POST /cosign (service key): multisig co-signature after every check passes",
            "policy": "GET/PUT /policy (CFO admin key)",
            "pause": "POST /pause (CFO admin key)",
        },
    }


@app.get("/health")
def health():
    return {"status": "healthy", "service": "rules-server"}


@app.post("/validate-payment")
def validate_payment(payment: PaymentRequest):
    reasons = []
    current = policy.load_policy()

    if current.get("paused"):
        reasons.append("Payments are paused by the CFO")

    if payment.supplier_id not in set(current["approved_suppliers"]):
        reasons.append("Supplier is not approved")

    if payment.amount > Decimal(current["max_payment_zar"]):
        reasons.append("Payment exceeds the spending limit")

    if reserved_total_last_7_days() + payment.amount > Decimal(current["weekly_cap_zar"]):
        reasons.append("Payment would exceed the weekly spending cap")

    invoice = load_invoices().get(payment.invoice_number)

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

    return authorize_invoice(
        invoice_number=payment.invoice_number,
        supplier_id=payment.supplier_id,
        amount=str(payment.amount),
    )


@app.post(
    "/verify-xrpl-transaction",
    dependencies=[Depends(require_service_key)],
)
def verify_transaction(transaction: dict):
    return verify_xrpl_transaction(transaction)


@app.post(
    "/cosign",
    dependencies=[Depends(require_service_key)],
)
def cosign(request: CosignRequest):
    """Add the rules server's multisig signature to a fully autofilled payment.

    Signs only if: payments are not paused, the exact transaction matches the
    invoice register (supplier wallet, amount, memo, fee, flags), and the invoice
    was reserved through /authorize-payment and has not been signed before.
    """
    from xrpl.models.transactions import Payment
    from xrpl.transaction import sign
    from xrpl.wallet import Wallet

    tx_json = request.tx_json
    if policy.load_policy().get("paused"):
        return {"signed": False, "reasons": ["Payments are paused by the CFO"]}
    if "Signers" in tx_json or "TxnSignature" in tx_json:
        return {"signed": False, "reasons": ["Send the unsigned transaction"]}

    verification = verify_xrpl_transaction(tx_json, autofilled=True)
    if not verification["verified"]:
        return {"signed": False, "reasons": verification["reasons"]}

    seed = os.getenv("RULES_SERVER_SEED")
    if not seed:
        raise HTTPException(status_code=503, detail="Rules server signing key is not configured")

    invoice_number = verification["invoice_number"]
    if not mark_signed(invoice_number):
        return {"signed": False, "reasons": ["Invoice not reserved, or already co-signed"]}

    try:
        signed = sign(Payment.from_xrpl(tx_json), Wallet.from_seed(seed), multisign=True)
    except Exception:
        release_signature(invoice_number)
        raise HTTPException(status_code=500, detail="Signing failed")

    return {"signed": True, "invoice_number": invoice_number, "tx_json": signed.to_xrpl()}


@app.post("/pause", dependencies=[Depends(require_admin_key)])
def set_pause(request: PauseRequest):
    """Kill switch enforced here: a paused rules server refuses to approve or co-sign."""
    current = policy.load_policy()
    policy.save_policy({**current, "paused": request.paused})
    return {"paused": request.paused}


@app.get("/policy", dependencies=[Depends(require_admin_key)])
def get_policy():
    current = policy.load_policy()
    return {**current, "spent_last_7_days_zar": f"{reserved_total_last_7_days():.2f}"}


@app.put("/policy", dependencies=[Depends(require_admin_key)])
def put_policy(update: PolicyUpdate):
    saved = policy.save_policy({
        "max_payment_zar": f"{update.max_payment_zar:.2f}",
        "weekly_cap_zar": f"{update.weekly_cap_zar:.2f}",
        "approved_suppliers": update.approved_suppliers,
        "paused": bool(policy.load_policy().get("paused")),
    })
    return {"saved": True, "policy": saved}
