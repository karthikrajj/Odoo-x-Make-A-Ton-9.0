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
Money is stored in integer paise, rates in basis points. Discounts apply before tax; each line rounds tax to the nearest paise. A fixed discount is apportioned proportionally across eligible lines, with remainder on the last eligible line. Usage is consumed when a draft invoice is created, and remains consumed on cancellation. Cancelled periods are not automatically reissued. Resume/renew starts a new cycle on the demo date, with no proration. Existing invoice prices never change when catalog prices change. Existing contract lines and billing frequencies are snapshotted; choose explicit repricing to use current catalog prices on future invoices. MRR excludes taxes and temporary promotions; it is not recognized accounting revenue.

Automatic billing is off by default for a controlled demo. Enable it under Billing settings. Choose Demo or Live clock; Live follows the current India date. The scheduler runs every 30 seconds while the server is running and catches up missed periods. Plan-controlled expiry closing runs even when automatic invoice generation is off; earned pre-expiry periods remain recoverable. Reminders use the selected clock and queue only the latest eligible stage on catch-up.

## Verification
Run `python verify_all.py` for the complete acceptance suite. See ACCEPTANCE.md for the requirement-by-requirement result.

`python -m unittest -v` runs 93 business and configuration regression tests.
`python verify_http.py` uses a disposable database and local server for auth checks and ten complete API rehearsals.
Results are written under `reports/`. The suite includes ten full API journeys, a 9,459-invoice batch, rollback/retry checks and concurrent reads against 10,050 subscriptions. These are local measurements, not production capacity guarantees. Frontend handlers run against a DOM adapter; full browser/mobile visual verification remains outstanding.

Run `ruff check .`, `ruff format --check .`, and the pinned development tools `npm exec --yes --package=eslint@10.14.0 -- eslint static tests` and `npm exec --yes --package=prettier@3.6.2 -- prettier --check static tests/*.cjs eslint.config.mjs`. No npm runtime dependencies or package installation is required to run the app. Python and JavaScript are not statically typed; compilation and lint checks do not constitute a static type check.

Run `python scripts/check_repository.py` for import, cycle and secret checks. Run `python scripts/build_release.py` for an allowlisted ZIP release, excluding credentials and live data, with extracted bootstrap verification.

## Files and scope
`server.py` is the stable launcher. `renewsure/` separates configuration, database/schema, seed data, security, billing, workflows, documents, delivery and HTTP handling. `static/` contains the frontend; `tests/` contains regression checks; `scripts/` contains repository/release tools; `reports/` holds generated evidence. SQLite data persists in `renewsure.db`; recovery copies in `backups/` are preserved.

This remains a local hackathon application. Public hosting needs a hardened server/reverse proxy, HTTPS, review of seeded demo accounts, deployment secret management and operational backups. Live bank feeds and GST compliance certification are outside scope. See CLEANUP.md for the cleanup results and remaining review items.
