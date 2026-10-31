"""Local RenewSure application. Start: python server.py (loopback only)."""

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import database as db
from . import delivery, schema, security, services
from . import domain as d
from .config import BASE, email_mode, load_config
from .documents import pdf_invoice

ATTEMPTS = {}
LOCK = threading.Lock()
REPORT_LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def reply(
        self,
        data,
        status=200,
        mime="application/json; charset=utf-8",
        cookie=None,
        headers=None,
    ):
        body = (
            json.dumps(data).encode() if mime.startswith("application/json") else data
        )
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            v = None
            host = self.headers.get("Host", "")
            if host not in [
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            ]:
                return self.reply({"error": "Local host required"}, 403)
            if self.command == "POST":
                origin = self.headers.get("Origin")
                if origin and origin not in [
                    f"http://127.0.0.1:{self.server.server_port}",
                    f"http://localhost:{self.server.server_port}",
                ]:
                    return self.reply({"error": "Cross-origin request rejected"}, 403)
                if (
                    self.headers.get("Content-Type", "").split(";")[0]
                    != "application/json"
                ):
                    return self.reply({"error": "JSON required"}, 415)
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 2000000:
                    return self.reply({"error": "Maximum upload is 2 MB"}, 413)
                v = json.loads(self.rfile.read(length))
                if not isinstance(v, dict):
                    raise d.Error("Expected a JSON object")
            if not path.startswith("/api/"):
                if self.command != "GET":
                    return self.reply({"error": "Method not allowed"}, 405)
                file = (
                    BASE
                    / "static"
                    / ("index.html" if path == "/" else path.lstrip("/"))
                )
                if (
                    not file.resolve().is_relative_to((BASE / "static").resolve())
                    or not file.is_file()
                ):
                    return self.reply({"error": "Not found"}, 404)
                return self.reply(
                    file.read_bytes(),
                    mime={
                        ".html": "text/html; charset=utf-8",
                        ".js": "text/javascript; charset=utf-8",
                        ".css": "text/css; charset=utf-8",
                    }.get(file.suffix, "text/plain"),
                )
            path = path[5:]
            cookie = None
            only_post = {
                "login",
                "signup",
                "forgot",
                "reset",
                "logout",
                "transition",
                "clock",
                "bill",
                "import",
                "allocate",
                "payment",
            }
            if path in only_post and v is None:
                return self.reply({"error": "Use POST for this action"}, 405)
            with db.conn() as c:
                if v is not None:
                    c.execute("BEGIN IMMEDIATE")
                if path in ["login", "signup", "forgot", "reset"]:
                    key = (self.client_address[0], path)
                    with LOCK:
                        recent = [
                            x for x in ATTEMPTS.get(key, []) if x > time.time() - 60
                        ]
                        if len(recent) >= 30:
                            return self.reply(
                                {"error": "Too many attempts. Try again in a minute."},
                                429,
                            )
                        ATTEMPTS[key] = recent + [time.time()]
                    if path == "signup":
                        d.new_user(c, v)
                        result = {"message": "Account created. You can sign in."}
                    elif path == "forgot":
                        e = d.email(v.get("email"))
                        u = c.execute(
                            "SELECT id FROM users WHERE email=?", (e,)
                        ).fetchone()
                        if u:
                            token = secrets.token_urlsafe(32)
                            hashed = hashlib.sha256(token.encode()).hexdigest()
                            c.execute(
                                "UPDATE resets SET used=1 WHERE user_id=?", (u["id"],)
                            )
                            c.execute(
                                "INSERT INTO resets VALUES(?,?,?,0)",
                                (hashed, u["id"], time.time() + 1800),
                            )
                            d.mail(
                                c,
                                e,
                                "Reset your RenewSure password",
                                f"Open {os.environ.get('RENEWSURE_BASE_URL', 'http://' + host).rstrip('/')}/?reset={token}\nThis single-use link expires in 30 minutes.",
                                "reset",
                            )
                        result = {
                            "message": "If the account exists, a reset link has been queued for its registered email. Delivery: "
                            + email_mode()
                        }
                    elif path == "reset":
                        hashed = hashlib.sha256(
                            str(v.get("token", "")).encode()
                        ).hexdigest()
                        r = c.execute(
                            "SELECT * FROM resets WHERE token=? AND used=0 AND expires>?",
                            (hashed, time.time()),
                        ).fetchone()
                        if not r:
                            raise d.Error(
                                "Reset link is invalid, expired or already used"
                            )
                        if not security.valid(v.get("password", "")):
                            raise d.Error(
                                "Password must exceed 8 characters and include uppercase, lowercase and a special character"
                            )
                        salt = secrets.token_hex(16)
                        c.execute(
                            "UPDATE users SET salt=?,hash=? WHERE id=?",
                            (
                                salt,
                                security.password(v["password"], salt),
                                r["user_id"],
                            ),
                        )
                        c.execute("UPDATE resets SET used=1 WHERE token=?", (hashed,))
                        c.execute(
                            "DELETE FROM sessions WHERE user_id=?", (r["user_id"],)
                        )
                        result = {
                            "message": "Password updated. Sign in with your new password."
                        }
                    else:
                        u = c.execute(
                            "SELECT * FROM users WHERE email=?",
                            (str(v.get("email", "")).lower().strip(),),
                        ).fetchone()
                        if not u or not secrets.compare_digest(
                            u["hash"],
                            security.password(v.get("password", ""), u["salt"]),
                        ):
                            raise PermissionError("Email or password is incorrect")
                        token = secrets.token_hex(32)
                        c.execute(
                            "INSERT INTO sessions VALUES(?,?,?)",
                            (token, u["id"], time.time() + 28800),
                        )
                        cookie = f"session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"
                        result = {}
                elif path == "demo-mail":
                    return self.reply({"error": "Local mailbox has been removed"}, 404)
                else:
                    token = next(
                        (
                            s.strip().split("=", 1)[1]
                            for s in self.headers.get("Cookie", "").split(";")
                            if s.strip().startswith("session=")
                        ),
                        "",
                    )
                    u = c.execute(
                        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?",
                        (token, time.time()),
                    ).fetchone()
                    if not u:
                        return self.reply({"error": "Please sign in again"}, 401)
                    u = dict(u)
                    if path == "logout":
                        c.execute("DELETE FROM sessions WHERE token=?", (token,))
                        cookie = (
                            "session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
                        )
                        result = {}
                    elif path == "invoice.pdf":
                        i = d.invoice(c, d.integer(q["id"], 1), u)
                        return self.reply(
                            pdf_invoice(i),
                            mime="application/pdf",
                            headers={
                                "Content-Disposition": f'inline; filename="INV-{i["id"]}.pdf"'
                            },
                        )
                    else:
                        started = time.perf_counter()
                        if (
                            path in ["dashboard", "reconcile", "preview", "recovery"]
                            and v is None
                        ):
                            # Bound heavy SQLite report work to avoid GIL/row-conversion contention.
                            with REPORT_LOCK:
                                c.execute("BEGIN")
                                result = services.handle(c, path, v, u, q)
                        else:
                            result = services.handle(c, path, v, u, q)
                        if isinstance(result, dict):
                            result["server_ms"] = round(
                                (time.perf_counter() - started) * 1000, 2
                            )
            self.reply(result, cookie=cookie)
        except PermissionError as e:
            self.reply({"error": str(e)}, 403)
        except (ValueError, KeyError, TypeError, db.sqlite3.IntegrityError) as e:
            self.reply({"error": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            LOGGER.exception("Unexpected request failure")
            self.reply({"error": "Unexpected server error. Check the server log."}, 500)


def scheduler_tick():
    with db.conn() as c:
        c.execute("BEGIN IMMEDIATE")
        enabled = c.execute(
            "SELECT 1 FROM settings WHERE key='auto_billing' AND value='1'"
        ).fetchone()
        if enabled and all(x["passed"] for x in d.checks(c)):
            p = d.rehearsal(c)
            if p["count"] or p["expired"]:
                d.billing(c)
        d.close_expired(c)
        d.chase(c)
    delivery.deliver_pending()


def worker(stop):
    while not stop.is_set():
        try:
            scheduler_tick()
        except Exception:
            LOGGER.exception("Scheduled job failed")
        stop.wait(30)


def initialize():
    db.init()
    with db.conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
    schema.migrate()


def main():
    load_config()
    initialize()
    port = int(os.environ.get("PORT", "8766"))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    stop = threading.Event()
    threading.Thread(target=worker, args=(stop,), daemon=True).start()
    (BASE / "server.pid").write_text(str(os.getpid()))
    print(f"RenewSure: http://127.0.0.1:{port}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        stop.set()
        httpd.server_close()
