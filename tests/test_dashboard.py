"""Dashboard: data helpers and a headless render of every page."""
import json
from decimal import Decimal

import pytest
from streamlit.testing.v1 import AppTest

from dashboards import core

RECORDS = [
    {"timestamp": "2026-11-13T20:48:35+00:00", "status": "blocked_by_agent", "invoice_number": "INV-2",
     "supplier_id": "SUP-001", "amount_zar": "50000.00",
     "reasons": ["'Laptop' costs R50,000.00, 233% above market price R15,000.00"]},
    {"timestamp": "2026-11-13T20:48:35+00:00", "status": "blocked_by_rules_server", "invoice_number": "INV-1",
     "supplier_id": "SUP-001", "amount_zar": "15000.00", "simulated_compromise": True,
     "reasons": ["Supplier destination mismatch"]},
    {"timestamp": "2026-11-13T20:48:39+00:00", "status": "paid", "invoice_number": "INV-1",
     "supplier_id": "SUP-001", "amount_zar": "15000.00", "tx_hash": "ABC123", "reasons": []},
    {"timestamp": "2026-11-13T21:00:00+00:00", "status": "paused", "reasons": ["Agent paused by CFO"]},
]


def test_summary_counts_values_and_tampering():
    s = core.summarise(RECORDS)
    assert s["reviewed"] == 3
    assert s["paid_value"] == Decimal("15000.00")
    assert s["blocked_value"] == Decimal("65000.00")
    assert s["tampering"] == 1


def test_reason_categories():
    assert core.categorise_reason("Invoice contains instructions aimed at the payment system: x") == core.INJECTION
    assert core.categorise_reason("Invoice is not registered") == "Unregistered invoice"
    assert core.categorise_reason("Supplier 'X' is not registered") == "Unapproved supplier"
    assert core.block_reason_counts(RECORDS) == {"Inflated price": 1, core.WRONG_WALLET: 1}


def test_decision_trail_for_compromised_agent_stops_at_rules_server():
    states = [state for _, state, _ in core.decision_trail(RECORDS[1])]
    assert states == ["pass", "skip", "fail", "na"]


def test_decision_trail_for_paid_invoice_links_ledger():
    assert [s for _, s, _ in core.decision_trail(RECORDS[2])] == ["pass", "pass", "pass", "pass"]
    assert core.explorer_link(RECORDS[2]).endswith("ABC123")


def test_policy_checklist_marks_unchecked_items_when_invoice_unregistered():
    checks = dict(core.policy_checklist(["Invoice is not registered"]))
    assert checks["Invoice is registered against a purchase order"] == "fail"
    assert checks["Amount matches the registered invoice"] == "na"
    assert checks["Supplier is on the approved register"] == "pass"


def test_pause_writes_control_file_and_audit(tmp_path):
    control, audit = tmp_path / "control.json", tmp_path / "audit.jsonl"
    core.set_agent_paused(True, path=control, audit_path=audit)
    assert core.agent_paused(control) is True
    assert core.load_audit(audit)[0]["action"] == "Agent paused"


def test_load_records_skips_malformed_lines(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps(RECORDS[0]) + "\nnot json\n\n")
    assert len(core.load_records(log)) == 1


@pytest.fixture
def sample_log(tmp_path, monkeypatch):
    log = tmp_path / "payments.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in RECORDS))
    monkeypatch.setattr(core, "LOG_PATH", log)
    monkeypatch.setattr(core, "CONTROL_PATH", tmp_path / "control.json")
    monkeypatch.setattr(core, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setenv("RULES_SERVER_URL", "http://127.0.0.1:9")  # nothing listens here
    monkeypatch.setenv("XRPL_RPC_URL", "")  # no ledger calls in tests: pages use the local record
    monkeypatch.setenv("DASHBOARD_CFO_PASSWORD", "cfo-pass")
    monkeypatch.setenv("DASHBOARD_FINANCE_PASSWORD", "fin-pass")


def render(page: str, role: str | None = "cfo") -> AppTest:
    setup = f"import streamlit as st\nst.session_state['iy_role'] = {role!r}\n" if role else ""
    at = AppTest.from_string(
        f"{setup}from dashboards import app, theme\ntheme.inject_css()\napp.{page}()", default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def page_html(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


@pytest.mark.parametrize("page", ["overview", "payments", "invoice_check", "controls", "public_ledger",
                                  "submit_invoice", "sign_in"])
def test_page_renders_without_errors(sample_log, page):
    html = page_html(render(page))
    if page in ("overview", "public_ledger"):
        assert "R15,000.00" in html          # paid value from the sample log, not the real one
        assert "R65,000.00" in html          # value stopped
    if page in ("invoice_check", "submit_invoice"):
        assert "not reachable" in html       # offline rules server is explained, not a crash


def test_controls_refuse_non_cfo(sample_log):
    at = render("controls", role="finance")
    assert any("Only the CFO" in e.value for e in at.error)


def test_anonymous_visitor_sees_only_public_page_and_sign_in(sample_log):
    at = AppTest.from_file("../dashboards/app.py", default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    html = page_html(at)
    assert "Where our money goes" in html and "Offline" in html and "iy-topbar" in html
    assert "Payments register" not in html


def test_sign_in_with_correct_password_grants_role(sample_log):
    at = render("sign_in", role=None)
    at.selectbox[0].set_value("finance")
    at.text_input[0].input("fin-pass")
    at.button[0].click().run()
    assert at.session_state["iy_role"] == "finance"


def test_sign_in_with_wrong_password_is_refused(sample_log):
    at = render("sign_in", role=None)
    at.selectbox[0].set_value("cfo")
    at.text_input[0].input("fin-pass")      # the finance password does not open the CFO role
    at.button[0].click().run()
    assert "iy_role" not in at.session_state
    assert any("Incorrect" in e.value for e in at.error)


def test_unset_password_fails_closed(monkeypatch):
    from dashboards import auth

    monkeypatch.delenv("DASHBOARD_CFO_PASSWORD", raising=False)
    assert auth.check_password("cfo", "") is False
    assert auth.check_password("cfo", "anything") is False


def test_parse_ledger_payments_keeps_only_successful_treasury_invoice_payments():
    treasury, supplier = "rTreasury", "rSupplier"
    memo = [{"Memo": {"MemoType": "696E766F696365", "MemoData": b"INV-2026-0001".hex().upper()}}]

    def entry(**tx):
        meta = {"TransactionResult": tx.pop("result", "tesSUCCESS"), "delivered_amount": "10000000"}
        base = {"TransactionType": "Payment", "Account": treasury, "Destination": supplier,
                "DeliverMax": "10000000", "Memos": memo}
        return {"tx_json": {**base, **tx}, "meta": meta, "hash": "H1", "close_time_iso": "2026-11-13T20:49:00Z"}

    rows = core.parse_ledger_payments([
        entry(Signers=[{}, {}]),
        entry(result="tecUNFUNDED_PAYMENT"),             # failed
        entry(Account="rFaucet", Destination=treasury),  # incoming funding
        entry(Memos=[]),                                  # no invoice memo
    ], treasury, {supplier: "Honest Supplies (Pty) Ltd"})
    assert len(rows) == 1
    assert rows[0]["invoice_number"] == "INV-2026-0001"
    assert rows[0]["supplier"] == "Honest Supplies (Pty) Ltd"
    assert rows[0]["zar"] == Decimal("15000")
    assert rows[0]["multisigned"] is True
