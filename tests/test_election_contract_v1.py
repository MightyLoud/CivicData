from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote import (
    contract_v1,
    contract_v1_full_essentials,
    contract_v1_full_essentials_catalog,
    contract_v1_catalog,
    package_catalog,
)

try:
    import jsonschema
except ImportError:
    jsonschema = None

MARKET = "747 Market Street, Tacoma, WA 98402"
AKRON = "250 Main Avenue, Akron, CO 80720"


def tacoma_gps(district: str = "2") -> dict:
    return {
        "payload": {
            "input": {"matched_address": MARKET.upper()},
            "jurisdictions": [
                {"jurisdiction_id": "jur-us-wa-pierce"},
                {"jurisdiction_id": "jur-us-wa-tacoma"},
            ],
            "district_assignments": [
                {"adapter_id": "DIST-WA-PIERCE-COUNCIL", "district_key": "4"},
                {"adapter_id": "DIST-WA-TACOMA-COUNCIL", "district_key": district},
            ],
            "applicable_offices": [{"office_id": "untrusted-upstream-office"}],
            "officeholders": [{"person_id": "untrusted-upstream-person"}],
            "action_links": [{"label": "untrusted"}],
        }
    }


def akron_gps() -> dict:
    return {
        "payload": {
            "input": {"matched_address": AKRON.upper()},
            "jurisdictions": [{"jurisdiction_id": "jur-us-co-akron"}],
            "district_assignments": [],
        }
    }


def governed_contract(profile: str, gps: dict) -> tuple[dict, dict, dict]:
    catalog = package_catalog.load_catalog()
    entry = package_catalog.select_entry(catalog, gps, profile=profile)
    package = package_catalog.reconstruct_package(entry, ROOT)
    contract = export_factory_package(
        package,
        generated_at=contract_v1_catalog._generated_at(package),
        governed_package=True,
    )
    return entry, package, contract


