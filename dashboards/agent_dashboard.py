"""
Agent monitor (CFO):  streamlit run dashboards/agent_dashboard.py

- See every decision the agent made (paid / blocked / why), with explorer links
- Pause or resume the agent
- View and change spending limits held by the rules server (outside the agent)
"""
import json
import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_PATH = DATA_DIR / "payments.jsonl"
CONTROL_PATH = DATA_DIR / "agent_control.json"
RULES_URL = os.getenv("RULES_SERVER_URL", "http://localhost:8000").rstrip("/")
# Separate admin key: the agent only has RULES_SERVER_API_KEY, so it cannot change limits.
RULES_ADMIN_KEY = os.getenv("RULES_ADMIN_KEY", "")

STATUS_LABELS = {
    "paid": "✅ Paid",
    "approved_dry_run": "🟦 Approved (dry run)",
    "blocked_by_agent": "⛔ Blocked by agent",
    "blocked_by_rules_server": "🛡️ Blocked by rules server",
    "paused": "⏸️ Agent paused",
    "failed": "⚠️ Failed",
}

st.set_page_config(page_title="Imali Yethu – Agent monitor", page_icon="🏛️", layout="wide")
st.title("Imali Yethu · Agent monitor")


def load_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    return [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def is_paused() -> bool:
    try:
        return bool(json.loads(CONTROL_PATH.read_text()).get("paused"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


payments_tab, limits_tab = st.tabs(["Payments", "Limits & controls"])

# ---------------------------------------------------------------- Payments
with payments_tab:
    records = load_log()
    if not records:
        st.info("No agent decisions yet. Run `python -m agent.run_agent data/sample_invoices/honest.txt`.")
    else:
        paid = sum(1 for r in records if r["status"] == "paid")
        blocked = sum(1 for r in records if r["status"].startswith("blocked"))
        total_paid = sum(float(r.get("amount_zar", 0)) for r in records if r["status"] == "paid")
        c1, c2, c3 = st.columns(3)
        c1.metric("Payments made", paid)
        c2.metric("Payments blocked", blocked)
        c3.metric("Total paid", f"R{total_paid:,.2f}")

        rows = [{
            "Time (UTC)": r["timestamp"],
            "Invoice": r.get("invoice_number", ""),
            "Supplier": r.get("supplier_name") or r.get("supplier_id", ""),
            "Amount (ZAR)": r.get("amount_zar", ""),
            "Status": STATUS_LABELS.get(r["status"], r["status"]),
            "Reasons": "; ".join(r.get("reasons", [])),
            "Ledger": r.get("explorer", ""),
        } for r in reversed(records)]
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={"Ledger": st.column_config.LinkColumn("Ledger", display_text="View on XRPL")},
        )

# ---------------------------------------------------------------- Limits
with limits_tab:
    st.subheader("Agent kill switch")
    paused = is_paused()
    st.write("The agent is currently **paused**." if paused else "The agent is currently **running**.")
    if st.button("Resume agent" if paused else "Pause agent", type="primary"):
        CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTROL_PATH.write_text(json.dumps({"paused": not paused}))
        st.rerun()

    privy_address = os.getenv("PRIVY_WALLET_ADDRESS")
    if privy_address:
        st.divider()
        st.subheader("Agent signing key (on-ledger)")
        from xrpl.clients import JsonRpcClient
        from xrpl.models.requests import AccountInfo
        from xrpl.models.transactions import SetRegularKey
        from xrpl.transaction import submit_and_wait
        from xrpl.wallet import Wallet

        client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
        treasury = os.environ["TREASURY_ADDRESS"]
        info = client.request(AccountInfo(account=treasury)).result.get("account_data", {})
        active = info.get("RegularKey") == privy_address
        st.write(
            f"The agent's Privy wallet `{privy_address}` **can** sign for the Treasury."
            if active else
            "The agent's signing key is **revoked**. The ledger will reject anything it signs."
        )
        st.caption("This is enforced by the XRP Ledger itself, not by the agent's code.")
        if st.button("Revoke agent key" if active else "Restore agent key"):
            # The CFO's master key signs this; the agent never has it in production.
            cfo = Wallet.from_seed(os.environ["TREASURY_SEED"])
            tx = SetRegularKey(account=treasury, regular_key=None if active else privy_address)
            res = submit_and_wait(tx, client, cfo)
            st.toast(f"{res.result['meta']['TransactionResult']}: {res.result['hash'][:12]}…")
            st.rerun()

    st.divider()
    st.subheader("Spending limits (held by the rules server)")
    st.caption("The agent cannot read or change these. Only this dashboard, with the rules server key, can.")

    try:
        resp = requests.get(f"{RULES_URL}/policy", headers={"X-Admin-Key": RULES_ADMIN_KEY}, timeout=5)
    except requests.RequestException:
        st.error(f"Rules server not reachable at {RULES_URL}.")
        st.stop()

    if resp.status_code == 404:
        st.warning(
            "The rules server doesn't expose a `/policy` endpoint yet, so limits are still "
            "hardcoded in `rules_server/main.py` (max payment R50,000; approved suppliers "
            "SUP-001, SUP-002). See `docs/integration-contract.md` for the endpoint this "
            "page expects."
        )
        st.stop()

    resp.raise_for_status()
    policy = resp.json()

    with st.form("policy"):
        max_payment = st.number_input("Max per payment (ZAR)", min_value=0.0, step=1000.0,
                                      value=float(policy.get("max_payment_zar", 0)))
        weekly_cap = st.number_input("Weekly cap (ZAR)", min_value=0.0, step=1000.0,
                                     value=float(policy.get("weekly_cap_zar", 0)))
        suppliers = st.text_input("Approved suppliers (comma separated)",
                                  value=", ".join(policy.get("approved_suppliers", [])))
        if st.form_submit_button("Save limits"):
            new_policy = {
                "max_payment_zar": f"{max_payment:.2f}",
                "weekly_cap_zar": f"{weekly_cap:.2f}",
                "approved_suppliers": [s.strip() for s in suppliers.split(",") if s.strip()],
            }
            put = requests.put(f"{RULES_URL}/policy", json=new_policy,
                               headers={"X-Admin-Key": RULES_ADMIN_KEY}, timeout=5)
            if put.ok:
                st.success("Limits saved on the rules server.")
            else:
                st.error(f"Rules server refused the change ({put.status_code}): {put.text}")
