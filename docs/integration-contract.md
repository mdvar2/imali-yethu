# Agent ↔ rules server integration contract

Proposed by Melusi (agent + CFO dashboard). Nelisiwe owns the rules server; nothing in `rules_server/` was changed on this branch.

## 1. What the agent calls today (works with `main` as merged)

All calls send the header `X-Service-Key: $RULES_SERVER_API_KEY`. The agent calls them in this order:

| Step | Endpoint | Body | Agent proceeds when |
|---|---|---|---|
| 1 | `POST /validate-payment` | `{invoice_number, supplier_id, amount}` (ZAR, 2 dp) | `approved == true` |
| 2 | `POST /verify-xrpl-transaction` | the Payment JSON below, **before autofill** | `verified == true` |
| 3 | `POST /authorize-payment` | same as step 1 | `authorized == true` (invoice reserved) |

Verification runs **before** authorization. A transaction that fails verification therefore doesn't burn the invoice reservation.

Payment JSON sent in step 2:

```json
{
  "TransactionType": "Payment",
  "Account": "<TREASURY_ADDRESS>",
  "Destination": "<supplier wallet from data/suppliers.json -> .env>",
  "Amount": "10000000",
  "Memos": [{"Memo": {"MemoType": "696E766F696365", "MemoData": "<hex invoice number>"}}]
}
```

The agent takes the destination from the supplier register, never from the invoice text.

## 2. Gaps to close (rules server side)

1. **One request, one approval.** Merge steps 1–3 into a single call that takes `invoice_number`, `supplier_id`, `destination`, `amount_drops` and the transaction. Rules server policy should map `supplier_id → wallet` and `invoice → amount_drops`. Today the 10 XRP / `INV-2026-0001` values are hardcoded in `xrpl_verification.py`. The agent uses a demo rate of R1,500/XRP so that R15,000 = 10 XRP.
2. **Verify what you sign.** Once multisig is live, the rules server should receive the autofilled `tx_blob` (with `Fee`, `Sequence`, `LastLedgerSequence`, `SigningPubKey: ""`), decode it, check it, and return its signature. The current five-field allow-list will reject every autofilled transaction.
3. **Single use.** Mark the reservation `signed` after co-signing, and refuse a second signature for the same invoice.

## 3. What the CFO dashboard needs

The dashboard uses a **separate admin key**: header `X-Admin-Key: $RULES_ADMIN_KEY`. The agent never has this key, so it can't change its own limits.

```
GET  /policy  -> {"max_payment_zar": "50000.00", "weekly_cap_zar": "200000.00",
                  "approved_suppliers": ["SUP-001", "SUP-002"]}
PUT  /policy  <- same shape; 200 on success. Write an audit log entry.
```

Until these endpoints exist, the dashboard shows a notice instead of the editor.

**Kill switch:** the dashboard currently pauses the agent through `data/agent_control.json`. A stronger version would be `POST /pause` on the rules server, so a paused system refuses to co-sign even if the agent ignores the flag.

## 4. Signing

The agent signs with a **Privy server wallet** that is set as the Treasury's regular key (`scripts/setup_privy_wallet.py`). Privy enforces its own policy before signing: Payments only, approved supplier destinations only, at most `PRIVY_MAX_XRP`. The CFO dashboard can revoke the key with `SetRegularKey`. When the Treasury signer list (quorum 3) is live, the Privy wallet becomes the agent's signer entry instead of the regular key.
