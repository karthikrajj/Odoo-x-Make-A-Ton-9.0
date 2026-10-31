# Judge walkthrough

## The problem
Brightloop needs to know what should be billed, what was billed and what reached the bank.

## The distinction
RenewSure connects those three records and gives staff an action for each gap. Rehearsal predicts billing, calculation snapshots explain invoices, and verification checks prove billing consistency. Bank CSV matching remains human-approved.

## A continuous six-minute demo
Follow [DEMO.md](DEMO.md). Use `python fresh_demo.py` for an isolated dataset so the main database is preserved. Launch its generated Windows launcher on port 8767. On other systems set RENEWSURE_DB to the generated database and PORT to 8767 before running server.py.

1. Show MRR/ARR and overdue aging, explaining that MRR excludes tax and temporary promotions.
2. Create a subscription with the INR 560 variant; move through quotation, confirmation and activation.
3. Preview the billing cycle and checks, then create and confirm an invoice. Open its calculation explanation and PDF.
4. Record a partial payment, import a bank CSV, review a suggested allocation and resolve the remaining balance.
5. End on Expected / Invoiced / Received, then show verification and the customer view.

## Evidence
Run `python verify_all.py`. Tests cover roles, invoice history, discount limits, retry safety, a full seeded billing batch and concurrent request timings. GitHub Actions stores generated reports and a release ZIP as artifacts. Read ACCEPTANCE.md for the requirement mapping and explicit validation limits.

## Honest boundaries
This is a standalone local application, not an Odoo add-on. Confirm that format with organizers. Tax rules are configurable and tested; no legal compliance certification is claimed. CSV matching is not live bank integration. Gmail requires each installation's sender setup. Full browser/mobile/accessibility verification and public hosting hardening remain outstanding. Prepare a short backup demo video independently.
