
import os
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

import streamlit as st

API_BASE_URL = os.getenv(
    "RULES_SERVER_URL", "http://127.0.0.1:8000"
).rstrip("/")

# Illustrative analytics only, not ledger records.
SEGMENTS = {
    "Infrastructure": 45,
    "Technology": 30,
    "Community Services": 15,
    "Other": 10,
}

st.set_page_config(
    page_title="Imali Yethu | CFO Dashboard",
    page_icon="🛡️",
    layout="wide",
)

st.title("Imali Yethu")
st.caption("CFO Oversight | Public Finance Accountability")

st.info(
    "DEMONSTRATION MODE: Financial metrics and procurement "
    "segments are illustrative. They are not verified "
    "municipal expenditure or XRPL ledger balances."
)


def api_request(path, payload=None, admin=False):
    url = f"{API_BASE_URL}{path}"
    body = None
    headers = {"Content-Type": "application/json"}

    if admin:
        admin_key = os.getenv("RULES_ADMIN_API_KEY")

        if not admin_key:
            return None, "Administrator credentials are not configured"

        headers["X-Admin-Key"] = admin_key

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = Request(
        url,
        data=body,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )

    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response), None
    except HTTPError as error:
        return None, f"API returned HTTP {error.code}"
    except (URLError, TimeoutError, ValueError) as error:
        return None, f"API unavailable: {type(error).__name__}"


with st.sidebar:
    st.header("Navigation")
    page = st.radio(
        "Select view",
        [
            "Overview",
            "Payment Review",
            "Market Segmentation",
            "Governance",
        ],
    )

    st.divider()
    health, health_error = api_request("/health")

    if health and health.get("status") == "healthy":
        st.success("Rules Server connected")
    else:
        st.error("Rules Server unavailable")

    st.caption("Local demonstration environment")


