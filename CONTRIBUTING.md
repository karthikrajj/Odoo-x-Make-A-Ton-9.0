# Contributing

Use Python 3.12 and Node 24. No application package installation is needed.

1. Create a branch for your change.
2. Run `python server.py` and open http://127.0.0.1:8766.
3. Keep `.env`, customer databases, logs and recovery backups private.
4. Preserve integer-paise calculations, invoice snapshots, role checks and idempotent billing. Add regression coverage for changes to these areas.
5. Run `python verify_all.py`, `python scripts/check_repository.py` and `python scripts/build_release.py` before opening a pull request. Run the lint/format commands in README.md.
6. Describe the problem, resulting behavior and checks performed. Use your own GitHub-linked commit email; credit actual shared work with co-author trailers.

Tests use disposable databases and suppress test recipients. The complete suite includes measured performance checks; investigate slow results instead of disabling assertions. See ACCEPTANCE.md for requirement coverage and billing policies in README.md.
