"""Paths and environment loading. Importing modules never reads credentials."""

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def read_env():
    path = BASE / ".env"
    if not path.exists():
        return {}
    settings = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        settings[key.strip()] = value.strip().strip('"').strip("'")
    return settings


def load_config():
    for key, value in read_env().items():
        if key.startswith(("SMTP_", "RENEWSURE_")):
            os.environ.setdefault(key, value)


def email_configured():
    return all(
        os.environ.get(k)
        for k in ["SMTP_HOST", "SMTP_FROM", "SMTP_USER", "SMTP_PASSWORD"]
    )


def email_mode():
    return "Gmail SMTP" if email_configured() else "Email setup required"
