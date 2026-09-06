"""Synthetic Texas activation-readiness controls; no production activation or live address requests."""
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
TESTS = Path(__file__).resolve().parent
for path in (ROOT, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from civic_gps_extensions.loader import load_resolver_with_extensions
from civic_gps_extensions.texas_geometry_governance import PINS
from civic_gps_extensions.texas_legislative import build_texas_production_configuration
from consumers.empowered_vote import package_catalog, production_profile
from civic_gps_legislative_overlay_test import Response, Session, package as routing_package
from test_texas_bounded_contract import bounded_package, receipt
from test_tx_production_profile import compact_bindings, resolved_package
from tools import jurisdiction_package as builder
from tools.texas_activation_readiness import (
    ActivationReadinessError,
    EXPECTED_DEPLOYMENT_CHECKS,
    build_readiness_receipt,
)

HEAD = "a" * 40
ARTIFACT_SHA = "b" * 64


def package_sha(package):
    return hashlib.sha256(builder.canonical_json(package).encode("utf-8")).hexdigest()


def proposed_entry(package, acceptance):
    jid = package["jurisdiction"]["jurisdiction_id"]
    return {
        "entry_id": "tx-legislative-two-office-v0.1",
        "profile": "state_legislative_representation",
        "civic_gps_jurisdiction_id": jid,
        "package_jurisdiction_id": jid,
        "package_schema_version": "0.1",
        "artifact": {
            "encoding": "base64-parts",
            "parts_glob": "data/packages/tx/legislative/Tx_Legislative_Two_Office_v0.1.zip.b64.part*",
            "archive_sha256": ARTIFACT_SHA,
            "package_subdir": "Tx_Legislative_Two_Office_v0.1/package",
        },
        "district_bindings": compact_bindings(),
        "production_profile": {
            "profile_id": production_profile.PROFILE_ID,
            "acceptance_receipt": {
                "path": "data/packages/tx/legislative/acceptance.json",
                "sha256": hashlib.sha256(builder.canonical_json(acceptance).encode("utf-8")).hexdigest(),
            },
        },
    }


def deployment(head=HEAD, missing=None):
    ids = sorted(EXPECTED_DEPLOYMENT_CHECKS - ({missing} if missing else set()))
    return {
        "environment": "production",
        "head_sha": head,
        "status": "PASS",
        "profile_id": production_profile.PROFILE_ID,
        "checks": [{"check_id": check_id, "status": "PASS"} for check_id in ids],
    }


def production_group(package):
    groups, _ = build_texas_production_configuration(
        package, house_division_id="test-house-49", senate_division_id="test-senate-14")
    return groups[0]


def defaults():
    catalog = package_catalog.load_catalog()
    extension = json.loads((ROOT / "civic_gps_extensions" / "registry_bundles.v0.1.json").read_text(encoding="utf-8"))
    return catalog, extension


class GovernanceSession(Session):
    def __init__(self, drift=False):
        super().__init__()
        self.drift = drift
        self.metadata_calls = []

    def get(self, url, params=None, timeout=None):
        if ("Texas_State_House" in url or "Texas_State_Senate" in url) and params == {"f": "json"}:
            self.calls.append((url, copy.deepcopy(params)))
            self.metadata_calls.append((url, copy.deepcopy(params)))
            chamber = "house" if "Texas_State_House" in url else "senate"
            schema = 1742232985031 if chamber == "house" else 1742233136000
            data = 1742232985031 if chamber == "house" else 1770228332000
            body = {
                "serviceItemId": PINS[chamber]["service_item_id"],
                "name": PINS[chamber]["layer_name"],
                "editingInfo": {"schemaLastEditDate": schema, "dataLastEditDate": data},
                "fields": [{"name": "DIST_NBR", "type": "esriFieldTypeInteger"}],
            }
            if self.drift and chamber == "house":
                body["name"] = "changed"
            return Response(body)
        return super().get(url, params=params, timeout=timeout)


class TexasActivationReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.runtime_root = Path(cls.tmp.name)
        data = b"".join(path.read_bytes() for path in sorted((ROOT / "civic_gps_runtime_parts").glob("part.*")))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(cls.runtime_root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_resolved_proposal_is_ready_but_not_authorized_or_activated(self):
        package = resolved_package()
        acceptance = receipt(package=package)
        catalog, extension = defaults()
        result = build_readiness_receipt(
            package=package,
            acceptance_receipt=acceptance,
            package_sha256=package_sha(package),
            artifact_archive_sha256=ARTIFACT_SHA,
            proposed_catalog_entry=proposed_entry(package, acceptance),
            proposed_legislative_group=production_group(package),
            deployment_evidence=deployment(),
            expected_head_sha=HEAD,
            default_catalog=catalog,
            default_extension=extension,
        )
        self.assertEqual(result["status"], "READY_TO_ACTIVATE")
        self.assertFalse(result["activation_authorized"])
        self.assertEqual(result["repository_activation"], "NOT_ACTIVATED")
        self.assertEqual(result["gates"]["production_deployment"], "PASS")
        self.assertEqual(len(result["deterministic_sha256"]), 64)

    def test_provisional_people_remain_a_readiness_blocker(self):
        package = bounded_package()
        acceptance = receipt(package=package)
        catalog, extension = defaults()
        with self.assertRaises(ActivationReadinessError) as error:
            build_readiness_receipt(
                package=package, acceptance_receipt=acceptance, package_sha256=package_sha(package),
                artifact_archive_sha256=ARTIFACT_SHA, proposed_catalog_entry=proposed_entry(package, acceptance),
                proposed_legislative_group=production_group(package), deployment_evidence=deployment(),
                expected_head_sha=HEAD, default_catalog=catalog, default_extension=extension)
        self.assertEqual(error.exception.code, "PRODUCTION_PROFILE_PUBLIC_IDENTITY_UNRESOLVED")

    def test_deployment_must_cover_exact_head_and_all_required_checks(self):
        package = resolved_package()
        acceptance = receipt(package=package)
        catalog, extension = defaults()
        for evidence, expected in (
            (deployment(head="c" * 40), "ACTIVATION_DEPLOYMENT_HEAD_DRIFT"),
            (deployment(missing="hosted-runtime-route"), "ACTIVATION_DEPLOYMENT_CHECK_COVERAGE_INVALID"),
        ):
            with self.subTest(expected=expected), self.assertRaises(ActivationReadinessError) as error:
                build_readiness_receipt(
                    package=package, acceptance_receipt=acceptance, package_sha256=package_sha(package),
                    artifact_archive_sha256=ARTIFACT_SHA, proposed_catalog_entry=proposed_entry(package, acceptance),
                    proposed_legislative_group=production_group(package), deployment_evidence=evidence,
                    expected_head_sha=HEAD, default_catalog=catalog, default_extension=extension)
            self.assertEqual(error.exception.code, expected)

    def test_proposed_geometry_group_must_equal_governed_texas_configuration(self):
        package = resolved_package()
        acceptance = receipt(package=package)
        group = production_group(package)
        group["district_adapters"][0]["source"]["plan_id"] = "OTHER"
        catalog, extension = defaults()
        with self.assertRaises(ActivationReadinessError) as error:
            build_readiness_receipt(
                package=package, acceptance_receipt=acceptance, package_sha256=package_sha(package),
                artifact_archive_sha256=ARTIFACT_SHA, proposed_catalog_entry=proposed_entry(package, acceptance),
                proposed_legislative_group=group, deployment_evidence=deployment(), expected_head_sha=HEAD,
                default_catalog=catalog, default_extension=extension)
        self.assertEqual(error.exception.code, "ACTIVATION_LEGISLATIVE_GROUP_DRIFT")

    def test_readiness_refuses_to_certify_an_already_active_default_route(self):
        package = resolved_package()
        acceptance = receipt(package=package)
        catalog, extension = defaults()
        catalog = copy.deepcopy(catalog)
        catalog["entries"].append(copy.deepcopy(proposed_entry(package, acceptance)))
        with self.assertRaises(ActivationReadinessError) as error:
            build_readiness_receipt(
                package=package, acceptance_receipt=acceptance, package_sha256=package_sha(package),
                artifact_archive_sha256=ARTIFACT_SHA, proposed_catalog_entry=proposed_entry(package, acceptance),
                proposed_legislative_group=production_group(package), deployment_evidence=deployment(),
                expected_head_sha=HEAD, default_catalog=catalog, default_extension=extension)
        self.assertEqual(error.exception.code, "ACTIVATION_ALREADY_PRESENT_IN_CATALOG")

    def test_production_loader_runs_governance_preflight_before_geocoding(self):
        package = routing_package()
        groups, _ = build_texas_production_configuration(
            package, house_division_id="test-house-49", senate_division_id="test-senate-14")
        session = GovernanceSession()
        resolver = load_resolver_with_extensions(self.runtime_root, legislative_overlays=groups, session=session)
        self.assertEqual(len(session.metadata_calls), 2)
        self.assertEqual(len(session.geocoder_calls), 0)
        result = resolver.resolve("SYNTHETIC INPUT", observed_on="2026-09-06")
        tx_assignments = [row for row in result["payload"]["district_assignments"] if row.get("adapter_id", "").startswith("DIST-TX-")]
        self.assertEqual(len(tx_assignments), 2)
        self.assertTrue(all(row["scope"] == "PRODUCTION_BOUNDED" for row in tx_assignments))
        tx_coverage = [row for row in result["payload"]["coverage"] if row.get("layer") == "GEO-TX-LEGISLATIVE-TWO-DISTRICTS"]
        self.assertEqual(tx_coverage[0]["scope"], "PRODUCTION_BOUNDED")
        self.assertFalse(tx_coverage[0]["publication_eligible"])
        self.assertFalse(any(row.get("gap_id") == "GAP-GEO-TX-LEGISLATIVE-TWO-DISTRICTS-RELEASE" for row in result["payload"]["known_gaps"]))

    def test_geometry_drift_blocks_loader_before_geocoding(self):
        package = routing_package()
        groups, _ = build_texas_production_configuration(
            package, house_division_id="test-house-49", senate_division_id="test-senate-14")
        session = GovernanceSession(drift=True)
        with self.assertRaisesRegex(ValueError, "GEOMETRY_VERSION_DRIFT"):
            load_resolver_with_extensions(self.runtime_root, legislative_overlays=groups, session=session)
        self.assertEqual(len(session.geocoder_calls), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
