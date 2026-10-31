"""Check imports, package cycles, source compilation and accidental secret inclusion."""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = {".git", "backups", "__pycache__", ".ruff_cache", "dist", "reports"}


def source_files():
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not any(part in EXCLUDED for part in p.relative_to(ROOT).parts)
        and p.suffix
        in {".py", ".js", ".cjs", ".mjs", ".html", ".css", ".md", ".toml", ".json"}
    ]


def check():
    failures = []
    graph = {p.stem: set() for p in (ROOT / "renewsure").glob("*.py")}
    files = source_files()
    for path in [p for p in files if p.suffix == ".py"]:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        compile(tree, str(path), "exec")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    if item.name == "legacy":
                        failures.append(
                            {
                                "file": str(path.relative_to(ROOT)),
                                "line": node.lineno,
                                "issue": "obsolete legacy import",
                            }
                        )
            if (
                path.parent.name == "renewsure"
                and isinstance(node, ast.ImportFrom)
                and node.level == 1
            ):
                dependencies = (
                    [node.module.split(".")[0]]
                    if node.module
                    else [item.name for item in node.names]
                )
                for dep in dependencies:
                    if dep not in graph:
                        failures.append(
                            {
                                "file": str(path.relative_to(ROOT)),
                                "line": node.lineno,
                                "issue": "missing package import " + dep,
                            }
                        )
                    else:
                        graph[path.stem].add(dep)
    visited = set()
    active = set()

    def visit(name):
        if name in active:
            raise ValueError("Circular package import at " + name)
        if name in visited:
            return
        active.add(name)
        for dep in graph[name]:
            visit(dep)
        active.remove(name)
        visited.add(name)

    for name in graph:
        visit(name)
    # Scan only source. Never include credential values in reports or terminal output.
    patterns = [
        re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
        re.compile(r"sk-[0-9A-Za-z_-]{24,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ]
    env = ROOT / ".env"
    private_values = []
    if env.exists():
        for raw in env.read_text(encoding="utf-8-sig").splitlines():
            if raw.startswith("SMTP_PASSWORD="):
                value = raw.split("=", 1)[1].strip()
                if len(value) >= 8:
                    private_values.append(value)
    for path in files:
        body = path.read_text(encoding="utf-8-sig")
        for line_number, line in enumerate(body.splitlines(), 1):
            if any(pattern.search(line) for pattern in patterns) or any(
                value in line for value in private_values
            ):
                failures.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "line": line_number,
                        "issue": "possible secret [REDACTED]",
                    }
                )
    tracked = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True
    ).splitlines()
    if ".env" in tracked:
        failures.append({"file": ".env", "issue": "credentials file is tracked"})
    report = {
        "source_files_checked": len(files),
        "package_modules_checked": len(graph),
        "circular_imports": False,
        "failures": failures,
        "manual_review": [
            "Seeded demo accounts and frontend demo sign-in defaults must be reviewed before public deployment.",
            "The standard-library HTTP server is intentionally loopback-only and is not a hardened public hosting stack.",
            "Keep .env private; use deployment secret management if hosting publicly.",
            "Browser/mobile visual verification remains separate from handler tests.",
        ],
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "repository-check.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(check())
