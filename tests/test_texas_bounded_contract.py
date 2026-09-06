"""Synthetic contract fixtures; no live requests, civic facts, or release grants."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_role_term_integration import fixture
from civic_gps_extensions.texas_legislative import build_texas_internal_configuration
from consumers.empowered_vote import package_source, representation
from tools import jurisdiction_package as builder
from tools.texas_bounded_contract import BoundedContractError, build_contract

COMMIT = "a" * 40


def encode(value):
    return builder.canonical_json(value).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def bounded_package():
    p = fixture()
    for block in ("jurisdiction", "qa"):
        p[block].update(complete_jurisdiction=False, publication_eligible=False)
    p["qa"].update(blocking_gap_count=5, blocking_gaps=[{"gap_id": f"gap-{i}"} for i in range(5)], address_tests=[])
    for chamber, kind, district in (("house", "SLDL", "49"), ("senate", "SLDU", "14")):
        d = next(r for r in p["records"]["divisions"] if chamber in r["division_id"])
        d.update(division_kind=kind, division_name=f"Texas {chamber.title()} District {district}")
    return p


def public_identity_compatible_package():
    """Keep this suite's legacy-scope probe independent of provisional-identity policy."""
    p = fixture()
    for person in p["records"]["people"]:
        for key in ("person_status", "identity_resolution_status", "status", "current_status"):
            person.pop(key, None)
    p["warnings"] = []
    return p


def archive_files(package):
    groups, bindings = build_texas_internal_configuration(package, house_division_id="test-house-49", senate_division_id="test-senate-14")
    gps = {"payload": {"jurisdictions": [groups[0]["jurisdiction"]],
                       "district_assignments": [{"adapter_id": a["adapter_id"], "district_key": next(iter(a["districts"]))} for a in groups[0]["district_adapters"]]}}
    files = {
        "source_snapshot.json": {"source_candidate_sha256": digest(encode(package)), "runtime_zip_sha256": "b" * 64},
        "acceptance_verification.json": {"commit": COMMIT, "scope": "BOUNDED_INTERNAL_LIVE_ACCEPTANCE", "status": "PASS",
                                         "checks": [{"status": "PASS"}], "passed": 1, "total": 1},
        "address_control_summary.json": [], "boundary_control_summary.json": [], "geometry_comparison.json": [],
    }
    for case, expected in (("positive", "PASS"), ("negative", "FAIL-CLOSED")):
        geography = gps if case == "positive" else {"payload": {"jurisdictions": [], "district_assignments": []}}
        preview = representation.preview_representation_for_bindings(package, case, geography, bindings=bindings)
        files["address_control_summary.json"].append({"case_id": case, "address": case, "expect": expected,
                                                     "geocoder_requests": 1, "expected_status_met": True})
        files[f"address_controls/{case}/result.json"] = {"status": preview["status"], "representation": preview,
            "geography": geography, "scope": "INTERNAL_REVIEW", "canonical_writes": 0,
            "publication_eligible": False, "complete_jurisdiction": False}
    for chamber in ("house", "senate"):
        for position, expected in (("midpoint", "CONFLICT"), ("near", "CONFLICT"), ("inside", "PASS")):
            files["boundary_control_summary.json"].append({"case_id": chamber + "-" + position, "chamber": chamber,
                "expected": expected, "result": {"status": expected}, "expected_status_met": True,
                "geocoder_requests": 0, "address": None, "control_scope": "LIVE_COORDINATE_ADAPTER_ONLY"})
    return files


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for path, value in sorted(files.items()):
            z.writestr("synthetic/" + path, encode(value))
    return stream.getvalue()


def receipt(package=None, files=None, **changes):
    p = bounded_package() if package is None else package
    raw = encode(p)
    data = archive(archive_files(p) if files is None else files)
    args = {"expected_package_sha256": digest(raw), "expected_evidence_sha256": digest(data),
            "expected_tested_commit": COMMIT, "house_division_id": "test-house-49", "senate_division_id": "test-senate-14"}
    args.update(changes)
    return build_contract(raw, data, **args)


