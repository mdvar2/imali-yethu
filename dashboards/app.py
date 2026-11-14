"""
Imali Yethu: Municipal Payment Integrity dashboard.

    streamlit run dashboards/app.py

One app for the CFO's office (oversight, invoice checks, controls) and for
citizens (public transparency page). All figures come from the agent's
decision log, the supplier and price registers, and the live rules server.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402
import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from agent.price_check import MAX_MARKUP  # noqa: E402
from dashboards import auth, core, theme  # noqa: E402

load_dotenv(ROOT / ".env")
# On Streamlit Community Cloud, settings come from st.secrets instead of .env.
try:
    for _key, _value in st.secrets.items():
        if isinstance(_value, (str, int, float, bool)):
            os.environ.setdefault(_key, str(_value))
except Exception:  # no secrets file locally: .env is used
    pass
RULES_URL = os.getenv("RULES_SERVER_URL", "http://localhost:8000").rstrip("/")
# Separate admin key: the agent only has RULES_SERVER_API_KEY, so it cannot change limits.
RULES_ADMIN_KEY = os.getenv("RULES_ADMIN_KEY", "")
PRIVY_ADDRESS = os.getenv("PRIVY_WALLET_ADDRESS", "")


# ======================================================================
# Live checks (cached briefly so the UI stays fast)
# ======================================================================
@st.cache_data(ttl=15, show_spinner=False)
def rules_server_online(url: str) -> bool:
    try:
        return requests.get(f"{url}/health", timeout=2).json().get("status") == "healthy"
    except (requests.RequestException, ValueError):
        return False


@st.cache_data(ttl=20, show_spinner=False)
def agent_key_active(treasury: str, privy_address: str) -> bool | None:
    """True if the agent's Privy wallet can sign for the Treasury. None if unknown."""
    try:
        from xrpl.clients import JsonRpcClient
        from xrpl.models.requests import AccountInfo

        client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
        info = client.request(AccountInfo(account=treasury)).result.get("account_data", {})
        return info.get("RegularKey") == privy_address
    except Exception:  # network or config problems: show "unknown", never crash the page
        return None


@st.cache_data(ttl=60, show_spinner=False)
def ledger_payments(treasury: str) -> list[dict] | None:
    """Invoice payments from the Treasury, read from the XRP Ledger. None if unreachable."""
    try:
        from xrpl.clients import JsonRpcClient
        from xrpl.models.requests import AccountTx

        client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
        result = client.request(AccountTx(account=treasury, limit=200)).result
        return core.parse_ledger_payments(result.get("transactions", []), treasury,
                                          core.supplier_wallets(), core.invoice_supplier_names())
    except Exception:  # network problems: the page falls back to the local record
        return None


def fetch_policy() -> tuple[dict | None, str]:
    """Returns (policy, state). state: ok | missing | unauthorised | offline | error."""
    try:
        resp = requests.get(f"{RULES_URL}/policy", headers={"X-Admin-Key": RULES_ADMIN_KEY}, timeout=4)
    except requests.RequestException:
        return None, "offline"
    if resp.status_code == 404:
        return None, "missing"
    if resp.status_code in (401, 403):
        return None, "unauthorised"
    if not resp.ok:
        return None, "error"
    try:
        return resp.json(), "ok"
    except ValueError:
        return None, "error"


# ======================================================================
# Charts
# ======================================================================
def _hbar(df: pd.DataFrame, label: str, value: str, colors: list[str] | None = None,
          color: str = theme.TONE_HEX["brand"]) -> alt.LayerChart:
    order = df.sort_values(value, ascending=False)[label].tolist()
    enc_color = (alt.Color(f"{label}:N", scale=alt.Scale(domain=df[label].tolist(), range=colors), legend=None)
                 if colors else alt.value(color))
    base = alt.Chart(df).encode(
        y=alt.Y(f"{label}:N", sort=order, title=None, axis=alt.Axis(labelLimit=220, labelFontSize=12)),
        x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d", grid=True)),
    )
    bars = base.mark_bar(cornerRadiusEnd=4, size=20).encode(
        color=enc_color, tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip(f"{value}:Q")])
    text = base.mark_text(align="left", dx=6, fontWeight=600, color="#14213D").encode(text=f"{value}:Q")
    return (bars + text).properties(height=max(120, 38 * len(df) + 30))


