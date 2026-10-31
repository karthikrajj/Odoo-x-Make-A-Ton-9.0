import os
import shutil
import tempfile
import unittest

import server
from renewsure import database as db
from renewsure import domain as d
from renewsure import security
from renewsure import services as s
from renewsure.money import calc

ADMIN = {"role": "admin", "email": "admin@renewsure.demo"}
STAFF = {"role": "staff", "email": "staff@renewsure.demo"}
CUSTOMER = {"role": "customer", "email": "customer@renewsure.demo"}


class RenewSureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old = db.DB
        db.DB = os.path.join(cls.tmp.name, "base.db")
        server.initialize()
        cls.base = db.DB

    def setUp(self):
        db.DB = os.path.join(self.tmp.name, "case.db")
        shutil.copyfile(self.base, db.DB)
        self.cm = db.conn()
        self.c = self.cm.__enter__()

    def tearDown(self):
        self.cm.__exit__(None, None, None)

    @classmethod
    def tearDownClass(cls):
        db.DB = cls.old
        cls.tmp.cleanup()

    def call(self, path, data=None, user=ADMIN, q=None):
        return s.handle(self.c, path, data, user, q or {})

    def test_payment_history_batches_allocation_queries(self):
        invoice = self.inv()
        for number in range(30):
            self.call(
                "payments",
                {
                    "invoice_id": invoice["id"],
                    "amount": 1,
                    "method": "UPI",
                    "date": "2026-10-31",
                    "reference": f"batch-{number}",
                },
            )
        queries = []
        self.c.set_trace_callback(queries.append)
        try:
            result = s.payment_records(self.c, ADMIN, {})
        finally:
            self.c.set_trace_callback(None)
        self.assertEqual(len(result["rows"]), 30)
        selects = [sql for sql in queries if sql.lstrip().upper().startswith("SELECT")]
        self.assertEqual(len(selects), 3)
        self.assertTrue(all(len(row["allocations"]) == 1 for row in result["rows"]))

    def sub(self, **over):
        v = {
            "customer": "Test Account",
            "email": "customer@renewsure.demo",
            "plan_id": 1,
            "start_date": "2026-10-31",
            "terms_days": 0,
            "lines": [{"product_id": 1, "variant_id": 1, "qty": 2, "tax_id": 1}],
        }
        v.update(over)
        sid = self.call("subscriptions", v)["id"]
        for state in ["Quotation", "Confirmed", "Active"]:
            self.call("transition", {"id": sid, "state": state})
        return sid

    def inv(self):
        sid = self.sub()
        d.billing(self.c, only=sid)
        i = d.one(self.c, "SELECT * FROM invoices WHERE subscription_id=?", (sid,))
        self.call("invoice", {"id": i["id"], "action": "confirm"})
        return i

    def test_password_rules(self):
        for invalid in [
            "short",
            "abcdefgh!",
            "ABCDEFGH!",
            "Abcdefghi",
            "Abcdef!1",
            "Abcdefgh ",
        ]:
            self.assertFalse(security.valid(invalid))
        self.assertTrue(security.valid("TestPass!2026"))

    def test_signup_unique(self):
        d.new_user(
            self.c,
            {"email": "New@Example.com", "name": "New", "password": "TestPass!2026"},
        )
        with self.assertRaises(d.Error):
            d.new_user(
                self.c,
                {
                    "email": "new@example.com",
                    "name": "New",
                    "password": "TestPass!2026",
                },
            )

    def test_staff_cannot_configure(self):
        with self.assertRaises(PermissionError):
            self.call("taxes", {"name": "Bad", "rate": 1800}, STAFF)

    def test_customer_cannot_create(self):
        with self.assertRaises(PermissionError):
            self.call("subscriptions", {}, CUSTOMER)

    def test_customer_isolation(self):
        with self.assertRaises(PermissionError):
            self.call("invoice", None, CUSTOMER, {"id": 4})

    def test_variant_560(self):
        sid = self.sub()
        a = d.quote(
            self.c,
            d.one(self.c, "SELECT * FROM subscriptions WHERE id=?", (sid,)),
            "2026-10-31",
        )
        self.assertEqual(a["subtotal"], 212000)
        self.assertEqual(a["total"], 250160)

    def test_invalid_variant(self):
        with self.assertRaises(d.Error):
            s.line_values(
                self.c, [{"product_id": 2, "variant_id": 1, "qty": 1, "tax_id": 1}]
            )

    def test_min_quantity(self):
        self.c.execute("UPDATE plans SET min_qty=5 WHERE id=1")
        with self.assertRaises(d.Error):
            self.sub()

    def test_plan_availability(self):
        self.c.execute("UPDATE plans SET available_to='2026-01-01' WHERE id=1")
        with self.assertRaises(d.Error):
            self.sub()

    def test_template(self):
        sid = self.sub(template_id=1)
        self.assertEqual(
            d.one(self.c, "SELECT qty FROM subscriptions WHERE id=?", (sid,))["qty"], 1
        )

    def test_no_template_string_zero(self):
        self.sub(template_id="0")

    def test_pause_permission(self):
        sid = self.sub()
        self.c.execute("UPDATE plans SET allow_pause=0 WHERE id=1")
        with self.assertRaises(d.Error):
            self.call("transition", {"id": sid, "state": "Paused"})

    def test_customer_pause_own(self):
        sid = self.sub()
        self.call("transition", {"id": sid, "state": "Paused"}, CUSTOMER)
        self.assertFalse(d.rehearsal(self.c, only=sid)["items"])

    def test_expired_quote(self):
        sid = self.call(
            "subscriptions",
            {
                "customer": "X",
                "email": "x@example.com",
                "plan_id": 1,
                "start_date": "2026-10-31",
                "lines": [{"product_id": 1, "qty": 1, "tax_id": 1}],
            },
        )["id"]
        self.call("transition", {"id": sid, "state": "Quotation"})
        self.c.execute(
            "UPDATE subscriptions SET quotation_until='2020-01-01' WHERE id=?", (sid,)
        )
        with self.assertRaises(d.Error):
            self.call("transition", {"id": sid, "state": "Confirmed"})

    def test_tax_rounding(self):
        self.assertEqual(calc(103, 1, 0, 1800)["tax"], 19)

    def test_discount_before_tax(self):
        self.assertEqual(calc(10000, 1, 1000, 1800)["total"], 10620)

    def test_discount_limit_preview_readonly(self):
        did = self.call(
            "discounts",
            {
                "name": "Launch",
                "kind": "percent",
                "value": 1000,
                "min_qty": 1,
                "min_purchase": 0,
                "start": "2026-01-01",
                "end": "2026-12-31",
                "limit_uses": 1,
            },
        )["id"]
        sid = self.sub(discount_id=did, start_date="2026-09-30")
        p = d.rehearsal(self.c, only=sid)
        self.assertEqual(sum(i["discount"] > 0 for i in p["items"]), 1)
        self.assertEqual(
            d.one(self.c, "SELECT used FROM discount_rules WHERE id=?", (did,))["used"],
            0,
        )
        d.billing(self.c, only=sid)
        self.assertEqual(
            d.one(self.c, "SELECT used FROM discount_rules WHERE id=?", (did,))["used"],
            1,
        )

    def test_product_discount_scope(self):
        did = self.call(
            "discounts",
            {
                "name": "Other product",
                "kind": "fixed",
                "value": 50000,
                "min_qty": 1,
                "min_purchase": 0,
                "start": "2026-01-01",
                "end": "2026-12-31",
                "limit_uses": 3,
                "product_id": 2,
            },
        )["id"]
        sid = self.sub(discount_id=did)
        self.assertEqual(d.rehearsal(self.c, only=sid)["total"], 250160)

    def test_billing_catchup_idempotent(self):
        sid = self.sub(start_date="2026-08-31")
        r = d.billing(self.c, only=sid)
        self.assertEqual(r["created"], 3)
        self.assertEqual(d.billing(self.c, only=sid)["created"], 0)

    def test_month_end_anchor(self):
        self.assertEqual(
            d.next_period({"cycle": "monthly", "anchor_day": 31}, "2026-02-28"),
            "2026-03-31",
        )

    def test_leap_year(self):
        self.assertEqual(
            d.next_period({"cycle": "yearly", "anchor_day": 29}, "2024-02-29"),
            "2025-02-28",
        )

    def test_stale_preview(self):
        p = d.rehearsal(self.c)
        d.bump(self.c)
        with self.assertRaises(d.Error):
            d.billing(self.c, p["revision"])

    def test_expiry_auto_close(self):
        self.c.execute("UPDATE settings SET value='2026-09-01' WHERE key='clock'")
        sid = self.sub(start_date="2026-09-01", expiry="2026-09-30")
        self.c.execute("UPDATE settings SET value='2026-10-31' WHERE key='clock'")
        d.billing(self.c, only=sid)
        self.assertEqual(
            d.one(self.c, "SELECT state FROM subscriptions WHERE id=?", (sid,))[
                "state"
            ],
            "Closed",
        )

    def test_snapshot_preserved(self):
        i = self.inv()
        self.c.execute("UPDATE products SET sales_price=1")
        self.assertEqual(d.invoice(self.c, i["id"])["total"], 250160)

    def test_partial_and_combined(self):
        a = self.inv()
        b = self.inv()
        bid = self.c.execute(
            "INSERT INTO bank(fingerprint,reference,customer,amount,date,method) VALUES('split','combined','Test',300000,'2026-10-31','NEFT')"
        ).lastrowid
        d.allocate(self.c, bid, a["id"], a["total"])
        d.allocate(self.c, bid, b["id"], 300000 - a["total"])
        self.assertEqual(d.invoice(self.c, a["id"])["state"], "Paid")
        self.assertEqual(d.invoice(self.c, b["id"])["balance"], 200320)

    def test_overallocation_rejected(self):
        i = self.inv()
        bid = self.c.execute(
            "INSERT INTO bank(fingerprint,amount) VALUES('small',100)"
        ).lastrowid
        with self.assertRaises(d.Error):
            d.allocate(self.c, bid, i["id"], 101)

    def test_draft_payment_rejected(self):
        sid = self.sub()
        d.billing(self.c, only=sid)
        i = d.one(self.c, "SELECT id FROM invoices WHERE subscription_id=?", (sid,))
        bid = self.c.execute(
            "INSERT INTO bank(fingerprint,amount) VALUES('small',100)"
        ).lastrowid
        with self.assertRaises(d.Error):
            d.allocate(self.c, bid, i["id"], 100)

    def test_paid_cancel_rejected(self):
        i = self.inv()
        self.call(
            "payment",
            {
                "invoice_id": i["id"],
                "amount": 10,
                "reference": "unique",
                "date": "2026-10-31",
                "method": "UPI",
            },
        )
        with self.assertRaises(d.Error):
            self.call("invoice", {"id": i["id"], "action": "cancel"})

    def test_csv_dedup(self):
        csv = "reference,customer,amount,date,method\nR1,Test,10.00,2026-10-31,NEFT\n"
        self.assertEqual(self.call("import", {"csv": csv})["imported"], 1)
        self.assertEqual(self.call("import", {"csv": csv})["duplicates"], 1)

    def test_matching_reference(self):
        i = self.inv()
        self.call(
            "import",
            {
                "csv": f"reference,customer,amount,date\nINV-{i['id']},Test Account,2501.60,2026-10-31\n"
            },
        )
        r = self.call("bank")
        self.assertEqual(r["rows"][0]["suggestions"][0]["confidence"], "High")

    def test_reminders_idempotent(self):
        i = self.inv()
        self.assertEqual(len(d.chase(self.c, i["id"])), 1)
        self.assertEqual(len(d.chase(self.c, i["id"])), 0)

    def test_dispute_blocks_reminder(self):
        i = self.inv()
        self.call("invoice", {"id": i["id"], "action": "dispute"})
        self.assertEqual(d.chase(self.c, i["id"]), [])

    def test_reconcile_missing_invoice(self):
        sid = self.sub()
        r = self.call(
            "reconcile", q={"q": "Test Account", "status": "Due, not invoiced"}
        )
        self.assertTrue(any(x.get("subscription_id") == sid for x in r["rows"]))

    def test_pdf(self):
        self.assertTrue(
            server.pdf_invoice(d.invoice(self.c, self.inv()["id"])).startswith(
                b"%PDF-1.4"
            )
        )

    def test_invariants(self):
        self.assertTrue(all(x["passed"] for x in d.checks(self.c)))

    def test_pagination(self):
        r = self.call("subscriptions", q={"page": "999999", "q": "not-exist"})
        self.assertEqual(r["page"], 1)
        self.assertEqual(r["rows"], [])

    def test_mrr_movements(self):
        before = self.call("dashboard")["mrr"]
        sid = self.sub()
        after = self.call("dashboard")["mrr"]
        self.assertEqual(after - before, 212000)
        self.call("transition", {"id": sid, "state": "Paused"})
        self.assertEqual(self.call("dashboard")["mrr"], before)

    def test_plan_price_is_billed(self):
        self.c.execute("UPDATE plans SET price=90000 WHERE id=1")
        sid = self.sub()
        self.assertEqual(d.rehearsal(self.c, only=sid)["items"][0]["subtotal"], 292000)

    def test_paused_expiry_closes(self):
        sid = self.sub(expiry="2026-11-01")
        self.call("transition", {"id": sid, "state": "Paused"})
        self.c.execute("UPDATE settings SET value='2026-11-02' WHERE key='clock'")
        d.billing(self.c, only=sid)
        self.assertEqual(
            d.one(self.c, "SELECT state FROM subscriptions WHERE id=?", (sid,))[
                "state"
            ],
            "Closed",
        )

    def test_paused_expiry_respects_plan(self):
        sid = self.sub(expiry="2026-11-01")
        self.call("transition", {"id": sid, "state": "Paused"})
        self.c.execute("UPDATE plans SET auto_close=0 WHERE id=1")
        self.c.execute("UPDATE settings SET value='2026-11-02' WHERE key='clock'")
        d.billing(self.c, only=sid)
        self.assertEqual(
            d.one(self.c, "SELECT state FROM subscriptions WHERE id=?", (sid,))[
                "state"
            ],
            "Paused",
        )

    def test_subscription_amounts(self):
        sid = self.sub()
        r = self.call("subscription", q={"id": sid})
        self.assertEqual(r["calculation"]["total"], 250160)
        self.assertEqual(
            sum(line["total"] for line in r["lines"]), r["calculation"]["total"]
        )
        self.assertEqual(r["plan_name"], "Launch")

    def test_payment_history_keeps_fully_allocated(self):
        i = self.inv()
        p = self.call(
            "payment",
            {
                "invoice_id": i["id"],
                "amount": i["total"],
                "reference": "HISTORY",
                "date": "2026-10-31",
                "method": "UPI",
                "note": "Full settlement",
            },
        )
        r = self.call("payments", q={"q": "Test Account"})
        b = next(x for x in r["rows"] if x["id"] == p["id"])
        self.assertEqual(b["available"], 0)
        self.assertEqual(b["note"], "Full settlement")
        self.assertEqual(b["allocations"][0]["invoice_id"], i["id"])

    def test_payment_history_customer_privacy(self):
        i = self.inv()
        other = self.inv()
        self.c.execute(
            "UPDATE invoices SET email='other@example.test' WHERE id=?", (other["id"],)
        )
        bid = self.c.execute(
            "INSERT INTO bank(fingerprint,reference,customer,amount,date,method,note) VALUES('private','PRIVATE REF','Shared Corp',500000,'2026-10-31','NEFT','Confidential note')"
        ).lastrowid
        d.allocate(self.c, bid, i["id"], 10000)
        d.allocate(self.c, bid, other["id"], 20000)
        r = self.call("payments", user=CUSTOMER)
        b = next(x for x in r["rows"] if x["id"] == bid)
        self.assertEqual(b["amount"], 10000)
        self.assertIsNone(b["available"])
        self.assertEqual(len(b["allocations"]), 1)
        self.assertEqual(b["note"], "")
        self.assertNotIn("PRIVATE", b["reference"])

    def test_live_clock(self):
        import datetime

        self.call("clock", {"mode": "live"})
        expected = str(
            datetime.datetime.now(
                datetime.timezone(datetime.timedelta(hours=5, minutes=30))
            ).date()
        )
        self.assertEqual(d.today(self.c), expected)
        self.call("clock", {"mode": "demo", "date": "2026-10-31"})
        self.assertEqual(d.today(self.c), "2026-10-31")

    def test_staff_cannot_change_clock(self):
        with self.assertRaises(PermissionError):
            self.call("clock", {"mode": "live"}, STAFF)

    def test_scheduler_catches_up_once(self):
        self.c.execute("UPDATE subscriptions SET state='Paused'")
        sid = self.sub(start_date="2026-08-31")
        self.call("automation", {"enabled": True})
        self.c.commit()
        server.scheduler_tick()
        server.scheduler_tick()
        self.assertEqual(
            self.c.execute(
                "SELECT COUNT(*) FROM invoices WHERE subscription_id=?", (sid,)
            ).fetchone()[0],
            3,
        )

    def test_smtp_queue_success_and_no_resend(self):
        from unittest.mock import patch

        from renewsure import delivery

        self.c.execute("DELETE FROM outbox")
        d.mail(self.c, "test@unitmail.local", "Test", "Body")
        self.c.commit()
        sent = []
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "fake.local",
                "SMTP_FROM": "sender@example.test",
                "SMTP_USER": "test",
                "SMTP_PASSWORD": "fake-password",
            },
        ):
            self.assertEqual(delivery.deliver_pending(sent.append), 1)
            self.assertEqual(delivery.deliver_pending(sent.append), 0)
        self.assertEqual(len(sent), 1)
        self.assertEqual(
            self.c.execute("SELECT status FROM outbox").fetchone()[0], "Sent"
        )

    def test_smtp_uncertain_failure_requires_review(self):
        from unittest.mock import patch

        from renewsure import delivery

        self.c.execute("DELETE FROM outbox")
        d.mail(self.c, "test@unitmail.local", "Test", "Body")
        self.c.commit()

        def failed(msg):
            raise OSError("Network interrupted")

        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "fake.local",
                "SMTP_FROM": "sender@example.test",
                "SMTP_USER": "test",
                "SMTP_PASSWORD": "fake-password",
            },
        ):
            self.assertEqual(delivery.deliver_pending(failed), 0)
            self.assertEqual(delivery.deliver_pending(lambda m: None), 0)
        self.assertEqual(
            self.c.execute("SELECT status FROM outbox").fetchone()[0],
            "Delivery needs review",
        )

    def test_synthetic_recipient_suppressed(self):
        mid = d.mail(self.c, "finance@example.com", "Test", "Body")
        self.assertEqual(
            self.c.execute("SELECT status FROM outbox WHERE id=?", (mid,)).fetchone()[
                0
            ],
            "Suppressed demo recipient",
        )

    def test_invoice_email_pdf_attachment(self):
        from unittest.mock import patch

        from renewsure import delivery

        i = self.inv()
        self.c.execute("DELETE FROM outbox")
        d.mail(
            self.c,
            "test@unitmail.local",
            "Invoice",
            "Invoice details",
            invoice_id=i["id"],
        )
        self.c.commit()
        sent = []
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "fake.local",
                "SMTP_FROM": "sender@unitmail.local",
                "SMTP_USER": "test",
                "SMTP_PASSWORD": "fake-password",
            },
        ):
            self.assertEqual(delivery.deliver_pending(sent.append), 1)
        attachments = list(sent[0].iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertTrue(attachments[0].get_payload(decode=True).startswith(b"%PDF"))

    def test_expired_reset_not_delivered(self):
        from unittest.mock import patch

        from renewsure import delivery

        self.c.execute("DELETE FROM outbox")
        d.mail(
            self.c,
            "test@unitmail.local",
            "Reset",
            "Open http://localhost/?reset=expired",
            "reset",
        )
        self.c.commit()
        sent = []
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "fake.local",
                "SMTP_FROM": "sender@unitmail.local",
                "SMTP_USER": "test",
                "SMTP_PASSWORD": "fake-password",
            },
        ):
            self.assertEqual(delivery.deliver_pending(sent.append), 0)
        self.assertEqual(sent, [])
        self.assertEqual(
            self.c.execute("SELECT status FROM outbox").fetchone()[0],
            "Expired reset link",
        )

    def test_catalog_product_details_and_edit(self):
        product = self.call(
            "products",
            {
                "name": "Audit Product",
                "type": "Software",
                "sales_price": 123400,
                "cost_price": 40000,
                "notes": "Support included",
            },
        )["id"]
        self.call(
            "products",
            {
                "id": product,
                "name": "Audit Product revised",
                "type": "Service",
                "sales_price": 125000,
                "cost_price": 45000,
                "notes": "Updated",
                "active": False,
            },
        )
        p = d.one(self.c, "SELECT * FROM products WHERE id=?", (product,))
        self.assertEqual(
            (p["type"], p["sales_price"], p["cost_price"], p["notes"], p["active"]),
            ("Service", 125000, 45000, "Updated", 0),
        )

    def test_variant_creation_and_surcharge(self):
        vid = self.call(
            "variants", {"name": "Premium", "product_id": 1, "extra": 56000}
        )["id"]
        ls = s.line_values(
            self.c, [{"product_id": 1, "variant_id": vid, "qty": 1, "tax_id": 1}]
        )
        self.assertEqual(ls[0][4], 106000)

    def test_tax_rules_zero_reduced_standard(self):
        for rate, expected in [(0, 10000), (500, 10500), (1800, 11800)]:
            tid = self.call("taxes", {"name": "Tax " + str(rate), "rate": rate})["id"]
            ls = s.line_values(self.c, [{"product_id": 1, "qty": 1, "tax_id": tid}])
            self.assertEqual(calc(10000, 1, 0, ls[0][5])["total"], expected)

    def test_all_admin_configuration_rejects_staff(self):
        for path in [
            "products",
            "variants",
            "plans",
            "taxes",
            "discounts",
            "templates",
            "staff",
        ]:
            with self.subTest(path=path):
                with self.assertRaises(PermissionError):
                    self.call(path, {}, STAFF)

    def test_customer_all_lists_are_owned(self):
        for path in ["subscriptions", "invoices"]:
            records = self.call(path, user=CUSTOMER)["rows"]
            self.assertTrue(records)
            self.assertTrue(all(r["email"] == CUSTOMER["email"] for r in records))

    def test_customer_cannot_read_other_subscription(self):
        with self.assertRaises(PermissionError):
            self.call("subscription", user=CUSTOMER, q={"id": 4})

    def test_unique_subscription_number(self):
        self.assertNotEqual(self.sub(), self.sub())

    def test_full_state_sequence_and_close(self):
        sid = self.sub()
        self.call("transition", {"id": sid, "state": "Closed"})
        self.assertEqual(
            d.one(self.c, "SELECT state FROM subscriptions WHERE id=?", (sid,))[
                "state"
            ],
            "Closed",
        )
        self.assertEqual(d.rehearsal(self.c, only=sid)["count"], 0)

    def test_early_close_permission(self):
        sid = self.sub(expiry="2026-12-31")
        self.c.execute("UPDATE plans SET allow_close=0 WHERE id=1")
        with self.assertRaises(d.Error):
            self.call("transition", {"id": sid, "state": "Closed"})

    def test_natural_close_allowed_without_early_close(self):
        sid = self.sub(expiry="2026-11-01")
        self.c.execute("UPDATE plans SET allow_close=0 WHERE id=1")
        self.c.execute("UPDATE settings SET value='2026-11-02' WHERE key='clock'")
        self.call("transition", {"id": sid, "state": "Closed"})
        self.assertEqual(
            d.one(self.c, "SELECT state FROM subscriptions WHERE id=?", (sid,))[
                "state"
            ],
            "Closed",
        )

    def test_renewal_permission(self):
        sid = self.sub()
        self.call("transition", {"id": sid, "state": "Closed"})
        self.c.execute("UPDATE plans SET allow_renew=0 WHERE id=1")
        with self.assertRaises(d.Error):
            self.call("transition", {"id": sid, "state": "Active"})

    def test_expired_paused_contract_cannot_bypass_renewal_permission(self):
        sid = self.sub(expiry="2026-11-01")
        self.call("transition", {"id": sid, "state": "Paused"})
        self.c.execute("UPDATE plans SET allow_renew=0 WHERE id=1")
        self.c.execute("UPDATE settings SET value='2026-11-02' WHERE key='clock'")
        with self.assertRaises(d.Error):
            self.call(
                "transition", {"id": sid, "state": "Active", "expiry": "2027-01-01"}
            )

    def test_successful_renewal_new_expiry(self):
        sid = self.sub(expiry="2026-11-01")
        self.call("transition", {"id": sid, "state": "Closed"})
        self.c.execute("UPDATE settings SET value='2026-11-02' WHERE key='clock'")
        self.call("transition", {"id": sid, "state": "Active", "expiry": "2027-11-01"})
        r = d.one(self.c, "SELECT * FROM subscriptions WHERE id=?", (sid,))
        self.assertEqual(
            (r["state"], r["due"], r["expiry"]), ("Active", "2026-11-02", "2027-11-01")
        )

    def test_annual_expiry_closes_in_same_run(self):
        sid = self.sub(plan_id=4, expiry="2026-11-05")
        self.c.execute("UPDATE settings SET value='2026-11-06' WHERE key='clock'")
        r = d.billing(self.c, only=sid)
        self.assertEqual(r["created"], 1)
        self.assertEqual(
            d.one(self.c, "SELECT state FROM subscriptions WHERE id=?", (sid,))[
                "state"
            ],
            "Closed",
        )

    def test_plan_cycle_edit_does_not_rewrite_contract(self):
        sid = self.sub()
        self.c.execute("UPDATE plans SET cycle='daily' WHERE id=1")
        d.billing(self.c, only=sid)
        self.assertEqual(
            d.one(self.c, "SELECT due FROM subscriptions WHERE id=?", (sid,))["due"],
            "2026-11-30",
        )

    def test_daily_weekly_yearly_billing_dates(self):
        for cycle, expected in [
            ("daily", "2026-11-01"),
            ("weekly", "2026-11-07"),
            ("yearly", "2027-10-31"),
        ]:
            self.c.execute("UPDATE plans SET cycle=? WHERE id=1", (cycle,))
            sid = self.sub()
            d.billing(self.c, only=sid)
            self.assertEqual(
                d.one(self.c, "SELECT due FROM subscriptions WHERE id=?", (sid,))[
                    "due"
                ],
                expected,
            )

    def test_discount_fixed_whole_subscription(self):
        did = self.call(
            "discounts",
            {
                "name": "Fixed",
                "kind": "fixed",
                "value": 10000,
                "min_qty": 1,
                "min_purchase": 0,
                "start": "2026-10-01",
                "end": "2026-12-31",
                "limit_uses": 10,
            },
        )["id"]
        sid = self.sub(discount_id=did)
        a = d.rehearsal(self.c, only=sid)["items"][0]
        self.assertEqual((a["discount"], a["tax"], a["total"]), (10000, 36360, 238360))

    def test_discount_minimum_quantity_and_purchase(self):
        for qty, purchase in [(3, 0), (1, 300000)]:
            did = self.call(
                "discounts",
                {
                    "name": "Threshold",
                    "kind": "percent",
                    "value": 1000,
                    "min_qty": qty,
                    "min_purchase": purchase,
                    "start": "2026-10-01",
                    "end": "2026-12-31",
                    "limit_uses": 10,
                },
            )["id"]
            sid = self.sub(discount_id=did)
            self.assertEqual(d.rehearsal(self.c, only=sid)["items"][0]["discount"], 0)

    def test_discount_not_started_and_expired(self):
        for start, end in [("2026-11-01", "2026-12-31"), ("2026-09-01", "2026-10-30")]:
            did = self.call(
                "discounts",
                {
                    "name": "Dates",
                    "kind": "fixed",
                    "value": 50000,
                    "min_qty": 1,
                    "min_purchase": 0,
                    "start": start,
                    "end": end,
                    "limit_uses": 10,
                },
            )["id"]
            sid = self.sub(discount_id=did)
            self.assertEqual(d.rehearsal(self.c, only=sid)["items"][0]["discount"], 0)

    def test_discount_global_limit_across_subscriptions(self):
        did = self.call(
            "discounts",
            {
                "name": "Only once",
                "kind": "fixed",
                "value": 10000,
                "min_qty": 1,
                "min_purchase": 0,
                "start": "2026-10-01",
                "end": "2026-12-31",
                "limit_uses": 1,
            },
        )["id"]
        a = self.sub(discount_id=did)
        b = self.sub(discount_id=did)
        d.billing(self.c, only=a)
        d.billing(self.c, only=b)
        self.assertEqual(
            self.c.execute(
                "SELECT SUM(discount) FROM invoices WHERE subscription_id IN (?,?)",
                (a, b),
            ).fetchone()[0],
            10000,
        )

    def test_product_discount_leaves_other_products_full_price(self):
        did = self.call(
            "discounts",
            {
                "name": "Primary only",
                "kind": "percent",
                "value": 1000,
                "min_qty": 1,
                "min_purchase": 0,
                "start": "2026-10-01",
                "end": "2026-12-31",
                "limit_uses": 5,
                "product_id": 1,
            },
        )["id"]
        sid = self.sub(
            discount_id=did,
            lines=[
                {"product_id": 1, "qty": 2, "tax_id": 1},
                {"product_id": 2, "qty": 1, "tax_id": 1},
            ],
        )
        a = d.rehearsal(self.c, only=sid)["items"][0]
        self.assertEqual(a["lines"][0]["discount"], 10000)
        self.assertEqual(a["lines"][1]["discount"], 0)

    def test_cancelled_invoice_not_reissued(self):
        sid = self.sub()
        d.billing(self.c, only=sid)
        i = d.one(self.c, "SELECT id FROM invoices WHERE subscription_id=?", (sid,))
        self.call("invoice", {"id": i["id"], "action": "cancel"})
        self.assertEqual(d.billing(self.c, only=sid)["created"], 0)

    def test_draft_invoice_cannot_be_emailed(self):
        sid = self.sub()
        d.billing(self.c, only=sid)
        i = d.one(self.c, "SELECT id FROM invoices WHERE subscription_id=?", (sid,))
        with self.assertRaises(d.Error):
            self.call("invoice", {"id": i["id"], "action": "send"})

    def test_invoice_email_uses_customer_recipient(self):
        i = self.inv()
        self.call("invoice", {"id": i["id"], "action": "send"})
        r = d.one(
            self.c, "SELECT recipient,invoice_id FROM outbox ORDER BY id DESC LIMIT 1"
        )
        self.assertEqual(
            (r["recipient"], r["invoice_id"]), (CUSTOMER["email"], i["id"])
        )

    def test_import_deduplicates_manual_payment(self):
        i = self.inv()
        self.call(
            "payment",
            {
                "invoice_id": i["id"],
                "amount": 10000,
                "reference": "BANK-ONE",
                "date": "2026-10-31",
                "method": "NEFT",
            },
        )
        r = self.call(
            "import",
            {
                "csv": "reference,customer,amount,date,method\nBANK-ONE,Test Account,100.00,2026-10-31,NEFT\n"
            },
        )
        self.assertEqual((r["imported"], r["duplicates"]), (0, 1))
        self.assertEqual(d.invoice(self.c, i["id"])["paid"], 10000)

    def test_manual_payment_deduplicates_import(self):
        i = self.inv()
        self.call(
            "import",
            {
                "csv": "reference,customer,amount,date,method\nBANK-ONE,Test Account,100.00,2026-10-31,NEFT\n"
            },
        )
        with self.assertRaises(d.Error):
            self.call(
                "payment",
                {
                    "invoice_id": i["id"],
                    "amount": 10000,
                    "reference": "BANK-ONE",
                    "date": "2026-10-31",
                    "method": "NEFT",
                },
            )

    def test_partial_overdue_in_both_filters(self):
        i = self.inv()
        self.call(
            "payment",
            {
                "invoice_id": i["id"],
                "amount": 10000,
                "reference": "PARTIAL",
                "date": "2026-10-31",
                "method": "UPI",
            },
        )
        self.c.execute("UPDATE settings SET value='2026-11-01' WHERE key='clock'")
        self.assertTrue(
            any(
                r["id"] == i["id"]
                for r in self.call(
                    "invoices", q={"q": "Test Account", "status": "Overdue"}
                )["rows"]
            )
        )
        self.assertTrue(
            any(
                r["id"] == i["id"]
                for r in self.call(
                    "reconcile", q={"q": "Test Account", "status": "Overdue"}
                )["rows"]
            )
        )

    def test_payment_method_date_note_and_invoice_balance(self):
        i = self.inv()
        bid = self.call(
            "payment",
            {
                "invoice_id": i["id"],
                "amount": 20000,
                "reference": "PAY-NOTE",
                "date": "2026-10-30",
                "method": "UPI",
                "note": "First installment",
            },
        )["id"]
        b = d.one(self.c, "SELECT * FROM bank WHERE id=?", (bid,))
        self.assertEqual(
            (b["method"], b["date"], b["note"]),
            ("UPI", "2026-10-30", "First installment"),
        )
        self.assertEqual(d.invoice(self.c, i["id"])["balance"], i["total"] - 20000)

    def test_dashboard_numbers_match_payment_and_overdue(self):
        i = self.inv()
        self.call(
            "payment",
            {
                "invoice_id": i["id"],
                "amount": 20000,
                "reference": "DASH",
                "date": "2026-10-31",
                "method": "UPI",
            },
        )
        self.c.execute("UPDATE settings SET value='2026-11-01' WHERE key='clock'")
        r = self.call(
            "dashboard",
            q={"q": "Test Account", "from": "2026-10-01", "to": "2026-11-01"},
        )
        self.assertEqual(
            (
                r["active"],
                r["invoiced"],
                r["received"],
                r["outstanding"],
                r["overdue_count"],
                r["overdue_total"],
            ),
            (1, i["total"], 20000, i["total"] - 20000, 1, i["total"] - 20000),
        )

    def test_bulk_due_batch_has_no_skipped_or_duplicate_periods(self):
        p = d.rehearsal(self.c)
        self.assertGreater(p["count"], 9000)
        r = d.billing(self.c)
        self.assertEqual(r["created"], p["count"])
        self.assertEqual(d.rehearsal(self.c)["count"], 0)
        self.assertEqual(d.billing(self.c)["created"], 0)
        self.assertTrue(all(x["passed"] for x in d.checks(self.c)))

    def test_expiry_scheduler_independent_of_invoice_schedule(self):
        sid = self.sub(expiry="2026-11-01")
        self.c.execute("UPDATE settings SET value='2026-11-02' WHERE key='clock'")
        self.call("automation", {"enabled": False})
        self.c.commit()
        server.scheduler_tick()
        self.assertEqual(
            d.one(self.c, "SELECT state FROM subscriptions WHERE id=?", (sid,))[
                "state"
            ],
            "Closed",
        )
        p = d.rehearsal(self.c, only=sid)
        self.assertEqual(p["count"], 1)
        r = d.billing(self.c, only=sid)
        self.assertEqual(r["created"], 1)
        self.assertEqual(d.billing(self.c, only=sid)["created"], 0)

    def test_expired_paused_scheduler_never_bills_paused_period(self):
        sid = self.sub(expiry="2026-11-01")
        self.call("transition", {"id": sid, "state": "Paused"})
        self.c.execute("UPDATE settings SET value='2026-11-02' WHERE key='clock'")
        self.call("automation", {"enabled": False})
        self.c.commit()
        server.scheduler_tick()
        self.assertEqual(
            d.one(self.c, "SELECT state FROM subscriptions WHERE id=?", (sid,))[
                "state"
            ],
            "Closed",
        )
        self.assertEqual(d.rehearsal(self.c, only=sid)["count"], 0)

    def edit_payload(self, sid, **over):
        sub = self.call("subscription", q={"id": sid})
        lines = [
            {
                "line_id": line["id"],
                "product_id": line["product_id"],
                "variant_id": line["variant_id"] or 0,
                "qty": line["qty"],
                "tax_id": line["tax_id"] or 0,
            }
            for line in sub["lines"]
        ]
        result = {
            "id": sid,
            "lines": lines,
            "expiry": sub["expiry"],
            "terms_days": sub["terms_days"],
            "quotation_until": sub["quotation_until"],
            "discount_id": sub["discount_id"] or 0,
        }
        result.update(over)
        return result

    def test_contract_edit_preserves_price_and_tax_snapshots(self):
        sid = self.sub()
        self.c.execute("UPDATE plans SET price=1 WHERE id=1")
        self.c.execute("UPDATE taxes SET rate=500 WHERE id=1")
        data = self.edit_payload(sid)
        data["lines"][0]["qty"] = 3
        self.call("subscriptions", data)
        line = d.one(
            self.c, "SELECT * FROM subscription_lines WHERE subscription_id=?", (sid,)
        )
        self.assertEqual(
            (line["unit_price"], line["tax_rate"], line["qty"]), (106000, 1800, 3)
        )

    def test_retired_product_does_not_block_existing_contract_edit(self):
        sid = self.sub()
        self.c.execute("UPDATE products SET active=0 WHERE id=1")
        self.call("subscriptions", self.edit_payload(sid))
        self.assertEqual(
            self.call("subscription", q={"id": sid})["calculation"]["total"], 250160
        )

    def test_explicit_reprice_keeps_old_invoice_immutable(self):
        i = self.inv()
        self.c.execute("UPDATE plans SET price=100000 WHERE id=1")
        self.call(
            "subscriptions", self.edit_payload(i["subscription_id"], reprice=True)
        )
        self.assertEqual(
            self.call("subscription", q={"id": i["subscription_id"]})["lines"][0][
                "unit_price"
            ],
            156000,
        )
        self.assertEqual(d.invoice(self.c, i["id"])["total"], 250160)

    def test_line_cannot_be_copied_from_other_customer_contract(self):
        sid = self.sub()
        other = self.sub()
        data = self.edit_payload(other)
        data["id"] = sid
        with self.assertRaises(d.Error):
            self.call("subscriptions", data)

    def test_addon_can_be_enabled_and_removed(self):
        sid = self.sub()
        data = self.edit_payload(sid)
        data["lines"].append({"product_id": 2, "variant_id": 0, "qty": 1, "tax_id": 1})
        self.call("subscriptions", data)
        self.assertEqual(len(self.call("subscription", q={"id": sid})["lines"]), 2)
        data = self.edit_payload(sid)
        data["lines"] = data["lines"][:1]
        self.call("subscriptions", data)
        self.assertEqual(len(self.call("subscription", q={"id": sid})["lines"]), 1)


if __name__ == "__main__":
    unittest.main()