class ElectionContractV1Tests(unittest.TestCase):
    def test_tacoma_factory_projection_contains_complete_election_extension(self):
        _, _, contract = governed_contract("municipal_essentials", tacoma_gps())

        self.assertEqual(len(contract["elections"]), 2)
        self.assertEqual(len(contract["contests"]), 9)
        self.assertEqual(len(contract["candidacies"]), 26)
        self.assertEqual(contract["election_certification"]["status"], "certified")
        self.assertTrue(contract["election_certification"]["scope_complete"])
        self.assertEqual(contract["election_certification"]["unexplained_loss"], 0)

        named = [row for row in contract["candidacies"] if row["candidate_kind"] == "person"]
        writeins = [
            row for row in contract["candidacies"]
            if row["candidate_kind"] == "write_in_bucket"
        ]
        self.assertEqual(len(named), 17)
        self.assertEqual(len(writeins), 9)
        self.assertTrue(all(row["person_id"] for row in named))
        self.assertTrue(all(row["person_id"] is None for row in writeins))

        errors = contract_v1.validate_contract(
            contract,
            require_certified=True,
            require_elections=True,
        )
        self.assertEqual(errors, [])

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_tacoma_election_contract_validates_against_wire_schema(self):
        _, _, contract = governed_contract("municipal_essentials", tacoma_gps())
        schema = json.loads(
            (ROOT / "schemas/representation_contract_v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
        errors = sorted(
            validator.iter_errors(contract), key=lambda error: list(error.path)
        )
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_market_street_full_essentials_shadow_matches_legacy(self):
        model = contract_v1_full_essentials_catalog.build_full_essentials_from_catalog(
            MARKET,
            tacoma_gps("2"),
            repo_root=ROOT,
        )
        self.assertEqual(model["status"], "PASS", model)
        self.assertEqual(model["consumer_gate"], "EV-RC1-FULL-SHADOW")
        self.assertEqual(
            model["package_catalog_entry_id"],
            "wa-tacoma-municipal-essentials-v0.2",
        )
        self.assertEqual(len(model["applicable_offices"]), 6)
        self.assertEqual(len(model["recent_certified_contests"]), 5)
        self.assertEqual(
            sum(
                len(contest["candidates"])
                for contest in model["recent_certified_contests"]
            ),
            15,
        )
        self.assertEqual(model["election_certification"]["status"], "certified")
        self.assertEqual(model["canonical_writes"], 0)

        self.assertTrue(
            all(
                office["office_id"] != "untrusted-upstream-office"
                for office in model["applicable_offices"]
            )
        )

        parity = (
            contract_v1_full_essentials_catalog.compare_full_essentials_shadow_to_legacy(
                MARKET,
                tacoma_gps("2"),
                repo_root=ROOT,
            )
        )
        self.assertEqual(parity["status"], "PASS", parity)
        self.assertTrue(parity["parity_ok"], parity)
        self.assertEqual(parity["legacy_office_count"], 6)
        self.assertEqual(parity["contract_v1_office_count"], 6)
        self.assertEqual(parity["legacy_contest_count"], 5)
        self.assertEqual(parity["contract_v1_contest_count"], 5)
        self.assertEqual(parity["legacy_candidate_count"], 15)
        self.assertEqual(parity["contract_v1_candidate_count"], 15)
        self.assertEqual(parity["office_differences"], [])
        self.assertEqual(parity["contest_differences"], [])
        self.assertEqual(parity["canonical_writes"], 0)

    def test_election_certification_tampering_fails_closed(self):
        entry, package, contract = governed_contract(
            "municipal_essentials", tacoma_gps()
        )
        broken = copy.deepcopy(contract)
        broken["election_certification"]["scope_complete"] = False
        binding = contract_v1_catalog._contract_binding(
            entry, package, broken, tacoma_gps()
        )
        model = contract_v1_full_essentials.build_full_essentials_from_civic_gps_result(
            broken,
            MARKET,
            tacoma_gps(),
            binding=binding,
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "CONTRACT_ELECTION_EXTENSION_INVALID")
        self.assertIn("CONTRACT_ELECTION_SCOPE_INCOMPLETE", model["detail"])
        self.assertEqual(model["canonical_writes"], 0)

    def test_write_in_linked_to_person_fails_closed(self):
        entry, package, contract = governed_contract(
            "municipal_essentials", tacoma_gps()
        )
        broken = copy.deepcopy(contract)
        writein = next(
            row
            for row in broken["candidacies"]
            if row["candidate_kind"] == "write_in_bucket"
        )
        writein["person_id"] = broken["people"][0]["id"]
        binding = contract_v1_catalog._contract_binding(
            entry, package, broken, tacoma_gps()
        )
        model = contract_v1_full_essentials.build_full_essentials_from_civic_gps_result(
            broken,
            MARKET,
            tacoma_gps(),
            binding=binding,
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "CONTRACT_ELECTION_EXTENSION_INVALID")
        self.assertIn("CONTRACT_WRITE_IN_PERSON_FORBIDDEN", model["detail"])

    def test_named_candidate_without_person_fails_closed(self):
        entry, package, contract = governed_contract(
            "municipal_essentials", tacoma_gps()
        )
        broken = copy.deepcopy(contract)
        named = next(
            row for row in broken["candidacies"] if row["candidate_kind"] == "person"
        )
        named["person_id"] = None
        binding = contract_v1_catalog._contract_binding(
            entry, package, broken, tacoma_gps()
        )
        model = contract_v1_full_essentials.build_full_essentials_from_civic_gps_result(
            broken,
            MARKET,
            tacoma_gps(),
            binding=binding,
        )
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], "CONTRACT_ELECTION_EXTENSION_INVALID")
        self.assertIn("CONTRACT_CANDIDACY_PERSON_FK", model["detail"])

    def test_representation_only_akron_remains_valid_but_full_essentials_fails(self):
        entry, package, contract = governed_contract(
            "municipal_representation", akron_gps()
        )
        self.assertNotIn("elections", contract)
        self.assertEqual(
            contract_v1.validate_contract(
                contract,
                require_certified=True,
                require_elections=False,
            ),
            [],
        )
        binding = contract_v1_catalog._contract_binding(
            entry, package, contract, akron_gps()
        )
        representation = contract_v1.build_representation_from_civic_gps_result(
            contract,
            AKRON,
            akron_gps(),
            binding=binding,
        )
        self.assertEqual(representation["status"], "PASS", representation)

        full = contract_v1_full_essentials.build_full_essentials_from_civic_gps_result(
            contract,
            AKRON,
            akron_gps(),
            binding=binding,
        )
        self.assertEqual(full["status"], "FAIL-CLOSED")
        self.assertEqual(full["error"], "CONTRACT_ELECTION_EXTENSION_INVALID")
        self.assertIn("CONTRACT_ELECTION_EXTENSION_REQUIRED", full["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