def outcome_chart(records: list[dict]) -> alt.LayerChart:
    counts = core.outcome_counts(records)
    rows = [{"Outcome": core.status_of(code).label, "Invoices": n,
             "_c": theme.TONE_HEX[core.status_of(code).tone]} for code, n in counts.items()]
    df = pd.DataFrame(rows)
    return _hbar(df, "Outcome", "Invoices", colors=df["_c"].tolist())


def reasons_chart(counts: dict[str, int]) -> alt.LayerChart:
    df = pd.DataFrame([{"Reason": k, "Invoices": v} for k, v in counts.items()])
    return _hbar(df, "Reason", "Invoices", color=theme.TONE_HEX["bad"])


# ======================================================================
# Pages
# ======================================================================
def overview() -> None:
    theme.page_header(
        "Overview",
        "How the AI payment agent has handled the municipality's invoices, and how much money it stopped "
        "from leaving the Treasury.",
        section="Oversight",
    )
    records = core.load_records()
    suppliers = core.load_suppliers()
    if not records:
        theme.empty_state("No invoices processed yet",
                          "Decisions appear here as soon as the agent reviews its first invoice.",
                          "python -m agent.run_agent data/sample_invoices/honest.txt")
        return

    s = core.summarise(records)
    theme.kpi_row([
        ("Paid to suppliers", core.fmt_zar(s["paid_value"]),
         f'{s["paid_count"]} payment{"s" * (s["paid_count"] != 1)} settled on the ledger', "ok", "paid"),
        ("Value stopped", core.fmt_zar(s["blocked_value"]),
         f'{s["blocked_count"]} invoice{"s" * (s["blocked_count"] != 1)} blocked before payment', "bad", "shield"),
        ("Invoices reviewed", f'{s["reviewed"]}', f'{s["block_rate"]:.0%} were blocked', "info", "doc"),
        ("Tampering attempts stopped", f'{s["tampering"]}', "Hidden instructions or a wrong wallet", "warn", "alert"),
    ])
    st.write("")

    left, right = st.columns([1, 1], gap="medium")
    with left, st.container(border=True):
        theme.section("Decisions by outcome", "Every invoice the agent has processed")
        st.altair_chart(outcome_chart(records))
    with right, st.container(border=True):
        theme.section("Why invoices were blocked", "Each blocked invoice counted once per reason")
        counts = core.block_reason_counts(records)
        if counts:
            st.altair_chart(reasons_chart(counts))
        else:
            theme.empty_state("Nothing blocked", "No invoice has failed a check yet.")

    with st.container(border=True):
        theme.section("Latest activity",
                      "The five most recent decisions. Open the Payments register for the full record.")
        theme.activity_table(list(reversed(records[-5:])), suppliers)


def payments() -> None:
    theme.page_header(
        "Payments register",
        "Every decision the agent made, why it made it, and a link to verify each payment on the public ledger.",
        section="Oversight",
    )
    records = core.load_records()
    suppliers = core.load_suppliers()
    if not records:
        theme.empty_state("The register is empty", "No invoices have been processed yet.")
        return

    newest_first = list(reversed(records))
    status_options = list(dict.fromkeys(core.status_of(r.get("status")).label for r in newest_first))
    supplier_options = sorted({core.supplier_name(r, suppliers) for r in newest_first})

    c1, c2, c3 = st.columns([2, 2, 3])
    chosen_status = c1.multiselect("Outcome", status_options, placeholder="All outcomes")
    chosen_supplier = c2.selectbox("Supplier", ["All suppliers", *supplier_options])
    query = c3.text_input("Search", placeholder="Invoice number or reason, e.g. INV-2026-0001")

    q = query.strip().lower()
    shown = [
        r for r in newest_first
        if (not chosen_status or core.status_of(r.get("status")).label in chosen_status)
        and (chosen_supplier == "All suppliers" or core.supplier_name(r, suppliers) == chosen_supplier)
        and (not q or q in (r.get("invoice_number") or "").lower()
             or any(q in reason.lower() for reason in r.get("reasons") or []))
    ]

    table = pd.DataFrame([{
        "Date (SAST)": core.fmt_time(r.get("timestamp")),
        "Invoice": r.get("invoice_number") or "-",
        "Supplier": core.supplier_name(r, suppliers),
        "Amount": core.fmt_zar(core.amount(r)),
        "Outcome": core.status_of(r.get("status")).label,
        "Ledger": core.explorer_link(r),
        "Main reason": (r.get("reasons") or [""])[0],
    } for r in shown], columns=["Date (SAST)", "Invoice", "Supplier", "Amount", "Outcome", "Ledger", "Main reason"])

    with st.container(border=True):
        theme.section(f"{len(shown)} of {len(records)} decisions",
                      "Select a row to see its full decision trail.")
        event = st.dataframe(
            table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
            key="payments_table",
            column_config={
                "Main reason": st.column_config.TextColumn(width="large"),
                "Ledger": st.column_config.LinkColumn("Ledger", display_text="Verify ↗", width="small"),
            },
        )
        st.download_button("Export CSV", table.to_csv(index=False).encode("utf-8"),
                           file_name="imali_yethu_payments.csv", mime="text/csv",
                           icon=":material/download:", disabled=table.empty)

    rows = event.selection.rows if event and event.selection else []
    if rows and rows[0] < len(shown):
        _payment_detail(shown[rows[0]], suppliers)


