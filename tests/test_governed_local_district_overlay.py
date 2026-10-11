from __future__ import annotations

from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from civic_gps_extensions.governed_local_district import (
    GovernedLocalDistrictError,
    apply_governed_local_district_overlays,
    validate_governed_local_district_overlays,
)
from civic_gps_extensions.loader import (
    CivicGPSBoundaryOverlayResolver,
    _load_extension,
)
from civic_gps_extensions.scoped_geocode import scoped_engine_class

EXTENSION = ROOT / "civic_gps_extensions/registry_bundles.v0.1.json"


def base_result(jurisdiction_id: str):
    return {
        "payload": {
            "input": {"matched_address": "fixture"},
            "jurisdictions": [{"jurisdiction_id": jurisdiction_id}],
            "matched_divisions": [],
            "district_assignments": [],
            "evidence": [],
            "coverage": [],
            "known_gaps": [],
            "applicable_offices": [{"office_id": "poison-office"}],
            "officeholders": [{"person_id": "poison-person"}],
            "action_links": [{"label": "poison-action"}],
        },
        "meta": {},
    }


class GovernedLocalDistrictOverlayTests(unittest.TestCase):
    def setUp(self):
        self.extension = _load_extension(EXTENSION)
        self.overlays = self.extension["governed_local_district_overlays"]

    def test_extension_contract_contains_two_valid_overlays(self):
        validate_governed_local_district_overlays(self.overlays)
        self.assertEqual(
            {row["adapter_id"] for row in self.overlays},
            {"DIST-CO-ALAMOSA-WARD", "DIST-CO-ARVADA-COUNCIL"},
        )

    def test_alamosa_point_resolves_from_governed_snapshot(self):
        result = apply_governed_local_district_overlays(
            base_result("jur-us-co-alamosa"),
            {
                "longitude": -105.870897502578,
                "latitude": 37.479843286555,
            },
            self.overlays,
            repo_root=ROOT,
            observed_on="2026-10-11",
        )
        payload = result["payload"]
        self.assertIn(
            {
                "adapter_id": "DIST-CO-ALAMOSA-WARD",
                "district_key": "1",
            },
            payload["district_assignments"],
        )
        self.assertTrue(
            any(
                row["division_id"] == "div-us-co-alamosa-ward-1"
                for row in payload["matched_divisions"]
            )
        )
        # Geography-only overlays never alter civic-fact collections.
        self.assertEqual(
            payload["applicable_offices"],
            [{"office_id": "poison-office"}],
        )
        self.assertEqual(
            payload["officeholders"],
            [{"person_id": "poison-person"}],
        )
        self.assertEqual(
            payload["action_links"],
            [{"label": "poison-action"}],
        )

    def test_arvada_point_resolves_from_governed_snapshot(self):
        result = apply_governed_local_district_overlays(
            base_result("jur-us-co-arvada"),
            {
                "longitude": -105.18539000544,
                "latitude": 39.816501932133,
            },
            self.overlays,
            repo_root=ROOT,
            observed_on=None,
        )
        self.assertIn(
            {
                "adapter_id": "DIST-CO-ARVADA-COUNCIL",
                "district_key": "4",
            },
            result["payload"]["district_assignments"],
        )

    def test_inactive_parent_does_not_apply_overlay(self):
        original = base_result("jur-us-co-akron")
        result = apply_governed_local_district_overlays(
            original,
            {"longitude": -105.870897502578, "latitude": 37.479843286555},
            self.overlays,
            repo_root=ROOT,
            observed_on=None,
        )
        self.assertEqual(result["payload"]["district_assignments"], [])

    def test_outside_active_parent_geometry_fails_closed(self):
        with self.assertRaisesRegex(
            GovernedLocalDistrictError,
            "LOCAL_DISTRICT_NOT_RESOLVED",
        ):
            apply_governed_local_district_overlays(
                base_result("jur-us-co-alamosa"),
                {"longitude": -100.0, "latitude": 40.0},
                self.overlays,
                repo_root=ROOT,
                observed_on=None,
            )

    def test_unresolved_registry_source_fails_closed(self):
        overlay = copy.deepcopy(self.overlays[0])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = {
                "registry_version": "0.1",
                "reviewed_at": "2026-10-11T00:00:00Z",
                "entries": [
                    {
                        "jurisdiction_id": "jurisdiction-co-alamosa",
                        "jurisdiction_ocdid": "ocd-jurisdiction/country:us/state:co/place:alamosa/government",
                        "expected_division_ids": list(overlay["districts"]),
                        "authority_sources": [
                            {
                                "kind": "OFFICIAL_MAP",
                                "url": "https://example.invalid/map",
                                "authority": "PRIMARY_OFFICIAL",
                                "notes": "test",
                            }
                        ],
                        "machine_source_status": "UNRESOLVED_ENDPOINT",
                        "machine_source_url": None,
                        "governed_snapshot_path": None,
                        "blocker_code": "TEST_UNRESOLVED",
                        "blocker_detail": "test",
                    }
                ],
            }
            (root / "registry.json").write_text(
                json.dumps(registry),
                encoding="utf-8",
            )
            overlay["source_registry_path"] = "registry.json"
            with self.assertRaisesRegex(
                GovernedLocalDistrictError,
                "LOCAL_DISTRICT_GEOMETRY_SOURCE_NOT_READY",
            ):
                apply_governed_local_district_overlays(
                    base_result("jur-us-co-alamosa"),
                    {
                        "longitude": -105.870897502578,
                        "latitude": 37.479843286555,
                    },
                    [overlay],
                    repo_root=root,
                    observed_on=None,
                )

    def test_scoped_wrapper_reuses_one_underlying_geocode(self):
        alamosa = [
            row
            for row in self.overlays
            if row["adapter_id"] == "DIST-CO-ALAMOSA-WARD"
        ]

        class FakeBase:
            def __init__(self):
                self.underlying_geocode_calls = 0

            def _geocode(self, address):
                self.underlying_geocode_calls += 1
                return {
                    "longitude": -105.870897502578,
                    "latitude": 37.479843286555,
                }

            def resolve(self, address, *, observed_on=None):
                self._geocode(address)
                return base_result("jur-us-co-alamosa")

        Scoped = scoped_engine_class(FakeBase, ValueError)
        engine = Scoped()
        resolver = CivicGPSBoundaryOverlayResolver(
            engine,
            [],
            [],
            alamosa,
            repo_root=ROOT,
        )
        result = resolver.resolve("500 Cottonwood Dr")
        self.assertNotIn("error", result)
        self.assertEqual(engine.underlying_geocode_calls, 1)
        self.assertIn(
            {
                "adapter_id": "DIST-CO-ALAMOSA-WARD",
                "district_key": "1",
            },
            result["payload"]["district_assignments"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
