
import os
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

import streamlit as st

API_BASE_URL = os.getenv(
    "RULES_SERVER_URL", "http://127.0.0.1:8001"
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


def api_request(path, payload=None):
    url = f"{API_BASE_URL}{path}"
    body = None
    headers = {"Content-Type": "application/json"}

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

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Proposed Spend", "R 245,000")
    c2.metric("Approved Proposals", "12")
    c3.metric("Flagged Proposals", "3")
    c4.metric("Suppliers Monitored", "8")

    st.caption(
        "All four figures above are illustrative placeholders."
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

    st.table(
        [
            {
                "Control": "Approved suppliers",
                "Policy": "SUP-001, SUP-002",
            },
            {
                "Control": "Maximum payment",
                "Policy": "50,000.00 demo units",
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

    st.warning(
        "Governance configuration is currently read-only. "
        "XRPL multisignature enforcement has not yet been "
        "verified against the intended approval policy."
    )