def _payment_detail(record: dict, suppliers: dict[str, str]) -> None:
    status = core.status_of(record.get("status"))
    with st.container(border=True):
        info, steps = st.columns([2, 3], gap="large")
        with info:
            theme.section(f'Invoice {record.get("invoice_number") or "-"}', core.supplier_name(record, suppliers))
            st.markdown(theme.pill(record.get("status")), unsafe_allow_html=True)
            st.write("")
            st.metric("Amount", core.fmt_zar(core.amount(record)))
            st.caption(f'Decided {core.fmt_time(record.get("timestamp"))} SAST')
            st.caption(status.description)
            if record.get("simulated_compromise"):
                theme.note("Demo scenario: the agent was deliberately compromised to show that the "
                           "independent rules server still protects the Treasury.", "warn")
            link = core.explorer_link(record)
            if link:
                st.link_button("Verify on the XRP Ledger", link, icon=":material/open_in_new:")
        with steps:
            theme.section("Decision trail", "Each control the invoice passed through, in order")
            theme.trail(core.decision_trail(record))


def invoice_check() -> None:
    theme.page_header(
        "Invoice check",
        "Check a supplier invoice against the municipality's payment policy before it is processed, "
        "and look up the market prices the agent uses.",
        section="Oversight",
    )
    precheck_tab, prices_tab = st.tabs(["Policy pre-check", "Market price benchmarks"])

    with precheck_tab:
        suppliers = core.load_suppliers()
        online = rules_server_online(RULES_URL)
        if not online:
            theme.note(f"The rules server is not reachable at {RULES_URL}. Start it with "
                       "uvicorn rules_server.main:app --port 8000 to run checks.", "warn")

        form_col, result_col = st.columns([2, 3], gap="large")
        with form_col, st.container(border=True):
            theme.section("Invoice details", "This only checks policy. It does not reserve the invoice or move money.")
            with st.form("precheck", border=False):
                invoice = st.text_input("Invoice number", value="INV-2026-0001")
                supplier = st.selectbox("Supplier", list(suppliers),
                                        format_func=lambda k: f"{suppliers[k]} ({k})")
                total = st.number_input("Invoice total (ZAR)", min_value=0.01, value=15000.00,
                                        step=500.0, format="%.2f")
                submitted = st.form_submit_button("Run policy check", type="primary",
                                                  disabled=not online, icon=":material/fact_check:")

        with result_col, st.container(border=True):
            theme.section("Result", "Checks performed by the independent rules server")
            if not submitted:
                theme.empty_state("No check run yet", "Enter the invoice details and select Run policy check.")
            else:
                payload = {"invoice_number": invoice.strip(), "supplier_id": supplier,
                           "amount": f"{total:.2f}"}
                try:
                    resp = requests.post(f"{RULES_URL}/validate-payment", json=payload, timeout=5)
                    resp.raise_for_status()
                    result = resp.json()
                except (requests.RequestException, ValueError) as exc:
                    st.error(f"The rules server could not be reached ({type(exc).__name__}).")
                else:
                    approved = bool(result.get("approved"))
                    theme.verdict(approved,
                                  "Meets payment policy" if approved else "Does not meet payment policy",
                                  "The agent may proceed to price and delivery checks." if approved
                                  else "The rules server would refuse to approve this payment.")
                    theme.checklist(core.policy_checklist(result.get("reasons", [])))

    with prices_tab, st.container(border=True):
        limit_pct = int(MAX_MARKUP * 100)
        theme.section("Market price benchmarks",
                      f"Any line item priced more than {limit_pct}% above the market price is blocked "
                      "automatically. This check is plain code, not AI.")
        prices = core.load_prices()
        st.dataframe(
            pd.DataFrame([{
                "Item": core.pretty_item(k),
                "Market price": core.fmt_zar(v),
                f"Highest accepted (+{limit_pct}%)": core.fmt_zar(v * (1 + MAX_MARKUP)),
            } for k, v in prices.items()]),
            hide_index=True, width="stretch",
        )
        st.caption("Sample price list for the pilot. In production this would be fed from National Treasury "
                   "transversal contract prices and recent municipal purchases.")


