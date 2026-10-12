"""Regressions for address-policy ordering, failure envelopes and artifact parity."""
from __future__ import annotations

import csv
import fnmatch
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consumers.empowered_vote.address_runtime import build_representation_for_address
from tests.governed_district_controls import PACKAGE_PATHS, load_district_controls
from tools.geocoding_boundary import GeocodingBoundaryError, select_candidate
from tools.jurisdiction_package_strict import build, verify_package


def candidate(control, score=100, addr_type="PointAddress"):
    return {
        "address": control["address_input"], "score": score,
        "location": {"x": control["longitude"], "y": control["latitude"]},
        "attributes": {"Addr_type": addr_type},
    }


class Provider:
    provider_id = "HARDENING_FIXTURE"

    def __init__(self, rows):
        self.rows = rows

    def find_candidates(self, address, *, max_locations):
        return self.rows[:max_locations]


class CandidateOrderingTests(unittest.TestCase):
    def controls(self):
        return [row for _, _, row in load_district_controls(ROOT)][:2]

    def test_unequal_aliases_cannot_fabricate_margin_in_any_order(self):
        a, b = self.controls()
        for rows in itertools.permutations([candidate(a, 90), candidate(a), candidate(b, 98)]):
            with self.subTest(order=[row["score"] for row in rows]):
                with self.assertRaisesRegex(GeocodingBoundaryError, "AMBIGUOUS_ADDRESS"):
                    select_candidate(rows)

    def test_full_runtime_rejects_every_ambiguous_alias_permutation(self):
        a, b = self.controls()
        for rows in itertools.permutations([candidate(a, 90), candidate(a), candidate(b, 98)]):
            model = build_representation_for_address(
                "synthetic ambiguous address", geocoder=Provider(rows),
                generated_at="2026-10-12T03:00:00Z", root=ROOT,
            )
            self.assertEqual(model["status"], "FAIL-CLOSED", model)
            self.assertEqual(model["error"], "AMBIGUOUS_ADDRESS")
            self.assertNotIn("applicable_offices", model)
            self.assertEqual(model["canonical_writes"], 0)

    def test_strongest_alias_and_output_are_order_independent(self):
        a, b = self.controls()
        outputs = [select_candidate(rows) for rows in itertools.permutations(
            [candidate(a, 90), candidate(a), candidate(b, 85)]
        )]
        self.assertTrue(all(row == outputs[0] for row in outputs))
        self.assertEqual(outputs[0]["score"], 100)
        self.assertEqual(outputs[0]["score_margin"], 15)

    def test_equal_best_alias_type_conflicts_fail_in_every_order(self):
        a, _ = self.controls()
        for rows in itertools.permutations([candidate(a), candidate(a, addr_type="Postal")]):
            with self.assertRaisesRegex(GeocodingBoundaryError, "GEOCODER_ALIAS_TYPE_CONFLICT"):
                select_candidate(rows)

    def test_stronger_unsupported_type_is_not_replaced_by_weaker_alias(self):
        a, _ = self.controls()
        for rows in itertools.permutations([candidate(a, 99), candidate(a, addr_type="Postal")]):
            with self.assertRaisesRegex(GeocodingBoundaryError, "GEOCODER_ADDRESS_TYPE_NOT_ALLOWED"):
                select_candidate(rows)


class RuntimeFailureEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "data/reference/co", self.root / "data/reference/co")
        for relative in PACKAGE_PATHS:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.control = load_district_controls(self.root)[0][2]

    def resolve(self):
        return build_representation_for_address(
            self.control["address_input"], geocoder=Provider([candidate(self.control)]),
            generated_at="2026-10-12T03:00:00Z", root=self.root,
        )

    def assert_failed(self, code):
        model = self.resolve()
        self.assertEqual(model["status"], "FAIL-CLOSED", model)
        self.assertTrue(model["error"].startswith(code), model)
        self.assertEqual(model["canonical_writes"], 0)
        self.assertNotIn("applicable_offices", model)

    def test_supplied_root_controls_registry_and_snapshots(self):
        model = self.resolve()
        self.assertEqual(model["status"], "PASS", model)
        (self.root / "data/reference/co/district_geometry_sources_v0.1.json").unlink()
        self.assert_failed("GOVERNED_GEOMETRY_SOURCE_REGISTRY_INVALID")

    def test_malformed_registry_json_is_a_structured_failure(self):
        (self.root / "data/reference/co/district_geometry_sources_v0.1.json").write_text("{broken")
        self.assert_failed("GOVERNED_GEOMETRY_SOURCE_REGISTRY_INVALID")

    def test_registry_shape_error_is_a_structured_failure(self):
        (self.root / "data/reference/co/district_geometry_sources_v0.1.json").write_text("[]")
        self.assert_failed("SOURCE_REGISTRY_INVALID")

    def test_corrupt_snapshot_is_a_structured_failure(self):
        (self.root / "data/reference/co/geometry/alamosa_wards_2023_v0.1.json").write_text("{broken")
        self.assert_failed("GOVERNED_GEOMETRY_SNAPSHOT_INVALID")

    def test_missing_snapshot_is_a_structured_failure(self):
        (self.root / "data/reference/co/geometry/alamosa_wards_2023_v0.1.json").unlink()
        self.assert_failed("GOVERNED_GEOMETRY_SNAPSHOT_MISSING")

    def test_corrupt_package_is_a_structured_failure(self):
        (self.root / PACKAGE_PATHS[0]).write_text("{broken")
        self.assert_failed("GOVERNED_JURISDICTION_PACKAGE_INVALID")

    def test_invalid_package_shape_is_a_structured_failure(self):
        (self.root / PACKAGE_PATHS[0]).write_text("[]")
        self.assert_failed("GOVERNED_JURISDICTION_PACKAGE_INVALID")

    def test_duplicate_package_is_a_structured_failure(self):
        duplicate = self.root / "data/normalized/co/duplicate/jurisdiction.json"
        duplicate.parent.mkdir(parents=True)
        shutil.copyfile(self.root / PACKAGE_PATHS[0], duplicate)
        self.assert_failed("JURISDICTION_PACKAGE_DUPLICATE")

    def test_missing_package_is_a_structured_failure(self):
        (self.root / PACKAGE_PATHS[0]).unlink()
        self.assert_failed("GOVERNED_JURISDICTION_PACKAGE_MISSING")

    def test_package_export_error_is_a_structured_failure(self):
        path = self.root / PACKAGE_PATHS[0]
        package = json.loads(path.read_text())
        package["records"] = {}
        path.write_text(json.dumps(package))
        self.assert_failed("GOVERNED_JURISDICTION_PACKAGE_EXPORT_INVALID")


