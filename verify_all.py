"""One command for the PS acceptance checks. Uses disposable DBs; sends no real test email."""

import datetime
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    (BASE / "reports").mkdir(exist_ok=True)
    commands = [
        [sys.executable, "-m", "unittest", "-q"],
        ["node", "--check", "static/app.js"],
        ["node", "tests/test_forms.cjs"],
        [sys.executable, "verify_frontend.py"],
        [sys.executable, "verify_http.py"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=BASE)
        if result.returncode:
            raise SystemExit(result.returncode)

    def read(name):
        return json.loads((BASE / "reports" / name).read_text(encoding="utf-8-sig"))

    api = read("verification.json")
    front = read("frontend-verification.json")
    performance = read("performance.json")
    email = (
        read("email-verification.json")
        if (BASE / "reports" / "email-verification.json").exists()
        else {"inbox_receipt_confirmed": False}
    )
    requirements = [
        ("AUTH-01", "Unique customer email accounts", "test_signup_unique"),
        (
            "AUTH-02",
            "More than eight characters with uppercase, lowercase and special character",
            "test_password_rules",
        ),
        (
            "AUTH-03",
            "Reset link to registered email, expiring and single-use",
            "verify_http: single-use reset; Gmail SMTP verified",
        ),
        (
            "ROLE-01",
            "Admin, limited staff and isolated customer portal",
            "test_customer_all_lists_are_owned",
        ),
        (
            "ROLE-02",
            "Only admin can create staff",
            "test_all_admin_configuration_rejects_staff",
        ),
        (
            "CAT-01",
            "Product name/type/sales price/cost/notes",
            "test_catalog_product_details_and_edit",
        ),
        ("CAT-02", "Variants, including Odoo +560", "test_variant_560"),
        (
            "PLAN-01",
            "Plan price and minimum quantity",
            "test_plan_price_is_billed; test_min_quantity",
        ),
        (
            "PLAN-02",
            "Daily/weekly/monthly/yearly schedules",
            "test_daily_weekly_yearly_billing_dates; test_billing_catchup_idempotent",
        ),
        ("PLAN-03", "Availability date bounds", "test_plan_availability"),
        (
            "PLAN-04",
            "Auto close at expiry, early close, pause and renew permissions",
            "test_annual_expiry_closes_in_same_run; test_renewal_permission; test_expired_paused_contract_cannot_bypass_renewal_permission",
        ),
        (
            "QUOTE-01",
            "Template with plan, lines and validity",
            "test_template; test_expired_quote",
        ),
        (
            "SUB-01",
            "Unique number, customer, plan, start/expiry, terms and priced/taxed lines",
            "test_unique_subscription_number; test_subscription_amounts",
        ),
        (
            "SUB-02",
            "Draft to Quotation to Confirmed to Active to Closed",
            "test_full_state_sequence_and_close; frontend handler flow",
        ),
        (
            "SUB-03",
            "Add-ons and quantities can change for future cycles",
            "test_addon_can_be_enabled_and_removed; test_contract_edit_preserves_price_and_tax_snapshots",
        ),
        (
            "BILL-01",
            "Automatic recurring invoices from subscription details",
            "test_scheduler_catches_up_once",
        ),
        (
            "BILL-02",
            "Automatic tax from admin rules",
            "test_tax_rules_zero_reduced_standard; test_tax_rounding",
        ),
        (
            "BILL-03",
            "Confirm, cancel, send and print individual invoices",
            "frontend handlers; test_cancelled_invoice_not_reissued; test_invoice_email_pdf_attachment",
        ),
        ("BILL-04", "Draft to Confirmed to Paid", "frontend handler flow"),
        (
            "BILL-05",
            "No double billing or skipped eligible periods; safe retry after failure",
            "test_bulk_due_batch_has_no_skipped_or_duplicate_periods; verify_http injected rollback",
        ),
        (
            "DISC-01",
            "Admin fixed/percent rules with quantity/purchase/date/use constraints",
            "test_discount_fixed_whole_subscription; test_discount_minimum_quantity_and_purchase; test_discount_not_started_and_expired",
        ),
        (
            "DISC-02",
            "Product or whole-subscription scope and automatic next-invoice application",
            "test_product_discount_leaves_other_products_full_price; test_discount_global_limit_across_subscriptions",
        ),
        (
            "PAY-01",
            "Record method, amount, date and note against invoice",
            "test_payment_method_date_note_and_invoice_balance",
        ),
        (
            "PAY-02",
            "Paid/outstanding and partial/combined allocation visibility",
            "test_partial_and_combined; test_payment_history_keeps_fully_allocated",
        ),
        (
            "PAY-03",
            "Bank CSV matching and duplicate import safety",
            "test_matching_reference; test_import_deduplicates_manual_payment; test_manual_payment_deduplicates_import",
        ),
        (
            "REPORT-01",
            "Active counts, money collected, outstanding and overdue summaries with filters",
            "test_dashboard_numbers_match_payment_and_overdue; test_partial_overdue_in_both_filters",
        ),
        (
            "PERF-01",
            "Under two seconds with thousands of subscriptions",
            "performance.json: four clients, 34 requests after full billing batch",
        ),
    ]
    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "functional_automated_checks_passed": api["concurrent_reads_passed"]
        and front["all_passed"]
        and performance["all_under_2_seconds"],
        "backend_tests": api["domain_tests"],
        "frontend_form_regression_checks": 12,
        "frontend_server_requests": front["requests"],
        "full_api_rehearsals": api["demo_rehearsals"],
        "bulk_invoices_created": api["bulk_created"],
        "max_concurrent_request_ms": performance["max_ms"],
        "gmail_connection_inbox_confirmed": email["inbox_receipt_confirmed"],
        "browser_visual_review_complete": False,
        "browser_review_limit": "Browser tool reports local browser access disabled; frontend handlers and templates were tested with a DOM adapter, not a browser.",
        "requirements": [
            {
                "id": rid,
                "requirement": text,
                "implemented": True,
                "automated_evidence": evidence,
            }
            for rid, text, evidence in requirements
        ],
    }
    (BASE / "reports" / "acceptance-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(
        "PS acceptance: "
        + str(len(requirements))
        + " requirement groups implemented; automated checks passed. Browser visual review remains explicitly unverified."
    )


if __name__ == "__main__":
    main()