LSF_DISABLE_MASTER = 0x00100000
SIGNER_ROLES = {"AGENT_ADDRESS": "AI agent", "RULES_SERVER_ADDRESS": "Rules server",
                "CFO_ADDRESS": "CFO", "MUNICIPAL_MANAGER_ADDRESS": "Municipal Manager"}


@st.cache_data(ttl=30, show_spinner=False)
def treasury_governance(treasury: str) -> dict | None:
    """Signer list and master-key state of the Treasury, from the ledger. None if unreachable."""
    try:
        from xrpl.clients import JsonRpcClient
        from xrpl.models.requests import AccountInfo

        client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
        result = client.request(AccountInfo(account=treasury, signer_lists=True)).result
        data = result["account_data"]
        lists = result.get("signer_lists") or data.get("signer_lists") or []
        names = {os.getenv(k): v for k, v in SIGNER_ROLES.items() if os.getenv(k)}
        signers = [(names.get(e["SignerEntry"]["Account"], e["SignerEntry"]["Account"]),
                    e["SignerEntry"]["SignerWeight"])
                   for lst in lists for e in lst.get("SignerEntries", [])]
        return {
            "quorum": lists[0]["SignerQuorum"] if lists else None,
            "signers": signers,
            "master_disabled": bool(data.get("Flags", 0) & LSF_DISABLE_MASTER),
        }
    except Exception:  # network or config problems: show "unknown", never crash the page
        return None


def _governance_card() -> None:
    treasury = os.getenv("TREASURY_ADDRESS", "")
    gov = treasury_governance(treasury) if treasury and os.getenv("XRPL_RPC_URL") else None
    if gov is None:
        st.markdown(theme.pill_text("Status unknown", "warn"), unsafe_allow_html=True)
        st.caption("The XRP Ledger could not be reached. Try again shortly.")
        return
    if gov["quorum"] and gov["master_disabled"]:
        st.markdown(theme.pill_text("Multisig enforced by the ledger", "ok"), unsafe_allow_html=True)
        st.caption("The agent cannot move money alone: the rules server must co-sign every payment.")
    elif gov["quorum"]:
        st.markdown(theme.pill_text("Multisig set, master key still enabled", "warn"), unsafe_allow_html=True)
        st.caption("Disable the master key to make the signer list the only way to pay: "
                   "python scripts/setup_multisig.py --apply --disable-master")
    else:
        st.markdown(theme.pill_text("Single key: not yet enforced", "bad"), unsafe_allow_html=True)
        st.caption("The Treasury still signs with one key. Run python scripts/setup_multisig.py to see the plan.")
    if gov["signers"]:
        st.dataframe(pd.DataFrame([{"Signer": name, "Weight": weight} for name, weight in gov["signers"]]),
                     hide_index=True, width="stretch")
        st.caption(f"{gov['quorum']} signature weight needed to move money.")


def _set_server_pause(paused: bool) -> bool:
    try:
        resp = requests.post(f"{RULES_URL}/pause", json={"paused": paused},
                             headers={"X-Admin-Key": RULES_ADMIN_KEY}, timeout=4)
        return resp.ok
    except requests.RequestException:
        return False


