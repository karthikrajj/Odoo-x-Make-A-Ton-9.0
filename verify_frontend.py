"""Use a disposable database to verify the real JavaScript form handlers against HTTP."""

import os
import subprocess
import tempfile
import threading
from pathlib import Path

import server
from renewsure import database as db


def main():
    Path("reports").mkdir(exist_ok=True)
    old = db.DB
    with tempfile.TemporaryDirectory() as directory:
        db.DB = os.path.join(directory, "frontend.db")
        server.initialize()
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "tests/test_ui_flow.cjs",
                    f"http://127.0.0.1:{httpd.server_port}",
                ],
                check=False,
            )
            if result.returncode:
                raise SystemExit(result.returncode)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()
            db.DB = old


if __name__ == "__main__":
    main()
