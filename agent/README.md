# Agent (owner: Melusi)

The agent pays approved invoices on XRPL Testnet. It never decides alone: the independent rules server must approve each payment first.

```
invoice text ──► Claude extracts fields (invoice text = untrusted data)
             ──► agent checks: injected instructions, prices vs data/prices.json, totals
             ──► destination looked up in data/suppliers.json (never from the invoice)
             ──► rules server: validate → verify exact tx → reserve invoice
             ──► submit Payment to XRPL Testnet, log decision to data/payments.jsonl
```

## Run

```bash
pip install -r requirements.txt
# .env needs: ANTHROPIC_API_KEY, wallet addresses/seeds (scripts/setup_wallets.py),
#             RULES_SERVER_URL, RULES_SERVER_API_KEY
uvicorn rules_server.main:app --port 8000          # terminal 1

python -m agent.run_agent data/sample_invoices/honest.txt              # dry run
python -m agent.run_agent data/sample_invoices/honest.txt --submit     # real Testnet payment
python -m agent.run_agent data/sample_invoices/inflated.txt            # blocked by agent (price)
python -m agent.run_agent data/sample_invoices/hacked.txt              # blocked by agent (injection)
python -m agent.run_agent data/sample_invoices/hacked.txt --simulate-compromised
#   ^ agent is "fooled" and tries to pay the fake supplier; the rules server blocks it

streamlit run dashboards/agent_dashboard.py          # CFO view, pause switch, limits
```

## Notes

- Model: `claude-opus-5-5` with structured outputs. Server-side refusal fallback (`fallbacks: "default"`) is on.
- Demo FX rate: R1,500 = 1 XRP, so the registered R15,000 invoice pays 10 XRP.
- **Signing (Privy):** after `python scripts/setup_privy_wallet.py`, the agent signs through a Privy server
  wallet that is the Treasury's *regular key*. Privy's policy only signs Payments to approved suppliers
  under `PRIVY_MAX_XRP`, and the CFO dashboard can revoke the key on-ledger. Without Privy configured,
  it falls back to `TREASURY_SEED`.