def controls() -> None:
    theme.page_header(
        "Controls & limits",
        "Human controls that sit outside the AI agent. The agent cannot read or change anything on this page.",
        section="Governance",
    )
    if auth.role() != "cfo":  # defence in depth: navigation already hides this page
        st.error("Only the CFO can view controls and limits.")
        return
    kill_col, gov_col = st.columns(2, gap="medium")

    with kill_col, st.container(border=True):
        theme.section("Kill switch", "Stops all payments. Enforced by the rules server, so it holds even if "
                                     "the agent ignores it.")
        policy, state = fetch_policy() if rules_server_online(RULES_URL) else (None, "offline")
        server_paused = bool(policy and policy.get("paused"))
        paused = core.agent_paused() or server_paused
        st.markdown(theme.pill_text("Payments paused" if paused else "Payments running",
                                    "muted" if paused else "ok"), unsafe_allow_html=True)
        st.write("")
        if st.button("Resume payments" if paused else "Pause all payments", type="primary",
                     icon=":material/play_circle:" if paused else ":material/pause_circle:"):
            ok = _set_server_pause(not paused)
            core.set_agent_paused(not paused)
            if ok:
                st.toast("Payments resumed" if paused else "All payments paused, on the agent and the rules server.")
            else:
                st.toast("Agent flag changed, but the rules server could not be reached.", icon="⚠️")
            st.rerun()
        if state != "ok":
            st.caption("The rules server is not reachable, so only the agent's own pause flag can be changed.")
        st.caption("Every change is written to the audit trail below.")

    with gov_col, st.container(border=True):
        theme.section("Treasury signing rules", "Read live from the XRP Ledger: who must sign before money moves.")
        _governance_card()

    treasury = os.getenv("TREASURY_ADDRESS", "")
    if PRIVY_ADDRESS and treasury:
        with st.container(border=True):
            theme.section("Agent signing key (Privy)", "Whether the XRP Ledger accepts transactions signed by the agent.")
            active = agent_key_active(treasury, PRIVY_ADDRESS)
            if active is None:
                st.markdown(theme.pill_text("Status unknown", "warn"), unsafe_allow_html=True)
                st.caption("The XRP Ledger could not be reached. Try again shortly.")
            else:
                st.markdown(theme.pill_text("Can sign" if active else "Revoked", "ok" if active else "bad"),
                            unsafe_allow_html=True)
                st.write("")
                if st.button("Revoke agent key" if active else "Restore agent key",
                             icon=":material/key_off:" if active else ":material/key:"):
                    _confirm_key_change(active, treasury)
                st.caption("Enforced by the XRP Ledger itself, not by the agent's code.")

    with st.container(border=True):
        theme.section("Spending limits", "Held by the independent rules server. Changes need the CFO admin key.")
        _limits_panel()

    with st.container(border=True):
        theme.section("Audit trail", "Every control change made from this dashboard")
        audit = core.load_audit()
        if not audit:
            st.caption("No changes recorded yet.")
        else:
            st.dataframe(pd.DataFrame([{
                "Date (SAST)": core.fmt_time(a.get("timestamp")),
                "Action": a.get("action", ""),
                "By": a.get("actor", ""),
                "Detail": a.get("detail", ""),
            } for a in reversed(audit)]), hide_index=True, width="stretch")


@st.dialog("Confirm signing key change")
def _confirm_key_change(active: bool, treasury: str) -> None:
    if active:
        st.write("Revoking the key means the XRP Ledger will **reject every transaction the agent signs** "
                 "until the key is restored. Payments in progress will stop.")
    else:
        st.write("Restoring the key lets the agent sign Treasury payments again, within its Privy policy.")
    if st.button("Revoke key" if active else "Restore key", type="primary"):
        from xrpl.clients import JsonRpcClient
        from xrpl.models.transactions import SetRegularKey
        from xrpl.transaction import submit_and_wait
        from xrpl.wallet import Wallet

        try:
            client = JsonRpcClient(os.environ["XRPL_RPC_URL"])
            # Demo: the Treasury master key signs this. In production a CFO-held key would.
            cfo = Wallet.from_seed(os.environ["TREASURY_SEED"])
            tx = SetRegularKey(account=treasury, regular_key=None if active else PRIVY_ADDRESS)
            res = submit_and_wait(tx, client, cfo)
        except Exception as exc:
            st.error(f"The ledger did not accept the change ({type(exc).__name__}).")
            return
        code, tx_hash = res.result["meta"]["TransactionResult"], res.result["hash"]
        core.append_audit("Agent key revoked" if active else "Agent key restored",
                          f"{code} · {core.EXPLORER_TX}{tx_hash}")
        agent_key_active.clear()
        st.rerun()


