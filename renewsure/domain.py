"""RenewSure domain services. Money is integer paise; tax/percentage rates are basis points."""

import calendar
import datetime as dt
import json
import re
import secrets
from decimal import Decimal, InvalidOperation

from . import security
from .config import email_configured
from .database import one, rows
from .errors import Error
from .money import calc, monthly_value


def today(c):
    mode = c.execute("SELECT value FROM settings WHERE key='clock_mode'").fetchone()
    if mode and mode[0] == "live":
        return str(
            dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
        )
    return c.execute("SELECT value FROM settings WHERE key='clock'").fetchone()[0]


def date(s):
    try:
        return str(dt.date.fromisoformat(str(s)))
    except ValueError:
        raise Error("Use a valid date in YYYY-MM-DD format")


def integer(v, low=0, high=100000000000):
    try:
        n = int(str(v))
        if not low <= n <= high:
            raise ValueError()
        return n
    except (ValueError, TypeError):
        raise Error(f"Enter a whole number between {low} and {high}")


def text(v, limit=250):
    s = str(v or "").strip()
    if not s or len(s) > limit:
        raise Error(f"Text is required and must be at most {limit} characters")
    return s


def email(v):
    s = text(v).lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", s):
        raise Error("Enter a valid email address")
    return s


def money(v):
    try:
        d = Decimal(str(v))
        if (
            not d.is_finite()
            or d < 0
            or d > Decimal("1000000000")
            or d * 100 != (d * 100).to_integral_value()
        ):
            raise ValueError()
        return int(d * 100)
    except (ValueError, InvalidOperation):
        raise Error("Amount must be positive with at most two decimal places")


def audit(c, event, actor="system"):
    c.execute("INSERT INTO audit(event) VALUES(?)", (actor + ": " + event,))


def bump(c):
    c.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")


def mrr(c, s):
    total = c.execute(
        "SELECT COALESCE(SUM(qty*unit_price),0) FROM subscription_lines WHERE subscription_id=?",
        (s["id"],),
    ).fetchone()[0]
    cycle = (
        s.get("cycle")
        or one(c, "SELECT cycle FROM plans WHERE id=?", (s["plan_id"],))["cycle"]
    )
    return monthly_value(total, cycle)


def movement(c, s, kind, amount):
    c.execute(
        "INSERT INTO movements(date,subscription_id,email,kind,amount) VALUES(?,?,?,?,?)",
        (today(c), s["id"], s["email"], kind, amount),
    )


def next_period(s, period):
    d = dt.date.fromisoformat(period)
    cycle = s["cycle"]
    if cycle in ["daily", "weekly"]:
        return str(d + dt.timedelta(days=1 if cycle == "daily" else 7))
    month = d.month + (12 if cycle == "yearly" else 1)
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return str(
        dt.date(
            year,
            month,
            min(s.get("anchor_day") or d.day, calendar.monthrange(year, month)[1]),
        )
    )


def quote(c, s, period, used=None, legacy_used=None, line_cache=None, rule_cache=None):
    lines = (
        line_cache.get(s["id"], [])
        if line_cache is not None
        else rows(
            c,
            "SELECT * FROM subscription_lines WHERE subscription_id=? ORDER BY id",
            (s["id"],),
        )
    )
    base = sum(line["qty"] * line["unit_price"] for line in lines)
    rule = None
    amount = 0
    eligible = lines
    if s.get("discount_id"):
        rule = (
            rule_cache[s["discount_id"]]
            if rule_cache is not None
            else one(c, "SELECT * FROM discount_rules WHERE id=?", (s["discount_id"],))
        )
        count = (used or {}).get(rule["id"], rule["used"])
        eligible = [
            line
            for line in lines
            if not rule["product_id"] or line["product_id"] == rule["product_id"]
        ]
        subtotal = sum(line["qty"] * line["unit_price"] for line in eligible)
        if (
            rule["active"]
            and rule["start"] <= period <= rule["end"]
            and count < rule["limit_uses"]
            and sum(line["qty"] for line in eligible) >= rule["min_qty"]
            and subtotal >= rule["min_purchase"]
        ):
            amount = min(
                subtotal,
                rule["value"]
                if rule["kind"] == "fixed"
                else (subtotal * rule["value"] + 5000) // 10000,
            )
    elif (
        s.get("discount")
        and s.get("discount_end")
        and period <= s["discount_end"]
        and (s["discount_used"] if legacy_used is None else legacy_used)
        < s["discount_limit"]
    ):
        amount = min(base, s["discount"])
    eligible_total = sum(line["qty"] * line["unit_price"] for line in eligible)
    remaining = amount
    output = []
    last = eligible[-1]["id"] if eligible else None
    for line in lines:
        sub = line["qty"] * line["unit_price"]
        disc = 0
        if line in eligible and eligible_total:
            disc = remaining if line["id"] == last else amount * sub // eligible_total
            remaining -= disc
        tax = calc(line["unit_price"], line["qty"], disc, line["tax_rate"])["tax"]
        output.append(
            {
                **line,
                "subtotal": sub,
                "discount": disc,
                "tax": tax,
                "total": sub - disc + tax,
            }
        )
    return {
        "lines": output,
        "subtotal": base,
        "discount": amount,
        "tax": sum(line["tax"] for line in output),
        "total": sum(line["total"] for line in output),
        "discount_id": rule["id"] if rule and amount else None,
    }


