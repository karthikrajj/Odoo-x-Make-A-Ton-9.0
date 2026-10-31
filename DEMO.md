# Six-minute demo

1. Sign in as admin. Explain the four finance figures and aging buckets; clarify the selected reporting period.
2. Open Subscriptions, create a customer using Launch / Odoo starter. Inspect the INR 560 variant addition. Move Draft → Quotation → Confirmed → Active.
3. Reconciliation: filter the customer. Show Due, not invoiced and create its draft. Alternatively use Billing rehearsal for a whole-cycle preview.
4. Open the invoice, explain subtotal/discount/tax, confirm, then open its PDF.
5. Record a partial UPI payment. Show the outstanding balance in Reconciliation. Import a CSV referencing INV-number, review the suggestion and approve the remaining allocation.
6. Show Paid in the customer portal, invoice delivery in the local mailbox, and verification checks/audit.
7. For an unpaid invoice, demonstrate reminder scheduling and dispute hold. End on the three-way ledger.

Use `python fresh_demo.py` to create an isolated seeded database and launcher without overwriting existing data. Start its launcher on port 8767. Each new demo is independent.

For password reset: sign out, choose Forgot password, submit a registered demo email, open Demo mailbox for that address, follow the single-use link. This is local test delivery, not an external email service.
