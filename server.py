"""Stable launcher for the local RenewSure application."""

from http.server import ThreadingHTTPServer

from renewsure.documents import pdf_invoice
from renewsure.http import Handler, initialize, main, scheduler_tick

__all__ = [
    "Handler",
    "ThreadingHTTPServer",
    "initialize",
    "scheduler_tick",
    "pdf_invoice",
]

if __name__ == "__main__":
    main()
