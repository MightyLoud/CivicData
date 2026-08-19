from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_two_jurisdiction_factory_proof(self) -> None:
        data = json.loads((ROOT / "registry" / "jurisdictions.json").read_text(encoding="utf-8"))
        records = {row["slug"]: row for row in data["jurisdictions"]}
        self.assertEqual(set(records), {"seattle-wa", "tacoma-wa"})
        self.assertTrue(all(row["parity_ok"] for row in records.values()))
        self.assertTrue(all(row["consumer_test"] == "PASS" for row in records.values()))
        self.assertEqual(records["tacoma-wa"]["modeled_office_count"], 16)
        self.assertEqual(records["tacoma-wa"]["public_elected_office_count"], 15)
        self.assertEqual(records["tacoma-wa"]["current_role_term_count"], 16)

    def test_contract_assets_exist(self) -> None:
        required = [
            ROOT / "schema" / "civic_reality_package_v0_1.schema.json",
            ROOT / "scripts" / "validate_release.py",
            ROOT / "scripts" / "run_consumer_test.py",
            ROOT / "partner-acceptance" / "ACCEPTANCE_PROTOCOL.md",
        ]
        self.assertTrue(all(path.exists() for path in required))


if __name__ == "__main__":
    unittest.main()
