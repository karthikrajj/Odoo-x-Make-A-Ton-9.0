"""Idempotent database migrations, preserving existing records."""

import json

from . import database as db
from .database import rows
from .domain import mrr


def migrate():
    with db.conn() as c:
        additions = {
            "plans": {
                "available_from": "TEXT DEFAULT '2020-01-01'",
                "available_to": "TEXT",
                "allow_pause": "INTEGER DEFAULT 1",
                "allow_close": "INTEGER DEFAULT 1",
                "allow_renew": "INTEGER DEFAULT 1",
                "auto_close": "INTEGER DEFAULT 1",
            },
            "subscriptions": {
                "start_date": "TEXT",
                "expiry": "TEXT",
                "terms_days": "INTEGER DEFAULT 15",
                "quotation_until": "TEXT",
                "discount_id": "INTEGER",
                "anchor_day": "INTEGER",
                "cycle": "TEXT",
                "close_reason": "TEXT",
            },
            "invoices": {
                "due_date": "TEXT",
                "disputed": "INTEGER DEFAULT 0",
                "lines": "TEXT",
                "expected": "INTEGER",
                "notes": "TEXT DEFAULT ''",
            },
            "bank": {"note": "TEXT DEFAULT ''"},
            "outbox": {"invoice_id": "INTEGER"},
            "subscription_lines": {"tax_id": "INTEGER"},
        }
        for table, cols in additions.items():
            existing = {r[1] for r in c.execute("PRAGMA table_info(" + table + ")")}
            if not existing:
                continue
            for k, v in cols.items():
                if k not in existing:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {k} {v}")
        c.executescript("""
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT NOT NULL,type TEXT,sales_price INTEGER,cost_price INTEGER,notes TEXT,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS variants(id INTEGER PRIMARY KEY,product_id INTEGER REFERENCES products(id),name TEXT,extra INTEGER);
CREATE TABLE IF NOT EXISTS taxes(id INTEGER PRIMARY KEY,name TEXT,rate INTEGER,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS discount_rules(id INTEGER PRIMARY KEY,name TEXT,kind TEXT,value INTEGER,min_qty INTEGER,min_purchase INTEGER,start TEXT,end TEXT,limit_uses INTEGER,used INTEGER DEFAULT 0,product_id INTEGER,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS templates(id INTEGER PRIMARY KEY,name TEXT,plan_id INTEGER,valid_days INTEGER,lines TEXT);
CREATE TABLE IF NOT EXISTS subscription_lines(id INTEGER PRIMARY KEY,subscription_id INTEGER REFERENCES subscriptions(id),product_id INTEGER,variant_id INTEGER,description TEXT,qty INTEGER,unit_price INTEGER,tax_rate INTEGER);
CREATE TABLE IF NOT EXISTS discount_applications(id INTEGER PRIMARY KEY,discount_id INTEGER,invoice_id INTEGER UNIQUE,amount INTEGER);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,recipient TEXT,subject TEXT,body TEXT,kind TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP,status TEXT DEFAULT 'Local mailbox');
CREATE TABLE IF NOT EXISTS resets(token TEXT PRIMARY KEY,user_id INTEGER,expires REAL,used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS reminder_events(invoice_id INTEGER,stage INTEGER,mail_id INTEGER,PRIMARY KEY(invoice_id,stage));
CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,date TEXT,subscription_id INTEGER,email TEXT,kind TEXT,amount INTEGER);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,date TEXT,created INTEGER,skipped INTEGER,total INTEGER,revision INTEGER,at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS run_items(run_id INTEGER,subscription_id INTEGER,period TEXT,invoice_id INTEGER,reason TEXT);
CREATE INDEX IF NOT EXISTS ix_lines_sub ON subscription_lines(subscription_id);
CREATE INDEX IF NOT EXISTS ix_bank_alloc ON allocations(bank_id);
CREATE INDEX IF NOT EXISTS ix_invoice_due ON invoices(due_date,state);
CREATE INDEX IF NOT EXISTS ix_moves_date ON movements(date);
""")
        if "tax_id" not in {
            r[1] for r in c.execute("PRAGMA table_info(subscription_lines)")
        }:
            c.execute("ALTER TABLE subscription_lines ADD COLUMN tax_id INTEGER")
        if "invoice_id" not in {r[1] for r in c.execute("PRAGMA table_info(outbox)")}:
            c.execute("ALTER TABLE outbox ADD COLUMN invoice_id INTEGER")
        c.execute("INSERT OR IGNORE INTO settings VALUES('revision','1')")
        c.execute("INSERT OR IGNORE INTO settings VALUES('clock_mode','demo')")
        c.execute("INSERT OR IGNORE INTO settings VALUES('auto_billing','0')")
        c.execute("CREATE INDEX IF NOT EXISTS ix_bank_date ON bank(date)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS ix_bank_identity ON bank(reference COLLATE NOCASE,date,amount,customer COLLATE NOCASE)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS ix_sub_email ON subscriptions(email)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS ix_outbox_recipient ON outbox(recipient,id)"
        )
        if not c.execute("SELECT 1 FROM products").fetchone():
            for p in rows(c, "SELECT * FROM plans"):
                c.execute(
                    "INSERT INTO products(id,name,type,sales_price,cost_price,notes) VALUES(?,?,?,?,?,?)",
                    (
                        p["id"],
                        p["name"] + " Software",
                        "Service",
                        p["price"],
                        p["price"] // 3,
                        "Seeded subscription software",
                    ),
                )
            c.execute(
                "INSERT INTO variants(product_id,name,extra) VALUES(1,'Odoo brand',56000)"
            )
            c.executemany(
                "INSERT INTO taxes(name,rate) VALUES(?,?)",
                [("Standard 18%", 1800), ("Reduced 5%", 500), ("Zero rated", 0)],
            )
        c.execute(
            "INSERT INTO subscription_lines(subscription_id,product_id,description,qty,unit_price,tax_rate) SELECT s.id,p.id,p.name,s.qty,p.price,p.tax FROM subscriptions s JOIN plans p ON s.plan_id=p.id WHERE NOT EXISTS(SELECT 1 FROM subscription_lines l WHERE l.subscription_id=s.id)"
        )
        c.execute(
            "UPDATE subscription_lines SET tax_id=(SELECT id FROM taxes WHERE taxes.rate=subscription_lines.tax_rate ORDER BY id LIMIT 1) WHERE tax_id IS NULL"
        )
        c.execute(
            "UPDATE subscriptions SET cycle=(SELECT cycle FROM plans WHERE plans.id=subscriptions.plan_id) WHERE cycle IS NULL"
        )
        c.execute(
            "UPDATE subscriptions SET start_date=COALESCE(start_date,due),anchor_day=COALESCE(anchor_day,CAST(substr(due,9,2) AS INT))"
        )
        c.execute(
            "UPDATE invoices SET due_date=date(period,'+15 days'),expected=total WHERE due_date IS NULL"
        )
        c.execute(
            "UPDATE invoices SET state='Paid' WHERE state='Confirmed' AND total<=COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0)"
        )
        if not c.execute("SELECT 1 FROM movements").fetchone():
            for s in rows(
                c,
                "SELECT s.*,p.cycle FROM subscriptions s JOIN plans p ON s.plan_id=p.id WHERE state='Active'",
            ):
                c.execute(
                    "INSERT INTO movements(date,subscription_id,email,kind,amount) VALUES(?,?,?,?,?)",
                    ("2026-09-01", s["id"], s["email"], "opening", mrr(c, s)),
                )
        if not c.execute("SELECT 1 FROM templates").fetchone():
            c.execute(
                "INSERT INTO templates(name,plan_id,valid_days,lines) VALUES(?,?,?,?)",
                (
                    "Launch Ãƒâ€šÃ‚Â· Odoo starter",
                    1,
                    14,
                    json.dumps(
                        [{"product_id": 1, "variant_id": 1, "qty": 1, "tax_id": 1}]
                    ),
                ),
            )