def rehearsal(c, on=None, only=None):
    on = on or today(c)
    conditions = "WHERE (s.due<=? OR s.expiry<?)"
    params = [on, on]
    if only:
        conditions += " AND s.id=?"
        params.append(only)
    subs = rows(
        c,
        "SELECT s.*,p.cycle,p.auto_close FROM subscriptions s JOIN plans p ON p.id=s.plan_id "
        + conditions
        + " ORDER BY s.due,s.id",
        params,
    )
    line_cache = {}
    only_args = (only,) if only else ()
    line_query = (
        "SELECT * FROM subscription_lines"
        + (" WHERE subscription_id=?" if only else "")
        + " ORDER BY id"
    )
    for line in rows(c, line_query, only_args):
        line_cache.setdefault(line["subscription_id"], []).append(line)
    rule_cache = {r["id"]: r for r in rows(c, "SELECT * FROM discount_rules")}
    exists = {
        (r["subscription_id"], r["period"]): r["id"]
        for r in c.execute(
            "SELECT id,subscription_id,period FROM invoices"
            + (" WHERE subscription_id=?" if only else ""),
            only_args,
        )
    }
    used = {}
    items = []
    skips = []
    expired = []
    for s in subs:
        if (
            s["state"] == "Paused"
            and s["expiry"]
            and s["expiry"] < on
            and s["auto_close"]
        ):
            expired.append(s["id"])
            skips.append(
                {
                    "id": s["id"],
                    "customer": s["customer"],
                    "reason": "Paused contract expired; automatic close",
                }
            )
            continue
        if s["state"] != "Active" and not (
            s["state"] == "Closed" and s.get("close_reason") == "expiry"
        ):
            skips.append(
                {"id": s["id"], "customer": s["customer"], "reason": s["state"]}
            )
            continue
        if (
            s["state"] == "Active"
            and s["expiry"]
            and s["expiry"] < on
            and s["due"] > on
            and s["auto_close"]
        ):
            expired.append(s["id"])
            skips.append(
                {
                    "id": s["id"],
                    "customer": s["customer"],
                    "reason": "Contract expired; automatic close",
                }
            )
            continue
        period = s["due"]
        legacy_count = s["discount_used"]
        count = 0
        while period <= on:
            if s["expiry"] and period > s["expiry"]:
                skips.append(
                    {
                        "id": s["id"],
                        "customer": s["customer"],
                        "reason": "Contract expired",
                    }
                )
                if s["auto_close"] and s["state"] == "Active":
                    expired.append(s["id"])
                break
            if (s["id"], period) in exists:
                skips.append(
                    {
                        "id": s["id"],
                        "customer": s["customer"],
                        "reason": "Already invoiced",
                        "period": period,
                    }
                )
            else:
                a = quote(c, s, period, used, legacy_count, line_cache, rule_cache)
                if a["discount_id"]:
                    used[a["discount_id"]] = (
                        used.get(a["discount_id"], rule_cache[a["discount_id"]]["used"])
                        + 1
                    )
                if a["discount"]:
                    legacy_count += 1
                items.append(
                    {
                        "id": s["id"],
                        "customer": s["customer"],
                        "email": s["email"],
                        "period": period,
                        "due_date": str(
                            dt.date.fromisoformat(period)
                            + dt.timedelta(days=s["terms_days"])
                        ),
                        **a,
                    }
                )
            period = next_period(s, period)
            count += 1
            if count > 400:
                raise Error(
                    "More than 400 periods are overdue. Advance in smaller billing batches."
                )
            if (
                s["state"] == "Active"
                and s["expiry"]
                and s["expiry"] < on
                and s["auto_close"]
                and s["id"] not in expired
            ):
                expired.append(s["id"])
    return {
        "items": items,
        "skips": skips,
        "expired": expired,
        "count": len(items),
        "total": sum(i["total"] for i in items),
        "revision": int(
            one(c, "SELECT value FROM settings WHERE key='revision'")["value"]
        ),
        "date": on,
    }


