"""Shared Gmail setup; callers keep credentials out of terminal output and chat."""

import os
import smtplib
import ssl
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from .config import BASE, read_env


def defaults():
    settings = read_env()
    return (
        os.environ.get("SMTP_FROM") or settings.get("SMTP_FROM", ""),
        os.environ.get("RENEWSURE_BASE_URL")
        or settings.get("RENEWSURE_BASE_URL", "http://127.0.0.1:8766"),
    )


def save_connection(sender, secret, base_url=None):
    if "@" not in sender or any(c in sender for c in "\r\n"):
        raise ValueError("Enter your Gmail address.")
    secret = secret.replace(" ", "").strip()
    if len(secret) != 16 or not secret.isalpha():
        raise ValueError(
            "Paste the 16-character app password Google generated, not your normal Gmail password."
        )
    settings = read_env()
    base_url = base_url or settings.get("RENEWSURE_BASE_URL", "http://127.0.0.1:8766")
    parsed = urlparse(base_url)
    if (
        parsed.scheme not in ["http", "https"]
        or not parsed.netloc
        or any(c in base_url for c in "\r\n")
    ):
        raise ValueError("Enter a valid application URL.")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(sender, secret)
    except smtplib.SMTPAuthenticationError:
        raise ValueError(
            "Google rejected that app password. Generate a new one and try again."
        ) from None
    except (OSError, smtplib.SMTPException):
        raise ValueError(
            "Could not connect to Gmail. Check your internet connection and try again."
        ) from None
    settings.update(
        SMTP_HOST="smtp.gmail.com",
        SMTP_PORT="587",
        SMTP_SECURITY="starttls",
        SMTP_USER=sender,
        SMTP_PASSWORD=secret,
        SMTP_FROM=sender,
        RENEWSURE_BASE_URL=base_url.rstrip("/"),
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=BASE,
            prefix=".env.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write("\n".join(k + "=" + v for k, v in settings.items()) + "\n")
        os.replace(temporary, BASE / ".env")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
