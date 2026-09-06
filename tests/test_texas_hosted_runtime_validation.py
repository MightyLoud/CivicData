"""Offline controls for hosted Texas production URL validation."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.texas_hosted_runtime_validation import HostedValidationError, validate_public_https


class TexasHostedRuntimeValidationTests(unittest.TestCase):
    def test_requires_https_public_host(self):
        for value in (
            "http://example.com",
            "https://localhost:8080",
            "https://127.0.0.1:8080",
            "https://10.0.0.1",
        ):
            with self.subTest(value=value), self.assertRaises(HostedValidationError):
                validate_public_https(value)

    def test_accepts_public_https_hostname_shape(self):
        validate_public_https("https://civicdata.example.org")


if __name__ == "__main__":
    unittest.main(verbosity=2)