def _limits_panel() -> None:
    policy, state = fetch_policy() if rules_server_online(RULES_URL) else (None, "offline")
    if state == "offline":
        theme.note(f"The rules server is not reachable at {RULES_URL}.", "warn")
        return
    if state == "unauthorised":
        theme.note("The rules server rejected the admin key. Check RULES_ADMIN_KEY in .env.", "warn")
        return
    if state == "error":
        theme.note("The rules server returned an unexpected response.", "warn")
        return
    if state == "missing":
        theme.note("This rules server is running an older version without the /policy endpoint. "
                   "Restart it (uvicorn rules_server.main:app --port 8000) to manage limits here.", "warn")
        return

    spent = Decimal(str(policy.get("spent_last_7_days_zar", "0")))
    cap = Decimal(str(policy.get("weekly_cap_zar", "0")))
    used = float(spent / cap) if cap else 0.0
    st.progress(min(used, 1.0), text=f"Spent in the last 7 days: {core.fmt_zar(spent)} of "
                                     f"{core.fmt_zar(cap)} weekly cap ({used:.0%})")

    with st.form("policy", border=False):
        c1, c2 = st.columns(2)
        max_payment = c1.number_input("Maximum per payment (ZAR)", min_value=0.0, step=1000.0, format="%.2f",
                                      value=float(policy.get("max_payment_zar", 0)))
        weekly_cap = c2.number_input("Weekly cap (ZAR)", min_value=0.0, step=1000.0, format="%.2f",
                                     value=float(policy.get("weekly_cap_zar", 0)))
        suppliers = st.text_input("Approved supplier IDs (comma separated)",
                                  value=", ".join(policy.get("approved_suppliers", [])))
        if st.form_submit_button("Save limits", type="primary", icon=":material/save:"):
            new_policy = {
                "max_payment_zar": f"{max_payment:.2f}",
                "weekly_cap_zar": f"{weekly_cap:.2f}",
                "approved_suppliers": [s.strip() for s in suppliers.split(",") if s.strip()],
            }
            try:
                put = requests.put(f"{RULES_URL}/policy", json=new_policy,
                                   headers={"X-Admin-Key": RULES_ADMIN_KEY}, timeout=5)
            except requests.RequestException:
                st.error("The rules server could not be reached.")
                return
            if put.ok:
                core.append_audit("Spending limits changed",
                                  f"Max R{new_policy['max_payment_zar']}, weekly R{new_policy['weekly_cap_zar']}, "
                                  f"suppliers {', '.join(new_policy['approved_suppliers'])}")
                st.success("Limits saved on the rules server. They apply to the next payment.")
            else:
                try:
                    detail = put.json().get("detail")
                    if isinstance(detail, list):
                        detail = "; ".join(str(d.get("msg", d)).removeprefix("Value error, ") for d in detail)
                except ValueError:
                    detail = None
                st.error(f"The rules server refused the change: {detail or f'HTTP {put.status_code}'}")


def public_ledger() -> None:
    theme.page_header(
        "Where our money goes",
        "A public record of every payment the municipality has made through Imali Yethu. "
        "Anyone can check each payment independently on the XRP Ledger.",
        section="Public",
    )
    records = core.load_records()
    s = core.summarise(records)
    treasury = os.getenv("TREASURY_ADDRESS", "")
    ledger = ledger_payments(treasury) if treasury and os.getenv("XRPL_RPC_URL") else None

    if ledger is not None:
        paid_rows = [{
            "Date (SAST)": core.fmt_time(p["timestamp"]),
            "Paid to": p["supplier"],
            "Invoice": p["invoice_number"],
            "Amount": f'{core.fmt_zar(p["zar"])}  ({p["xrp"]:,.2f} XRP)',
            "Signed by": "Agent + rules server" if p["multisigned"] else "Single key",
            "Public record": core.EXPLORER_TX + p["hash"],
        } for p in ledger]
        paid_value = sum((p["zar"] for p in ledger), Decimal("0"))
        source = "Read live from the XRP Ledger, not from our database."
    else:
        suppliers = core.load_suppliers()
        paid_rows = [{
            "Date (SAST)": core.fmt_time(r.get("timestamp")),
            "Paid to": core.supplier_name(r, suppliers),
            "Invoice": r.get("invoice_number") or "-",
            "Amount": core.fmt_zar(core.amount(r)),
            "Public record": core.explorer_link(r),
        } for r in reversed(records) if r.get("status") == "paid"]
        paid_value = s["paid_value"]
        source = "The XRP Ledger could not be reached, so this shows the agent's local record."

    theme.kpi_row([
        ("Paid to suppliers", core.fmt_zar(paid_value), "Settled and publicly verifiable", "ok", "paid"),
        ("Payments", f"{len(paid_rows)}", "Each linked to its ledger record", "info", "count"),
        ("Stopped before payment", core.fmt_zar(s["blocked_value"]),
         f'{s["blocked_count"]} invoice{"s" * (s["blocked_count"] != 1)} failed a check', "bad", "shield"),
    ])
    st.write("")

    with st.container(border=True):
        theme.section("Payments made", f"Newest first. {source}")
        if not paid_rows:
            theme.empty_state("No payments yet", "Payments appear here as soon as they settle on the ledger.")
        else:
            st.dataframe(pd.DataFrame(paid_rows), hide_index=True, width="stretch", column_config={
                "Public record": st.column_config.LinkColumn(display_text="Verify on XRP Ledger ↗"),
            })
        st.caption("Amounts in rand use the pilot's fixed demonstration rate of R1,500 per XRP.")

    with st.expander("How to read this page"):
        st.markdown(
            "1. **Every payment is checked before it is made.** An AI agent compares prices with the market, "
            "and an independent rules server checks the supplier, the amount and the spending limits.\n"
            "2. **Payments are recorded on a public ledger.** Select *Verify on XRP Ledger* to see the "
            "payment's permanent record. Nobody, including the municipality, can edit or delete it.\n"
            "3. **Stopped invoices are shown as totals.** Supplier details of blocked invoices stay private "
            "until an investigation is complete.\n"
            "4. **Personal information is never published.** Company directors' details stay off the ledger, "
            "in line with POPIA."
        )


