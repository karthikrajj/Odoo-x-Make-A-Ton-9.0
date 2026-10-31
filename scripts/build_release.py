"""Build an explicit, dependency-free source release; never package local data or secrets."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = [
    "server.py",
    "setup_gmail.py",
    "setup_gmail_gui.py",
    "fresh_demo.py",
    "Start-RenewSure.cmd",
    "start-renewsure.ps1",
    "Setup-Gmail.cmd",
    ".env.example",
    "README.md",
    "CLEANUP.md",
    "DEMO.md",
    "EMAIL_SETUP.md",
    "DESIGN.md",
    "UX-CONTRACT.md",
    "ACCEPTANCE.md",
    "TRACEABILITY.md",
    "sample-bank.csv",
]


def main():
    paths = [ROOT / name for name in ROOT_FILES]
    paths.extend(
        p
        for p in (ROOT / "renewsure").rglob("*")
        if p.is_file() and p.suffix in [".py", ".sql"]
    )
    paths.extend(
        p
        for p in (ROOT / "static").rglob("*")
        if p.is_file() and p.suffix in [".js", ".css", ".html"]
    )
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(p)
        if p.suffix == ".py":
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / "renewsure-release.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as release:
        for p in sorted(paths):
            release.write(p, p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as release:
        names = release.namelist()
        if any(
            Path(n).name == ".env" or Path(n).suffix in [".db", ".log", ".pyc"]
            for n in names
        ):
            raise ValueError("Private runtime data included in release")
        if release.testzip() is not None:
            raise ValueError("Corrupt release archive")
        with tempfile.TemporaryDirectory(prefix="renewsure-release-") as folder:
            release.extractall(folder)
            environment = os.environ.copy()
            environment["RENEWSURE_DB"] = str(Path(folder) / "smoke.db")
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import server; server.initialize(); print('Extracted release bootstrap passed')",
                ],
                cwd=folder,
                env=environment,
                check=True,
            )
    report = {
        "archive": str(archive.relative_to(ROOT)),
        "files": len(paths),
        "size_bytes": archive.stat().st_size,
        "secrets_and_live_data_excluded": True,
        "extracted_bootstrap_passed": True,
        "runtime_dependencies": "Python standard library; Node is needed only for development checks",
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "build.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
