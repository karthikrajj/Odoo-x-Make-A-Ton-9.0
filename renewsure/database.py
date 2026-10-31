"""SQLite connection ownership and the original base schema."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import BASE
from .errors import Error

DB = os.environ.get("RENEWSURE_DB", str(BASE / "renewsure.db"))


@contextmanager
def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        with c:
            yield c
    finally:
        c.close()


BASE_SCHEMA = Path(__file__).with_name("base.sql").read_text(encoding="utf-8")
BASE_INDEXES = Path(__file__).with_name("indexes.sql").read_text(encoding="utf-8")


def init():
    with conn() as c:
        c.executescript(BASE_SCHEMA)
        if c.execute("SELECT count(*) FROM users").fetchone()[0]:
            return
        from .seed import populate_demo

        populate_demo(c)
        c.executescript(BASE_INDEXES)


def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args)]


def one(c, sql, args=()):
    r = c.execute(sql, args).fetchone()
    if r is None:
        raise Error("Record not found")
    return dict(r)