def billing(c, revision=None, only=None):
    p = rehearsal(c, only=only)
    if revision is not None and integer(revision) != p["revision"]:
        raise Error(
            "Data changed after preview. Refresh rehearsal before running billing."
        )
    run = c.execute(
        "INSERT INTO runs(date,created,skipped,total,revision) VALUES(?,?,?,?,?)",
        (p["date"], p["count"], len(p["skips"]), p["total"], p["revision"]),
    ).lastrowid
    for a in p["items"]:
        cur = c.execute(
            "INSERT INTO invoices(subscription_id,period,customer,email,subtotal,discount,tax,total,state,due_date,lines,expected) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                a["id"],
                a["period"],
                a["customer"],
                a["email"],
                a["subtotal"],
                a["discount"],
                a["tax"],
                a["total"],
                "Draft",
                a["due_date"],
                json.dumps(a["lines"]),
                a["total"],
            ),
        )
        iid = cur.lastrowid
        if a["discount_id"]:
            c.execute(
                "UPDATE discount_rules SET used=used+1 WHERE id=?", (a["discount_id"],)
            )
            c.execute(
                "INSERT INTO discount_applications(discount_id,invoice_id,amount) VALUES(?,?,?)",
                (a["discount_id"], iid, a["discount"]),
            )
        elif a["discount"]:
            c.execute(
                "UPDATE subscriptions SET discount_used=discount_used+1 WHERE id=?",
                (a["id"],),
            )
        c.execute(
            "INSERT INTO run_items VALUES(?,?,?,?,?)",
            (run, a["id"], a["period"], iid, "Created draft invoice"),
        )
    for a in p["skips"]:
        c.execute(
            "INSERT INTO run_items VALUES(?,?,?,?,?)",
            (run, a["id"], a.get("period"), None, a["reason"]),
        )
    for s in rows(
        c,
        'SELECT s.*,p.cycle FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE (s.state="Active" OR (s.state="Closed" AND s.close_reason="expiry")) AND (s.due<=? OR s.expiry<?)'
        + (" AND s.id=?" if only else ""),
        (p["date"], p["date"]) + ((only,) if only else ()),
    ):
        period = s["due"]
        while period <= p["date"] and (not s["expiry"] or period <= s["expiry"]):
            period = next_period(s, period)
        c.execute("UPDATE subscriptions SET due=? WHERE id=?", (period, s["id"]))
        if s["id"] in p["expired"]:
            movement(c, s, "churn", -mrr(c, s))
            c.execute(
                "UPDATE subscriptions SET state='Closed',close_reason='expiry' WHERE id=?",
                (s["id"],),
            )
    for sid in p["expired"]:
        c.execute(
            "UPDATE subscriptions SET state='Closed',close_reason='paused_expiry' WHERE id=? AND state='Paused'",
            (sid,),
        )
    audit(
        c,
        f"Billing run {run}: {p['count']} draft invoices; {len(p['skips'])} explained skips",
    )
    bump(c)
    return {"created": p["count"], "run_id": run, "total": p["total"]}


