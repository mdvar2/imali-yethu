"""Public-facing transparency dashboard for demonstration payments."""

import os

import requests
import streamlit as st


API_URL = os.getenv(
    "RULES_SERVER_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

st.set_page_config(
    page_title="Imali Yethu | Citizen Transparency",
    page_icon="??",
    layout="wide",
)

st.title("Imali Yethu")
st.subheader("Citizen Transparency Portal")

st.info(
    "XRPL Testnet demonstration. All invoices, suppliers and policy "
    "amounts are illustrative. No real municipal funds are involved."
)

st.markdown(
    "Explore recorded demonstration payments and inspect their "
    "XRPL Testnet transaction references."
)


@st.cache_data(ttl=30)
def fetch_public_payments(api_url):
    response = requests.get(
        f"{api_url}/public/payments",
        params={"limit": 100},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


try:
    payload = fetch_public_payments(API_URL)
    payments = payload.get("payments", [])
except requests.RequestException:
    st.error(
        "The public payment service is currently unavailable. "
        "Please try again later."
    )
    st.stop()

validated = sum(
    1 for payment in payments
    if payment.get("verification_status") == "recorded_validated"
)

unconfirmed = len(payments) - validated

col1, col2, col3 = st.columns(3)
col1.metric("Recorded invoices", len(payments))
col2.metric("Ledger-validated records", validated)
col3.metric("Not confirmed", unconfirmed)

st.divider()

st.subheader("Explore public payment records")

search = st.text_input(
    "Search invoice or supplier",
    placeholder="e.g. INV-2026-0001",
)

status_filter = st.selectbox(
    "Payment status",
    ["All", "validated", "submitted", "submitting", "reserved", "failed"],
)

filtered = []

for payment in payments:
    searchable = (
        f"{payment.get('invoice_number', '')} "
        f"{payment.get('supplier_id', '')}"
    ).lower()

    if search.lower().strip() not in searchable:
        continue

    if status_filter != "All" and payment.get("status") != status_filter:
        continue

    filtered.append(payment)

st.caption(f"Showing {len(filtered)} of {len(payments)} records")

if not filtered:
    st.warning("No payment records match your search.")
else:
    rows = []

    for payment in filtered:
        rows.append(
            {
                "Invoice": payment.get("invoice_number"),
                "Supplier": payment.get("supplier_id"),
                "Amount (demo units)": payment.get("amount"),
                "Status": payment.get("status"),
                "Verification": payment.get("verification_status"),
                "XRPL Testnet proof": payment.get("explorer_url") or "",
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "XRPL Testnet proof": st.column_config.LinkColumn(
                "XRPL Testnet proof",
                display_text="View transaction",
            )
        },
    )

st.divider()

st.subheader("Understanding payment verification")

st.markdown(
    """
    **Recorded:** An invoice exists in the demonstration database.

    **Validated:** The application recorded a successful XRPL validated-ledger
    check for the transaction.

    **Not confirmed:** A successful ledger validation has not been
    recorded for this payment.

    **Independent verification:** Open the XRPL Testnet transaction link
    to inspect the public ledger evidence yourself.
    """
)

st.caption(
    "This prototype does not represent a live municipal payment system. "
    "The invoice policy amount is not the amount of XRP transferred."
)
