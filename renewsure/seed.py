"""Deterministic local demonstration fixtures; never used to change existing accounts."""

import secrets

from .money import calc
from .security import password


def populate_demo(c):
    for name, role in [
        ("Admin", "admin"),
        ("Staff", "staff"),
        ("Customer", "customer"),
    ]:
        s = secrets.token_hex(16)
        c.execute(
            "INSERT INTO users(email,name,role,salt,hash) VALUES(?,?,?,?,?)",
            (role + "@renewsure.demo", name, role, s, password("DemoPass!2026", s)),
        )
    c.executemany(
        "INSERT INTO plans(name,price,cycle,tax) VALUES(?,?,?,?)",
        [
            ("Launch", 50000, "monthly", 1800),
            ("Growth", 150000, "monthly", 1800),
            ("Scale", 500000, "monthly", 1800),
            ("Annual Suite", 1200000, "yearly", 1800),
        ],
    )
    c.execute("INSERT INTO settings VALUES('clock','2026-10-31')")
    names = [
        "Malabar Design",
        "Kochi Cloud",
        "Harbour Labs",
        "Spice Route Retail",
        "Bluewater Systems",
        "Coconut Studio",
        "Metro Works",
        "Backwater Digital",
    ]
    plan_by_id = {r["id"]: r for r in c.execute("SELECT * FROM plans")}
    for i in range(1, 10051):
        email = "customer@renewsure.demo" if i <= 3 else f"finance{i}@example.test"
        name = names[(i - 1) % 8] + f" {i:04d}"
        plan = (i - 1) % 4 + 1
        qty = i % 5 + 1
        due = f"2026-10-{i % 28 + 1:02d}"
        c.execute(
            "INSERT INTO subscriptions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                name,
                email,
                plan,
                qty,
                "Active" if i % 17 else "Paused",
                due,
                50000 if i % 7 == 0 else 0,
                "2026-10-15",
                2,
                0,
            ),
        )
        if i % 5:
            p = plan_by_id[plan]
            a = calc(p["price"], qty, 0, p["tax"])
            cur = c.execute(
                "INSERT INTO invoices(subscription_id,period,customer,email,subtotal,discount,tax,total) VALUES(?,?,?,?,?,?,?,?)",
                (i, "2026-09-01", name, email, *a.values()),
            )
            inv = cur.lastrowid
            if i % 3:
                paid = a["total"] if i % 4 else a["total"] // 2
                b = c.execute(
                    "INSERT INTO bank(fingerprint,reference,customer,amount,date,method) VALUES(?,?,?,?,?,?)",
                    (f"seed{i}", f"INV-{inv}", name, paid, "2026-09-10", "NEFT"),
                ).lastrowid
                c.execute(
                    "INSERT INTO allocations(bank_id,invoice_id,amount) VALUES(?,?,?)",
                    (b, inv, paid),
                )