def close_expired(c):
    """Expire independently of invoice automation; preserve earned, uninvoiced periods."""
    ended = rows(
        c,
        "SELECT s.*,p.cycle FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.state IN ('Active','Paused') AND p.auto_close=1 AND s.expiry<?",
        (today(c),),
    )
    for s in ended:
        if s["state"] == "Active":
            movement(c, s, "churn", -mrr(c, s))
        reason = "expiry" if s["state"] == "Active" else "paused_expiry"
        c.execute(
            "UPDATE subscriptions SET state='Closed',close_reason=? WHERE id=?",
            (reason, s["id"]),
        )
        audit(
            c,
            f"Automatically closed expired SUB-{s['id']}; prior unbilled periods remain recoverable",
        )
    if ended:
        bump(c)
    return len(ended)


def new_user(c, d, role="customer"):
    e = email(d.get("email"))
    p = d.get("password", "")
    if not security.valid(p):
        raise Error(
            "Password must exceed 8 characters and include uppercase, lowercase and a special character"
        )
    if c.execute("SELECT 1 FROM users WHERE email=?", (e,)).fetchone():
        raise Error("An account already exists for that email")
    salt = secrets.token_hex(16)
    uid = c.execute(
        "INSERT INTO users(email,name,role,salt,hash) VALUES(?,?,?,?,?)",
        (e, text(d.get("name")), role, salt, security.password(p, salt)),
    ).lastrowid
    audit(c, "Created " + role + " account " + e)
    return uid


def mail(c, to, subject, body, kind="invoice", invoice_id=None):
    status = (
        "Suppressed demo recipient"
        if (
            to.rsplit("@", 1)[-1].endswith((".test", ".demo", ".invalid", ".example"))
            or to.rsplit("@", 1)[-1] in ["example.com", "example.org", "example.net"]
        )
        else "Queued"
        if email_configured()
        else "Waiting for email setup"
    )
    return c.execute(
        "INSERT INTO outbox(recipient,subject,body,kind,status,invoice_id) VALUES(?,?,?,?,?,?)",
        (to, subject, body, kind, status, invoice_id),
    ).lastrowid


def invoice(c, iid, user=None):
    i = one(
        c,
        "SELECT i.*,COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=i.id),0) paid FROM invoices i WHERE id=?",
        (iid,),
    )
    if user and user["role"] == "customer" and i["email"] != user["email"]:
        raise PermissionError("You can only access your own invoice")
    i["lines"] = (
        json.loads(i["lines"])
        if i["lines"]
        else [
            {
                "description": "Historical subscription charge",
                "qty": 1,
                "unit_price": i["subtotal"],
                "subtotal": i["subtotal"],
                "discount": i["discount"],
                "tax": i["tax"],
                "total": i["total"],
            }
        ]
    )
    i["balance"] = i["total"] - i["paid"]
    return i


def allocate(c, bid, iid, amount):
    b = one(
        c,
        "SELECT *,amount-COALESCE((SELECT SUM(amount) FROM allocations WHERE bank_id=bank.id),0) available FROM bank WHERE id=?",
        (bid,),
    )
    i = invoice(c, iid)
    amount = integer(amount, 1)
    if i["state"] not in ["Confirmed", "Paid"]:
        raise Error("Confirm the invoice before recording payment")
    if amount > min(b["available"], i["balance"]):
        raise Error("Allocation exceeds transaction funds or invoice balance")
    c.execute(
        "INSERT INTO allocations(bank_id,invoice_id,amount) VALUES(?,?,?)",
        (bid, iid, amount),
    )
    if amount == i["balance"]:
        c.execute("UPDATE invoices SET state='Paid' WHERE id=?", (iid,))
    audit(c, f"Allocated {amount} paise from bank {bid} to invoice {iid}")
    bump(c)


def candidates(c, b):
    invoices = rows(
        c,
        "SELECT i.id,i.customer,i.total-COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=i.id),0) balance FROM invoices i WHERE state='Confirmed' AND (lower(customer)=lower(?) OR id=?) LIMIT 20",
        (
            b["customer"],
            int(re.search(r"(?i)INV[- #]*(\d+)", b["reference"]).group(1))
            if re.search(r"(?i)INV[- #]*(\d+)", b["reference"])
            else -1,
        ),
    )
    out = []
    for i in invoices:
        if i["balance"] <= 0:
            continue
        ref = bool(re.search(r"(?i)\bINV[- #]*" + str(i["id"]) + r"\b", b["reference"]))
        same = i["customer"].casefold() == b["customer"].casefold()
        exact = i["balance"] == b["available"]
        out.append(
            {
                **i,
                "amount": min(i["balance"], b["available"]),
                "confidence": "High"
                if ref and exact and same
                else "Medium"
                if ref or same and exact
                else "Low",
                "reason": ", ".join(
                    [
                        s
                        for s, ok in [
                            ("Invoice reference", ref),
                            ("Customer name", same),
                            ("Exact balance", exact),
                        ]
                        if ok
                    ]
                ),
            }
        )
    return sorted(
        out, key=lambda x: {"High": 0, "Medium": 1, "Low": 2}[x["confidence"]]
    )[:3]


