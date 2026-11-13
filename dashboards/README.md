# Dashboards (Streamlit)

```bash
uvicorn rules_server.main:app --port 8000     # terminal 1: rules server
streamlit run dashboards/app.py               # terminal 2: dashboard
```

`dashboards/app.py` is the main dashboard. It has five pages:

| Page | For | What it shows |
| --- | --- | --- |
| Overview | CFO's office | Money paid and stopped, tampering attempts, why invoices were blocked, latest activity |
| Payments register | CFO, auditors | Every agent decision, with filters, CSV export and a step-by-step decision trail |
| Invoice check | Finance officials | Policy pre-check against the live rules server, and market price benchmarks |
| Controls & limits | CFO | Agent kill switch, on-ledger key revocation, spending limits, audit trail |
| Public transparency | Citizens | Every payment with a link to verify it on the XRP Ledger |

All figures come from `data/payments.jsonl` (written by the agent), `data/suppliers.json`,
`data/prices.json` and the rules server. Nothing is hardcoded. Control changes are written to
`data/dashboard_audit.jsonl`.

Code layout: `core.py` (data, no Streamlit, unit tested), `theme.py` (styles and HTML components;
all dynamic text is escaped because invoice text is untrusted), `app.py` (pages).

