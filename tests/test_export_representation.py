from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.export_representation import (
    SUPPORTED_CONSUMERS,
    build_report,
    discover_packages,
    evaluate_package,
    render_markdown,
    write_artifacts,
)

STAMP = "2026-09-26T16:30:00Z"


class GenericRepresentationConformanceTests(unittest.TestCase):
    def test_repository_discovery_finds_all_normalized_jurisdiction_packages(self):
        paths = discover_packages(ROOT)
        self.assertEqual(
            [str(path.relative_to(ROOT)) for path in paths],
            [
                "data/normalized/co/jurisdiction-co-akron/jurisdiction.json",
                "data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json",
                "data/normalized/co/jurisdiction-co-alma/jurisdiction.json",
                "data/normalized/co/jurisdiction-co-arvada/jurisdiction.json",
                "data/normalized/co/jurisdiction-co-aspen/jurisdiction.json",
            ],
        )

    def test_all_certified_runs_every_current_package(self):
        paths = discover_packages(ROOT)
        report, _ = build_report(
            paths,
            root=ROOT,
            generated_at=STAMP,
            certified_only=True,
        )
        self.assertEqual(report["selection"]["discovered_count"], 5)
        self.assertEqual(report["selection"]["selected_count"], 5)
        self.assertEqual(report["selection"]["excluded"], [])
        self.assertEqual(report["summary"]["jurisdictions"], 5)
        self.assertEqual(report["summary"]["certification"], {"certified": 5})
        self.assertEqual(report["summary"]["source_package"], {"PASS": 5})
        self.assertEqual(report["summary"]["canonical_core"], {"PASS": 5})

    def test_contract_and_consumer_conformance_is_generic(self):
        report, _ = build_report(
            discover_packages(ROOT),
            root=ROOT,
            generated_at=STAMP,
            certified_only=True,
        )
        for row in report["results"]:
            with self.subTest(jurisdiction=row["jurisdiction_name"]):
                self.assertIn(
                    row["representation_contract"]["status"],
                    {"PASS", "LOSSY"},
                )
                self.assertEqual(
                    row["consumers"]["civicpatch"]["status"],
                    "PASS",
                    row["consumers"]["civicpatch"],
                )
                self.assertEqual(
                    row["consumers"]["empowered_vote"]["status"],
                    "PASS",
                    row["consumers"]["empowered_vote"],
                )
                self.assertEqual(
                    row["consumers"]["civic_mirror"]["status"],
                    "NOT_TESTED",
                )
                self.assertEqual(
                    row["consumers"]["seegov"]["status"],
                    "NOT_TESTED",
                )
                self.assertEqual(
                    row["consumers"]["civic_mirror"]["mode"],
                    "PARTNER_INBOUND_ONLY",
                )
                self.assertEqual(
                    row["consumers"]["seegov"]["mode"],
                    "PARTNER_INBOUND_ONLY",
                )

    def test_civicpatch_round_trip_has_no_semantic_loss_for_all_packages(self):
        report, _ = build_report(
            discover_packages(ROOT),
            root=ROOT,
            generated_at=STAMP,
            consumers=("civicpatch",),
            certified_only=True,
        )
        for row in report["results"]:
            with self.subTest(jurisdiction=row["jurisdiction_name"]):
                consumer = row["consumers"]["civicpatch"]
                self.assertEqual(consumer["status"], "PASS")
                self.assertEqual(consumer["semantic_loss"], [])
                self.assertGreaterEqual(len(consumer["identity_gaps"]), 1)

    def test_empowered_vote_static_contract_is_valid_but_runtime_is_explicitly_untested(self):
        report, _ = build_report(
            discover_packages(ROOT),
            root=ROOT,
            generated_at=STAMP,
            consumers=("empowered_vote",),
            certified_only=True,
        )
        for row in report["results"]:
            with self.subTest(jurisdiction=row["jurisdiction_name"]):
                consumer = row["consumers"]["empowered_vote"]
                self.assertEqual(consumer["status"], "PASS")
                self.assertIn(
                    "address_resolution_without_binding_fixture",
                    consumer["untested_capabilities"],
                )
                self.assertIn("civic_gps_runtime", consumer["untested_capabilities"])

    def test_contract_date_enrichment_is_visible_not_silent(self):
        akron = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
        result, _ = evaluate_package(
            akron,
            root=ROOT,
            generated_at=STAMP,
        )
        notes = result["representation_contract"]["semantic_notes"]
        self.assertTrue(
            any(
                note.startswith(
                    "CONTRACT_PARTIAL_DATE_ENRICHMENT:role-co-akron-"
                )
                for note in notes
            ),
            notes,
        )

    def test_blocked_source_package_fails_closed_before_consumers(self):
        source = json.loads(
            (
                ROOT
                / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
            ).read_text(encoding="utf-8")
        )
        source["qa"]["parity_ok"] = False
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data/normalized/co/broken/jurisdiction.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(source), encoding="utf-8")
            result, _ = evaluate_package(
                path,
                root=root,
                generated_at=STAMP,
            )
        self.assertEqual(result["source_package"]["status"], "BLOCKED")
        for consumer in SUPPORTED_CONSUMERS:
            self.assertEqual(result["consumers"][consumer]["status"], "BLOCKED")

    def test_report_and_markdown_are_deterministic(self):
        paths = discover_packages(ROOT)
        first, _ = build_report(
            paths,
            root=ROOT,
            generated_at=STAMP,
            certified_only=True,
        )
        second, _ = build_report(
            paths,
            root=ROOT,
            generated_at=STAMP,
            certified_only=True,
        )
        self.assertEqual(first, second)
        self.assertEqual(render_markdown(first), render_markdown(second))
        markdown = render_markdown(first)
        for name in ("Akron", "Alamosa", "Alma", "Arvada", "Aspen"):
            self.assertIn(name, markdown)

    def test_artifact_writer_emits_core_contract_civicpatch_and_result(self):
        path = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
        report, payloads = build_report(
            [path],
            root=ROOT,
            generated_at=STAMP,
            certified_only=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            write_artifacts(dest, report=report, payloads_by_path=payloads)
            out = dest / "jurisdiction-co-akron"
            self.assertTrue((out / "canonical_core.json").is_file())
            self.assertTrue((out / "representation_contract_v1.json").is_file())
            self.assertTrue((out / "civicpatch_bundle.json").is_file())
            self.assertTrue((out / "conformance.json").is_file())

    def test_consumer_subset_does_not_fake_unrequested_results(self):
        path = ROOT / "data/normalized/co/jurisdiction-co-akron/jurisdiction.json"
        report, _ = build_report(
            [path],
            root=ROOT,
            generated_at=STAMP,
            consumers=("civicpatch",),
        )
        self.assertEqual(set(report["results"][0]["consumers"]), {"civicpatch"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