def chase(c, manual=None):
    result = []
    on = today(c)
    for i in rows(
        c,
        "SELECT i.*,total-COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=i.id),0) balance FROM invoices i WHERE state='Confirmed' AND disputed=0 AND due_date<=?",
        (on,),
    ):
        if manual and i["id"] != manual:
            continue
        if i["balance"] <= 0:
            continue
        days = (dt.date.fromisoformat(on) - dt.date.fromisoformat(i["due_date"])).days
        stage = 7 if days >= 7 else 3 if days >= 3 else 0
        if c.execute(
            "SELECT 1 FROM reminder_events WHERE invoice_id=? AND stage=?",
            (i["id"], stage),
        ).fetchone():
            continue
        mid = mail(
            c,
            i["email"],
            f"Payment reminder ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· INV-{i['id']}",
            f"Hello {i['customer']},\nInvoice INV-{i['id']} has an outstanding balance of INR {i['balance'] / 100:.2f}. Due date: {i['due_date']}. Please contact Brightloop if you need help.",
            "reminder",
        )
        c.execute("INSERT INTO reminder_events VALUES(?,?,?)", (i["id"], stage, mid))
        result.append(mid)
    return result


def checks(c):
    tests = [
        (
            "Invoice totals equal line calculations",
            "SELECT COUNT(*) FROM invoices WHERE subtotal-discount+tax<>total",
        ),
        (
            "No duplicate subscription-period invoices",
            "SELECT COUNT(*) FROM (SELECT 1 FROM invoices GROUP BY subscription_id,period HAVING COUNT(*)>1)",
        ),
        (
            "No invoice overallocated",
            "SELECT COUNT(*) FROM invoices WHERE total<COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0)",
        ),
        (
            "No bank transaction overallocated",
            "SELECT COUNT(*) FROM bank WHERE amount<COALESCE((SELECT SUM(amount) FROM allocations WHERE bank_id=bank.id),0)",
        ),
        (
            "Discount usage matches committed applications",
            "SELECT COUNT(*) FROM discount_rules d WHERE used<>(SELECT COUNT(*) FROM discount_applications WHERE discount_id=d.id)",
        ),
        (
            "No discount exceeds its usage limit",
            "SELECT COUNT(*) FROM discount_rules WHERE used>limit_uses",
        ),
        (
            "Invoice totals match expected snapshots",
            "SELECT COUNT(*) FROM invoices WHERE total<>expected",
        ),
    ]
    out = [
        {
            "name": n,
            "passed": (nerr := c.execute(sql).fetchone()[0]) == 0,
            "failures": nerr,
        }
        for n, sql in tests
    ]
    line_errors = 0
    for i in rows(
        c,
        "SELECT subtotal,discount,tax,total,lines FROM invoices WHERE lines IS NOT NULL",
    ):
        ls = json.loads(i["lines"])
        if any(
            sum(line[k] for line in ls) != i[k]
            for k in ["subtotal", "discount", "tax", "total"]
        ):
            line_errors += 1
    out.append(
        {
            "name": "Invoice line sums match stored totals",
            "passed": line_errors == 0,
            "failures": line_errors,
        }
    )
    last = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if last:
        n = c.execute(
            "SELECT COUNT(*) FROM run_items WHERE run_id=? AND invoice_id IS NULL AND COALESCE(reason,'')=''",
            (last["id"],),
        ).fetchone()[0]
        out.append(
            {
                "name": "Latest run: every considered item has an invoice or skip reason",
                "passed": n == 0,
                "failures": n,
            }
        )
    return out
