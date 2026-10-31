# RenewSure — local hackathon application

## Start
Double-click Start-RenewSure.cmd, or run `python server.py`. Keep the server running and open http://127.0.0.1:8766.

Accounts: admin@renewsure.demo, staff@renewsure.demo, customer@renewsure.demo.
Demo password: DemoPass!2026. New customers can sign up; admin creates staff.

## Implemented workflow
- Signup, password rules, duplicate-email protection, session cookies, role checks and single-use expiring reset links.
- Products, cost/sales prices, notes, variants (seeded Odoo +560 INR), tax rules, recurring plans and their availability/minimum/permission controls.
- Quotation templates, multiple product lines, draft-to-active lifecycle, pause/resume/close/renew and expiry.
- Fixed/percentage discounts, product scope, date/quantity/purchase constraints and global use limits.
- Read-only revision-checked billing rehearsal, atomic catch-up billing, unique subscription/period invoices and automatic billing option under Billing settings.
- Draft invoice confirmation/cancellation, immutable calculations, printable individual PDFs, payment history, allocation details and Gmail invoice delivery.
- Unified Expected/Invoiced/Received view, missing invoices, overdue/partial/unmatched statuses, CSV import deduplication, confidence-labelled suggestions and staff-approved split allocations.
- Background reminder stages (due, +3, +7), dispute holds, priority queue, audit and live invariants.
- MRR/ARR, movement breakdown, receivables aging, date/customer filters, pagination and measured timings.

## Gmail delivery
The public local mailbox is removed. Gmail SMTP delivers password reset links, invoice PDFs and reminders. Run Setup-Gmail.cmd to configure the sending account in a private local window. Credentials live only in the ignored .env file. Admin's Email delivery screen shows delivery states without exposing reset links or credentials. See EMAIL_SETUP.md.

A real connection test was accepted by Gmail and recorded as Sent; the user confirmed receipt in Gmail Inbox. Old demo queue records and synthetic recipients are suppressed.

## Billing policies
Money is stored in integer paise, rates in basis points. Discounts apply before tax; each line rounds tax to the nearest paise. A fixed discount is apportioned proportionally across eligible lines, with remainder on the last eligible line. Usage is consumed when a draft invoice is created, and remains consumed on cancellation. Cancelled periods are not automatically reissued. Resume/renew starts a new cycle on the demo date, with no proration. Existing invoice prices never change when catalog prices change. MRR excludes taxes and temporary promotions; it is not recognized accounting revenue.

Automatic billing is off by default for a controlled demo. Enable it under Billing settings. Choose Demo or Live clock; Live follows the current India date. The scheduler runs every 30 seconds while the server is running and catches up missed periods. Reminders use the selected clock and queue only the latest eligible stage on catch-up.

## Verification
`python -m unittest -v` runs 51 domain tests.
`python verify_http.py` uses a disposable database and local server for auth checks and ten complete API rehearsals.
See verification.json for measured results. All sampled HTTP endpoints were below two seconds with 10,050 seeded subscriptions. The latest four-client test covered 34 requests with a maximum of 1,055.86 ms; see performance.json. This is a local measurement, not a production load guarantee. Browser validation covered dashboard rendering, subscription form validation and template creation; the latest full browser/mobile review remains outstanding because computer-use could not reliably access the browser. A rendered PDF was visually reviewed.

## Files and scope
server.py: HTTP/session layer; domain.py: money/billing; services.py: workflows; legacy.py: initial schema/seed; static/: frontend. SQLite data persists in renewsure.db. backups/ contains a pre-upgrade copy. No public deployment, live bank feeds or GST compliance certification is included. Production hosting requires hardened deployment, real email, security review and operational backups.
