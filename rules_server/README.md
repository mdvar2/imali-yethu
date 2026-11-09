# Rules server (owner: security teammate)

Independent FastAPI service. It co-signs a payment only if every check passes:

| Check | Rule |
| --- | --- |
| Approved supplier | Registered and tax compliant |
| Connected supplier | No director matches the officials list |
| Price | Not more than ~20% above market price |
| Caps | Within per-payment and weekly limits |
| Contract splitting | No run of invoices just under the tender threshold |
| Duplicate invoice | Invoice number never paid before |
| New supplier risk | Flag companies under 3 months old winning big invoices |

It also holds the escrow fulfillment secrets and releases one only after delivery is verified.
