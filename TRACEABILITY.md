# Requirement traceability

| Requirement | Screen / implementation | Evidence |
| --- | --- | --- |
| Unique email, password policy, reset | Sign in, Sign up, Forgot password, Gmail SMTP | API signup/reset tests |
| Admin/staff/customer and admin-only staff | Team access, server role guards | auth/ownership tests |
| Products, cost/sales/notes, +560 variant | Products, Variants | variant and scope tests |
| Frequencies, minimum, dates, lifecycle permissions | Recurring plans | availability/minimum/permission tests |
| Templates and validity | Quotation templates, New subscription | template/expired quote tests |
| Subscription number, customer, dates, terms, lines, states | Subscription register / Manage | lifecycle tests |
| Automatic invoices, taxes, no duplicates | Billing rehearsal, schedule, Invoices | catch-up/idempotency/tax tests |
| Confirm/cancel/send/print | Invoice detail and PDF | ten API journeys |
| Fixed/percent and scoped bounded discounts | Discount rules | limit/read-only/scope tests |
| Payments, methods, partial balances | Payment history, Record payment, Bank matching | split/overallocation tests |
| Active/revenue/payments/overdue reports | Overview, Overdue recovery | measured endpoints |
| Under two seconds with thousands | Timings on screens, verification.json | 10,050 seed; sampled HTTP checks |
| Distinctive three-way ledger | Reconciliation | missing invoice and payment tests |
| Rehearse/prove/reconcile | Rehearsal, Verification & audit, Bank matching | API demo repeated ten times |

Gmail SMTP is configured; the real connection-test email was accepted as Sent. The user confirmed receipt in Gmail Inbox. Full browser rehearsal, mobile/accessibility audit and backup video are not yet completed.

## Acceptance corrections
The plan price now determines the primary (first) product's unit price; its selected variant surcharge is added. Additional product lines use catalog prices. Prices are snapshotted when a contract is created or explicitly edited, so existing contracts/invoices do not silently reprice. This is the chosen resolution of the PS's unspecified plan/product price relationship.
Paused contracts now honor automatic close at expiry without billing paused periods. Regression tests cover both enabled and disabled automatic close.

Live-date scheduling, complete payment history and subscription line totals are implemented. The latest four-client test passed all 34 reads below two seconds (maximum 1,055.86 ms). A real Gmail connection test was accepted; the final complete browser/mobile walkthrough remains unconfirmed. These local results do not certify performance at arbitrary production load.