class BoundedContractTests(unittest.TestCase):
    def test_receipt_is_internal_deterministic_and_source_immutable(self):
        p = bounded_package()
        before = copy.deepcopy(p)
        a, b = receipt(p), receipt(p)
        self.assertEqual(a, b)
        self.assertEqual(p, before)
        self.assertEqual(a["status"], "INTERNAL_REVIEW_ACCEPTED")
        self.assertFalse(a["complete_jurisdiction"])
        self.assertFalse(a["publication_eligible"])
        self.assertFalse(a["production_release_eligible"])
        self.assertEqual(a["source_qa_preserved"]["blocking_gap_count"], 5)
        self.assertEqual(a["scope"]["address_domain"], "HOUSE_49_INTERSECTION_SENATE_14")

    def test_input_hash_and_commit_pins_are_required(self):
        for args in ({"expected_package_sha256": "0" * 64}, {"expected_evidence_sha256": "0" * 64},
                     {"expected_tested_commit": "c" * 40}, {"expected_tested_commit": "main"}):
            with self.subTest(args=args), self.assertRaises(BoundedContractError):
                receipt(**args)

    def test_evidence_must_bind_the_exact_package(self):
        p = bounded_package(); files = archive_files(p)
        files["source_snapshot.json"]["source_candidate_sha256"] = "0" * 64
        with self.assertRaisesRegex(BoundedContractError, "EVIDENCE_PACKAGE_MISMATCH"):
            receipt(p, files)

    def test_failed_or_incomplete_evidence_rejected(self):
        mutations = [
            lambda f: f["acceptance_verification.json"].update(status="FAIL"),
            lambda f: f["acceptance_verification.json"]["checks"][0].update(status="FAIL"),
            lambda f: f["acceptance_verification.json"].update(passed=True),
            lambda f: f["address_control_summary.json"].pop(),
            lambda f: f["address_control_summary.json"][0].update(geocoder_requests=2),
            lambda f: f["address_control_summary.json"][0].update(geocoder_requests=True),
            lambda f: f["boundary_control_summary.json"].pop(),
            lambda f: f["boundary_control_summary.json"][0]["result"].update(status="PASS"),
        ]
        for mutate in mutations:
            p = bounded_package(); files = archive_files(p); mutate(files)
            with self.subTest(mutation=mutate), self.assertRaises(BoundedContractError):
                receipt(p, files)

    def test_preview_scope_or_projection_drift_rejected(self):
        for mutate in (lambda r: r.update(publication_eligible=True),
                       lambda r: r["representation"]["projections"][0]["representation"]["applicable_offices"][0]["holders"][0].update(name="Changed")):
            p = bounded_package(); files = archive_files(p)
            mutate(files["address_controls/positive/result.json"])
            with self.assertRaises(BoundedContractError):
                receipt(p, files)

    def test_cleared_QA_does_not_make_partial_package_production_valid(self):
        p = bounded_package()
        p["qa"].update(blocking_gap_count=0, blocking_gaps=[], address_tests=[{"result": True}, {"result": True}])
        self.assertIn("partial_jurisdiction_scope:jurisdiction", builder.validate(p))
        with self.assertRaises(package_source.PackageContractError) as exc:
            package_source._validate_package_shape(p)
        self.assertEqual(exc.exception.code, "PACKAGE_PARTIAL_SCOPE_UNSUPPORTED")

    def test_partial_scope_rejected_after_resigning_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder.build(fixture(), root)
            p = json.loads((root / "jurisdiction.json").read_text())
            p["jurisdiction"]["complete_jurisdiction"] = False
            (root / "jurisdiction.json").write_bytes(encode(p))
            manifest = json.loads((root / "manifest.json").read_text())
            for row in manifest["files"]:
                row["bytes"] = (root / row["path"]).stat().st_size
            (root / "manifest.json").write_bytes(encode(manifest))
            (root / "SHA256SUMS.txt").write_text("".join(digest(path.read_bytes()) + "  " + path.name + "\n" for path in sorted(root.iterdir()) if path.name != "SHA256SUMS.txt"))
            with self.assertRaises(package_source.PackageContractError) as exc:
                package_source.load_jurisdiction_package(root)
            self.assertEqual(exc.exception.code, "PACKAGE_PARTIAL_SCOPE_UNSUPPORTED")

    def test_false_or_malformed_coverage_in_either_block_rejected(self):
        for block in ("jurisdiction", "qa"):
            for value in (False, None, 0, 1, "false", "true"):
                p = fixture(); p[block]["complete_jurisdiction"] = value
                with self.subTest(block=block, value=value):
                    self.assertIn("partial_jurisdiction_scope:" + block, builder.validate(p))

    def test_legacy_package_and_explicit_true_remain_scope_compatible(self):
        for explicit in (False, True):
            p = public_identity_compatible_package()
            if explicit:
                for block in ("jurisdiction", "qa"): p[block]["complete_jurisdiction"] = True
            self.assertEqual(builder.validate(p), [])
            package_source._validate_package_shape(p)

    def test_missing_partial_declaration_or_source_QA_failure_rejected(self):
        for mutate in (lambda p: p["jurisdiction"].pop("complete_jurisdiction"),
                       lambda p: p["qa"].update(parity_ok=False),
                       lambda p: p["qa"].update(qa_fail_count=1),
                       lambda p: p["qa"].update(blocking_gap_count=4)):
            p = bounded_package(); mutate(p)
            with self.assertRaises(BoundedContractError): receipt(p)

    def test_added_or_omitted_chain_rejected(self):
        p = bounded_package(); p["records"]["role_terms"].pop()
        with self.assertRaises(BoundedContractError): receipt(p)

    def test_receipt_is_not_a_jurisdiction_package(self):
        r = receipt()
        self.assertEqual(builder.validate(r), ["schema_version"])
        with self.assertRaises(package_source.PackageContractError) as exc:
            package_source._validate_package_shape(r)
        self.assertEqual(exc.exception.code, "PACKAGE_SCHEMA_VERSION_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()