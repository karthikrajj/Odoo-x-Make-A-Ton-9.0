"""Claim and deliver queued SMTP messages without silently retrying ambiguous sends."""

import hashlib
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage

from . import database as db
from . import domain as d
from .config import email_configured


def deliver_pending(transport=None):
    if not email_configured():
        return 0
    sender = os.environ.get("SMTP_FROM")
    if not sender:
        raise ValueError("Set SMTP_FROM before enabling email delivery")
    with db.conn() as c:
        batch = d.rows(
            c,
            "SELECT * FROM outbox WHERE status IN ('Waiting for email setup','Queued') ORDER BY id LIMIT 50",
        )
    delivered = 0
    for item in batch:
        # Claim before connecting. Ambiguous outcomes are never silently retried.
        with db.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if item["kind"] == "reset":
                match = re.search(r"reset=([^\s]+)", item["body"])
                hashed = (
                    hashlib.sha256(match.group(1).encode()).hexdigest() if match else ""
                )
                if not c.execute(
                    "SELECT 1 FROM resets WHERE token=? AND used=0 AND expires>?",
                    (hashed, time.time()),
                ).fetchone():
                    c.execute(
                        "UPDATE outbox SET status='Expired reset link' WHERE id=?",
                        (item["id"],),
                    )
                    continue
            claimed = c.execute(
                "UPDATE outbox SET status='Sending' WHERE id=? AND status IN ('Waiting for email setup','Queued')",
                (item["id"],),
            ).rowcount
        if not claimed:
            continue
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = item["recipient"]
        msg["Subject"] = item["subject"]
        msg["Message-ID"] = f"<renewsure-{item['id']}@local.renewsure>"
        msg.set_content(item["body"])
        try:
            if item.get("invoice_id"):
                from .documents import pdf_invoice

                with db.conn() as c:
                    attachment = pdf_invoice(d.invoice(c, item["invoice_id"]))
                msg.add_attachment(
                    attachment,
                    maintype="application",
                    subtype="pdf",
                    filename=f"INV-{item['invoice_id']}.pdf",
                )
            if transport:
                transport(msg)
            else:
                host = os.environ["SMTP_HOST"]
                port = int(os.environ.get("SMTP_PORT", "587"))
                security = os.environ.get("SMTP_SECURITY", "starttls")
                factory = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
                if security not in ["ssl", "starttls"]:
                    raise ValueError("SMTP_SECURITY must be ssl or starttls")
                with factory(
                    host,
                    port,
                    timeout=15,
                    **(
                        {"context": ssl.create_default_context()}
                        if security == "ssl"
                        else {}
                    ),
                ) as smtp:
                    if security == "starttls":
                        smtp.starttls(context=ssl.create_default_context())
                    if os.environ.get("SMTP_USER"):
                        smtp.login(
                            os.environ["SMTP_USER"],
                            os.environ.get("SMTP_PASSWORD", "").replace(" ", ""),
                        )
                    smtp.send_message(msg)
            status = "Sent"
            delivered += 1
        except Exception:
            status = "Delivery needs review"
        with db.conn() as c:
            c.execute("UPDATE outbox SET status=? WHERE id=?", (status, item["id"]))
    return delivered