if page == "Overview":
    st.subheader("Financial Overview")

    overview_result, overview_error = api_request(
        "/admin/payment-history",
        admin=True,
    )

    if overview_error:
        st.warning(
            f"Recorded financial metrics unavailable: {overview_error}"
        )
    else:
        payments = overview_result.get("payments", [])

        validated = sum(
            payment["status"] == "validated"
            for payment in payments
        )

        other = len(payments) - validated

        total_value = sum(
            (
                Decimal(str(payment["amount"]))
                for payment in payments
            ),
            Decimal("0.00"),
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Recorded Invoices", len(payments))
        c2.metric("Validated Invoice Records", validated)
        c3.metric("Other Invoice Records", other)
        c4.metric(
            "Recorded Invoice Value",
            f"{total_value:,.2f}",
        )

        st.caption(
            "Figures represent up to 100 recorded demonstration "
            "invoices. Invoice values are business policy amounts, "
            "not XRP transferred or verified municipal expenditure."
        )

    st.subheader("Procurement Distribution")
    st.bar_chart(SEGMENTS, horizontal=True)

    st.subheader("System Capabilities")
    st.write(
        "Payment policy validation, authenticated invoice "
        "reservation, duplicate protection and XRPL "
        "transaction proposal verification."
    )

elif page == "Payment Review":
    st.subheader("Payment Policy Review")
    st.write(
        "Submit a payment proposal to the live Rules Server. "
        "This checks policy only; it does not reserve funds "
        "or submit an XRPL transaction."
    )

    with st.form("payment_review"):
        invoice = st.text_input(
            "Invoice Number",
            value="INV-2026-0001",
        )

        supplier = st.text_input(
            "Supplier ID",
            value="SUP-001",
        )

        amount = st.number_input(
            "Invoice Amount (demo policy units)",
            min_value=0.01,
            value=15000.00,
            step=100.00,
        )

        submitted = st.form_submit_button(
            "Validate Payment",
            type="primary",
        )

    if submitted:
        payload = {
            "invoice_number": invoice.strip(),
            "supplier_id": supplier.strip(),
            "amount": str(Decimal(str(amount)).quantize(
                Decimal("0.01")
            )),
        }

        result, error = api_request(
            "/validate-payment", payload
        )

        if error:
            st.error(error)
        elif result.get("approved"):
            st.success("Payment proposal passed policy checks.")
            st.json(result)
        else:
            st.error("Payment proposal rejected by policy.")
            for reason in result.get("reasons", []):
                st.warning(reason)

    st.divider()
    st.subheader("Recorded Payment History")
    st.caption(
        "Records from the local demonstration database. "
        "Invoice amounts are business policy amounts, not XRP."
    )

    history_result, history_error = api_request(
        "/admin/payment-history",
        admin=True,
    )

    if history_error:
        st.warning(f"Payment history unavailable: {history_error}")
    else:
        payments = history_result.get("payments", [])

        if not payments:
            st.info("No recorded invoice payments found.")
        else:
            st.metric("Recorded Invoices", len(payments))

            for payment in payments:
                invoice_number = payment["invoice_number"]
                status = payment["status"]

                with st.expander(
                    f"{invoice_number} | {status.upper()}"
                ):
                    st.write(
                        f"Supplier: {payment['supplier_id']}"
                    )
                    st.write(
                        f"Invoice amount: {payment['amount']} "
                        "(demo policy units)"
                    )
                    st.write(f"Current status: {status}")

                    events = payment.get("events", [])

                    if events:
                        st.subheader("Audit Events")

                        for event in events:
                            st.write(
                                f"{event['created_at']} ? "
                                f"{event['event_type']}"
                            )

                            if event.get("reason"):
                                st.caption(event["reason"])

                            tx_hash = event.get("transaction_hash")

                            if tx_hash:
                                st.code(tx_hash)

                                if event["event_type"] == "VALIDATED":
                                    st.success(
                                        "Recorded as validated. "
                                        "Confirm settlement on XRPL Testnet."
                                    )
                                    st.link_button(
                                        "View validated transaction",
                                        "https://testnet.xrpl.org/transactions/"
                                        + tx_hash,
                                    )
                                else:
                                    st.caption(
                                        "Transaction reference only. "
                                        "This audit event does not prove "
                                        "successful settlement."
                                    )
                                    st.link_button(
                                        "Inspect transaction reference",
                                        "https://testnet.xrpl.org/transactions/"
                                        + tx_hash,
                                    )
                    else:
                        st.info("No audit events recorded.")


elif page == "Market Segmentation":
    st.subheader("Procurement Market Segmentation")

    st.write(
        "Illustrative breakdown of municipal procurement "
        "categories, designed to show how expenditure "
        "could be monitored and compared."
    )

    st.bar_chart(SEGMENTS, horizontal=True)

    st.dataframe(
        [
            {"Sector": name, "Share (%)": value}
            for name, value in SEGMENTS.items()
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "These percentages are synthetic and do not "
        "represent actual municipal procurement records."
    )

elif page == "Governance":
    st.subheader("Payment Governance")

    st.write("Current demonstration policy:")

    policy_result, policy_error = api_request(
        "/admin/spending-limit",
        admin=True,
    )

    if policy_error:
        st.warning(
            f"Live spending policy unavailable: {policy_error}"
        )
        current_limit = "Unavailable"
    else:
        current_limit = (
            f"{policy_result['max_payment']} demo policy units"
        )
        st.success("Live spending policy retrieved from Rules Server")

    st.table(
        [
            {
                "Control": "Approved suppliers",
                "Policy": "SUP-001, SUP-002",
            },
            {
                "Control": "Maximum payment",
                "Policy": current_limit,
            },
            {
                "Control": "Registered invoice",
                "Policy": "INV-2026-0001",
            },
            {
                "Control": "Invoice amount",
                "Policy": "15,000.00 demo units",
            },
            {
                "Control": "Duplicate protection",
                "Policy": "SQLite invoice reservation",
            },
        ]
    )

    st.success(
        "XRPL Testnet demonstration: the treasury multisignature "
        "configuration and a successful payment transaction "
        "have been independently verified."
    )

    st.info(
        "The Rules Server enforces an independent spending limit "
        "before the demonstrated payment execution workflow. "
        "This prototype does not establish production readiness, "
        "full municipal approval workflows, or regulatory compliance."
    )
