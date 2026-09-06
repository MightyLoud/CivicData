"""Current-phase control: publication execution receipt must not be present yet."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TexasReleaseExecutionBoundaryTests(unittest.TestCase):
    def test_execution_authorization_receipt_is_not_created_in_release_authorization_phase(self):
        path = ROOT / "data/packages/tx/legislative/publication-execution-authorization-v0.1.json"
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
