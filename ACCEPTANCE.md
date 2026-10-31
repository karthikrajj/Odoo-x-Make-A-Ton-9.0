# RenewSure requirement acceptance report

The implementation covers all 27 grouped functional requirements below. The combined automated acceptance suite passed. This report distinguishes tested functionality from visual browser verification: the latter remains unverified because the browser tool reports access disabled.

## Results

- 94 backend/configuration/presentation tests passed.
- 12 JavaScript form regression checks passed, including reproduction of the original form.id collision.
- Actual frontend handlers completed 75 HTTP requests against an isolated database: catalog, templates, subscription creation/editing, activation, invoicing, payments, CSV allocation, email queue and customer views.
- Ten complete API demo journeys passed.
- A full batch created 9,459 invoices; rerunning created zero duplicates and left zero eligible uninvoiced periods.
- An injected mid-batch error rolled back invoices and due dates; retry succeeded.
- Four concurrent clients completed 34 measured requests after the full billing batch. The slowest was 982.76 ms, below the two-second target.
- Gmail SMTP works; the user confirmed the connection-test email in Inbox. INV-8041 was sent to the actual subscription customer, independently of the sender address.

These checks use disposable test databases and suppressed test recipients. Existing customer payments and invoices are preserved.

## Requirement mapping

| ID | Requirement | Implementation / test evidence |
| --- | --- | --- |
| AUTH-01 | Unique customer email accounts | test_signup_unique |
| AUTH-02 | More than eight characters with uppercase, lowercase and special character | test_password_rules |
| AUTH-03 | Reset link to registered email, expiring and single-use | verify_http: single-use reset; Gmail SMTP verified |
| ROLE-01 | Admin, limited staff and isolated customer portal | test_customer_all_lists_are_owned |
| ROLE-02 | Only admin can create staff | test_all_admin_configuration_rejects_staff |
| CAT-01 | Product name/type/sales price/cost/notes | test_catalog_product_details_and_edit |
| CAT-02 | Variants, including Odoo +560 | test_variant_560 |
| PLAN-01 | Plan price and minimum quantity | test_plan_price_is_billed; test_min_quantity |
| PLAN-02 | Daily/weekly/monthly/yearly schedules | test_daily_weekly_yearly_billing_dates; test_billing_catchup_idempotent |
| PLAN-03 | Availability date bounds | test_plan_availability |
| PLAN-04 | Auto close at expiry, early close, pause and renew permissions | test_annual_expiry_closes_in_same_run; test_renewal_permission; test_expired_paused_contract_cannot_bypass_renewal_permission |
| QUOTE-01 | Template with plan, lines and validity | test_template; test_expired_quote |
| SUB-01 | Unique number, customer, plan, start/expiry, terms and priced/taxed lines | test_unique_subscription_number; test_subscription_amounts |
| SUB-02 | Draft to Quotation to Confirmed to Active to Closed | test_full_state_sequence_and_close; frontend handler flow |
| SUB-03 | Add-ons and quantities can change for future cycles | test_addon_can_be_enabled_and_removed; test_contract_edit_preserves_price_and_tax_snapshots |
| BILL-01 | Automatic recurring invoices from subscription details | test_scheduler_catches_up_once |
| BILL-02 | Automatic tax from admin rules | test_tax_rules_zero_reduced_standard; test_tax_rounding |
| BILL-03 | Confirm, cancel, send and print individual invoices | frontend handlers; test_cancelled_invoice_not_reissued; test_invoice_email_pdf_attachment |
| BILL-04 | Draft to Confirmed to Paid | frontend handler flow |
| BILL-05 | No double billing or skipped eligible periods; safe retry after failure | test_bulk_due_batch_has_no_skipped_or_duplicate_periods; verify_http injected rollback |
| DISC-01 | Admin fixed/percent rules with quantity/purchase/date/use constraints | test_discount_fixed_whole_subscription; test_discount_minimum_quantity_and_purchase; test_discount_not_started_and_expired |
| DISC-02 | Product or whole-subscription scope and automatic next-invoice application | test_product_discount_leaves_other_products_full_price; test_discount_global_limit_across_subscriptions |
| PAY-01 | Record method, amount, date and note against invoice | test_payment_method_date_note_and_invoice_balance |
| PAY-02 | Paid/outstanding and partial/combined allocation visibility | test_partial_and_combined; test_payment_history_keeps_fully_allocated |
| PAY-03 | Bank CSV matching and duplicate import safety | test_matching_reference; test_import_deduplicates_manual_payment; test_manual_payment_deduplicates_import |
| REPORT-01 | Active counts, money collected, outstanding and overdue summaries with filters | test_dashboard_numbers_match_payment_and_overdue; test_partial_overdue_in_both_filters |
| PERF-01 | Under two seconds with thousands of subscriptions | performance.json: four clients, 34 requests after full billing batch |

## Corrections made during this audit

- Expired paused contracts can no longer bypass a plan's renewal restriction.
- Natural expiry can be closed even when early closure is forbidden.
- Annual contracts close in the same billing run when they have expired.
- Expiry automation operates independently of invoice automation; earned pre-expiry periods remain billable after automatic closing.
- Existing contracts keep their agreed billing frequency when a plan is edited.
- Subscription edits preserve agreed prices and tax snapshots unless staff explicitly select repricing. Retired products do not break existing contracts.
- Manual payment entry and CSV imports share duplicate detection.
- Partially paid overdue invoices appear in overdue filters and summary balances.
- Form routing reads the form's attribute, so hidden id controls cannot break transitions or invoicing.

## Explicit business policies

The plan prices the primary product per unit/cycle; selected variants add their surcharge. Add-ons use catalog prices. The PS does not prescribe that relationship, so this policy is documented and tested. Expiry is inclusive; automatic closing occurs after the expiry date. Discount use is consumed when its invoice draft is committed; cancelled invoice periods are retained and not silently reissued. Resume/renew starts a new cycle without proration. MRR excludes temporary discounts and taxes; collected payments are reported separately from invoiced amounts.

## Verification limit

A complete real-browser/mobile and accessibility walkthrough cannot yet be marked passed. The frontend handler tests execute the app's real JavaScript and HTTP requests with a DOM adapter; they do not establish actual browser layout, keyboard interaction or mobile rendering. Browser access is currently disabled in Work settings. The app is local; its process must remain running for scheduled work. Public hosting and a backup pitch video are not literal PS feature requirements.

## Repeat the audit

Run `python verify_all.py`. It executes the backend tests, JavaScript checks, frontend-handler workflow, API rehearsals, fault injection and measured four-client checks. Inspect reports/acceptance-report.json, reports/frontend-verification.json, reports/verification.json and reports/performance.json for machine-readable results.
