"""Architecture and setup regression checks for the cleanup pass."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from renewsure import config, email_settings


class CleanupTests(unittest.TestCase):
    def test_importing_server_does_not_load_local_credentials(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("SMTP_")
        }
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; import server; assert 'SMTP_PASSWORD' not in os.environ",
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_setup_defaults_come_from_configuration(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                email_settings,
                "read_env",
                return_value={
                    "SMTP_FROM": "configured@example.test",
                    "RENEWSURE_BASE_URL": "http://localhost:8766",
                },
            ),
        ):
            self.assertEqual(
                email_settings.defaults(),
                ("configured@example.test", "http://localhost:8766"),
            )

    def test_setup_shares_tls_validation_and_atomic_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".env").write_text("RENEWSURE_NOTE=preserved\n", encoding="utf-8")
            with (
                patch.object(email_settings, "BASE", root),
                patch.object(config, "BASE", root),
                patch("renewsure.email_settings.smtplib.SMTP") as smtp,
            ):
                email_settings.save_connection(
                    "sender@example.test", "abcdefghijklmnop", "http://localhost:8766"
                )
                connection = smtp.return_value.__enter__.return_value
                connection.starttls.assert_called_once()
                connection.login.assert_called_once_with(
                    "sender@example.test", "abcdefghijklmnop"
                )
                values = config.read_env()
                self.assertEqual(values["SMTP_FROM"], "sender@example.test")
                self.assertEqual(values["RENEWSURE_NOTE"], "preserved")
                self.assertEqual(list(root.glob(".env.*.tmp")), [])

    def test_setup_rejects_header_injection_before_network_access(self):
        with patch("renewsure.email_settings.smtplib.SMTP") as smtp:
            with self.assertRaises(ValueError):
                email_settings.save_connection(
                    "sender@example.test\nBcc:other@example.test", "abcdefghijklmnop"
                )
            smtp.assert_not_called()

    def test_setup_failure_preserves_existing_configuration(self):
        import smtplib

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            existing = "RENEWSURE_NOTE=preserved\n"
            (root / ".env").write_text(existing, encoding="utf-8")
            with (
                patch.object(email_settings, "BASE", root),
                patch.object(config, "BASE", root),
                patch(
                    "renewsure.email_settings.smtplib.SMTP",
                    side_effect=smtplib.SMTPAuthenticationError(535, b"denied"),
                ),
            ):
                with self.assertRaises(ValueError):
                    email_settings.save_connection(
                        "sender@example.test", "abcdefghijklmnop"
                    )
                self.assertEqual((root / ".env").read_text(encoding="utf-8"), existing)


if __name__ == "__main__":
    unittest.main()
