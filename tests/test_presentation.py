"""Regression coverage for corrupted user-facing UTF-8 text."""

import unittest
from pathlib import Path


class PresentationTests(unittest.TestCase):
    def test_frontend_has_no_double_encoded_punctuation(self):
        source = (
            Path(__file__).resolve().parent.parent / "static" / "app.js"
        ).read_text(encoding="utf-8")
        for marker in ("\u00c2\u00b7", "\u00e2\u20ac", "\u00e2\u201a"):
            self.assertNotIn(marker, source)
        self.assertIn("\u20b9", source)