class PackageControlParityTests(unittest.TestCase):
    def test_current_packages_and_all_exports_reconcile(self):
        for relative in PACKAGE_PATHS:
            directory = (ROOT / relative).parent
            with self.subTest(package=relative):
                package = json.loads((directory / "jurisdiction.json").read_text())
                self.assertEqual(verify_package(directory), [])
                self.assertEqual(json.loads((directory / "qa_report.json").read_text()), package["qa"])
                with (directory / "address_tests.csv").open(newline="") as stream:
                    csv_rows = list(csv.DictReader(stream))
                expected = package["qa"]["address_tests"]
                self.assertEqual(len(expected), 6)
                self.assertEqual(len(csv_rows), 6)
                keys = sorted({key for row in expected for key in row})
                self.assertEqual(csv_rows, [
                    {key: "" if row.get(key) is None else str(row.get(key, "")) for key in keys}
                    for row in expected
                ])

    def test_export_rebuild_is_deterministic_and_preserves_package_values(self):
        for relative in PACKAGE_PATHS:
            original = json.loads((ROOT / relative).read_text())
            with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
                a, b = Path(one) / "package", Path(two) / "package"
                build(original, a)
                build(original, b)
                self.assertEqual(json.loads((a / "jurisdiction.json").read_text()), original)
                self.assertEqual({p.name: p.read_bytes() for p in a.iterdir()},
                                 {p.name: p.read_bytes() for p in b.iterdir()})

    def test_both_live_paths_share_exact_current_controls(self):
        from tests import civic_gps_governed_local_district_live_probe as gps
        from tests import governed_geocoding_live_probe as arcgis
        from tests import governed_address_live_smoke as smoke
        self.assertIs(gps.load_district_controls, load_district_controls)
        self.assertIs(arcgis.load_district_controls, load_district_controls)
        self.assertIs(smoke.main, arcgis.main)
        addresses = {row["address_input"] for _, _, row in load_district_controls(ROOT)}
        self.assertIn("2190 State Ave, Alamosa, CO 81101", addresses)
        self.assertIn("10664 W 58th Ave, Arvada, CO 80002", addresses)
        self.assertNotIn("1000 Twentieth St, Alamosa, CO 81101", addresses)


class LiveCIScopeTests(unittest.TestCase):
    DEPENDENCIES = (
        "tools/jurisdiction_package_strict.py",
        "data/normalized/co/jurisdiction-co-alamosa/address_tests.csv",
        "data/normalized/co/jurisdiction-co-arvada/SHA256SUMS.txt",
        "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
        "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
        "data/reference/co/geometry/alamosa_wards_2023_v0.1.json",
        "data/reference/co/district_geometry_sources_v0.1.json",
        "tools/geometry_governance.py",
        "tests/governed_district_controls.py",
        "tests/test_address_pipeline_hardening.py",
    )

    def test_civic_gps_pr_scope_executes_for_each_dependency(self):
        workflow = (ROOT / ".github/workflows/civic-gps-live-smoke.yml").read_text()
        pattern = re.search(r"grep -Eq '([^']+)'", workflow).group(1)
        for path in (*self.DEPENDENCIES, "tests/test_governed_local_district_overlay.py"):
            with self.subTest(path=path):
                self.assertEqual(subprocess.run(["grep", "-Eq", pattern], input=path,
                                               text=True, check=False).returncode, 0)
        self.assertEqual(subprocess.run(["grep", "-Eq", pattern], input="docs/unrelated.md",
                                       text=True, check=False).returncode, 1)

    def test_civic_gps_push_paths_cover_each_dependency(self):
        workflow = (ROOT / ".github/workflows/civic-gps-live-smoke.yml").read_text()
        paths_block = workflow.split("    paths:", 1)[1].split("  schedule:", 1)[0]
        patterns = re.findall(r"- '([^']+)'", paths_block)
        for path in self.DEPENDENCIES:
            self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), path)

    def test_arcgis_live_filters_cover_each_shared_dependency(self):
        for name in ("governed-address-live-smoke", "governed-geocoding-live"):
            workflow = (ROOT / f".github/workflows/{name}.yml").read_text()
            paths_block = workflow.split("    paths:", 1)[1].split("  workflow_dispatch:", 1)[0]
            patterns = re.findall(r'- "([^"]+)"', paths_block)
            for path in self.DEPENDENCIES:
                self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), (name, path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