SAMPLES_DIR = ROOT / "data" / "sample_invoices"
SAMPLE_LABELS = {
    "honest.txt": "Laptop, correct price (INV-2026-0001)",
    "chairs.txt": "Office chairs (INV-2026-0003)",
    "toner.txt": "Toner cartridges (INV-2026-0004)",
    "inflated.txt": "Laptop at an inflated price (INV-2026-0002)",
    "hacked.txt": "Invoice with hidden instructions to the AI",
}
VERDICTS = {
    "paid": (True, "Approved and paid", "Every check passed and the payment settled on the XRP Ledger."),
    "approved_dry_run": (True, "Approved, not sent", "Every check passed. Turn on payment to settle it."),
    "blocked_by_agent": (False, "Blocked by the AI agent", "The invoice failed the agent's checks. No money moved."),
    "blocked_by_rules_server": (False, "Blocked by the rules server",
                                "The independent rules server refused. No money moved."),
    "paused": (False, "Payments are paused", "The CFO has paused all payments."),
    "failed": (False, "Payment failed", "The checks passed but the ledger did not accept the payment."),
}


def submit_invoice() -> None:
    from agent.run_agent import run_invoice

    theme.page_header(
        "Submit invoice",
        "Upload a supplier invoice. The AI agent reads and checks it, then the independent rules server "
        "decides whether it may be paid.",
        section="Oversight",
    )
    has_key = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY"))
    online = rules_server_online(RULES_URL)
    if not has_key:
        theme.note("Reading invoices needs an Anthropic API key. Add ANTHROPIC_API_KEY to .env and restart "
                   "the dashboard.", "warn")
    if not online:
        theme.note(f"The rules server is not reachable at {RULES_URL}, so no invoice can be approved.", "warn")

    left, right = st.columns([2, 3], gap="medium")
    with left, st.container(border=True):
        theme.section("Invoice", "Upload a text invoice, paste one, or use a sample.")
        source = st.segmented_control("Source", ["Sample", "Upload", "Paste"], default="Sample",
                                      label_visibility="collapsed") or "Sample"
        text = ""
        if source == "Upload":
            upload = st.file_uploader("Invoice file (.txt)", type=["txt"])
            if upload is not None:
                text = upload.getvalue()[:100_000].decode("utf-8", errors="replace")
        elif source == "Paste":
            text = st.text_area("Invoice text", height=220, placeholder="Paste the invoice text here")
        else:
            name = st.selectbox("Sample invoice", list(SAMPLE_LABELS), format_func=SAMPLE_LABELS.get)
            text = (SAMPLES_DIR / name).read_text(encoding="utf-8")
            with st.expander("Preview invoice"):
                st.code(text, language=None)

        pay = st.toggle("Pay on XRPL Testnet if approved", value=True,
                        help="Off: check only. The invoice is not reserved, so it can be paid later.")
        compromised = st.checkbox(
            "Demo: simulate a hacked agent",
            help="The agent skips its own checks and tries to send the money to a fake wallet. "
                 "Shows the independent rules server stopping it.")
        go = st.button("Check and pay" if pay else "Check invoice", type="primary",
                       icon=":material/send:", disabled=not (text.strip() and has_key and online))

    with right, st.container(border=True):
        theme.section("Result", "What happened to the invoice, step by step")
        if go:
            with st.spinner("The agent is reading and checking the invoice..."):
                try:
                    st.session_state["iy_last_submission"] = run_invoice(
                        text, submit=pay, simulate_compromised=compromised)
                except Exception as exc:
                    st.session_state.pop("iy_last_submission", None)
                    st.error(f"The invoice could not be processed ({type(exc).__name__}). "
                             "Check the API key and the rules server, then try again.")
            ledger_payments.clear()
        record = st.session_state.get("iy_last_submission")
        if not record:
            theme.empty_state("No invoice submitted yet", "Choose an invoice and select Check and pay.")
            return
        passed, headline, detail = VERDICTS.get(record.get("status"), (False, "Unknown outcome", ""))
        theme.verdict(passed, headline, detail)
        theme.trail(core.decision_trail(record))
        link = core.explorer_link(record)
        if link:
            st.link_button("Verify on the XRP Ledger", link, icon=":material/open_in_new:")


def sign_in() -> None:
    theme.page_header(
        "Staff sign in",
        "Municipal staff sign in to review payments and manage controls. "
        "The public transparency page is open to everyone.",
    )
    col, _ = st.columns([2, 3])
    with col, st.container(border=True):
        attempts = st.session_state.get("iy_attempts", 0)
        if attempts >= auth.MAX_ATTEMPTS:
            st.error("Too many failed attempts. Close the page and try again later.")
            return
        with st.form("sign_in", border=False):
            role_key = st.selectbox("Role", list(auth.ROLES), format_func=lambda k: auth.ROLES[k][0])
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", icon=":material/login:")
        if submitted:
            if auth.check_password(role_key, password):
                st.session_state["iy_role"] = role_key
                st.session_state["iy_attempts"] = 0
                st.rerun()
            st.session_state["iy_attempts"] = attempts + 1
            st.error("Incorrect role or password.")
        if not any(os.getenv(env) for _, env in auth.ROLES.values()):
            theme.note("No staff passwords are configured. Set DASHBOARD_CFO_PASSWORD and "
                       "DASHBOARD_FINANCE_PASSWORD in .env.", "warn")


# ======================================================================
# App shell
# ======================================================================
def sidebar() -> None:
    with st.sidebar:
        if auth.role():
            st.caption(f"Signed in as {auth.role_label()}")
            if st.button("Sign out", icon=":material/logout:", width="stretch"):
                auth.sign_out()
                st.rerun()
            st.write("")
        online = rules_server_online(RULES_URL)
        paused = core.agent_paused()
        theme.sidebar_status([
            ("Rules server", "Online" if online else "Offline", "ok" if online else "bad"),
            ("AI agent", "Paused" if paused else "Running", "muted" if paused else "ok"),
            ("Network", "XRPL Testnet", "info"),
        ])
        st.write("")
        if st.button("Refresh data", icon=":material/refresh:", width="stretch"):
            st.cache_data.clear()
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Imali Yethu · Payment Integrity", page_icon="🏛️",
                       layout="wide", initial_sidebar_state="auto")
    theme.inject_css()
    role = auth.role()
    public = st.Page(public_ledger, title="Public transparency", icon=":material/public:", default=role is None)
    if role is None:
        pages = {"Public": [public],
                 "Staff": [st.Page(sign_in, title="Staff sign in", icon=":material/login:")]}
    else:
        pages = {"Oversight": [
            st.Page(overview, title="Overview", icon=":material/space_dashboard:", default=True),
            st.Page(payments, title="Payments register", icon=":material/receipt_long:"),
            st.Page(submit_invoice, title="Submit invoice", icon=":material/upload_file:"),
            st.Page(invoice_check, title="Invoice check", icon=":material/fact_check:"),
        ]}
        if role == "cfo":
            pages["Governance"] = [
                st.Page(controls, title="Controls & limits", icon=":material/admin_panel_settings:")]
        pages["Public"] = [public]
    nav = st.navigation(pages)
    theme.logo()
    sidebar()
    nav.run()
    theme.footer()


if __name__ == "__main__":
    main()
