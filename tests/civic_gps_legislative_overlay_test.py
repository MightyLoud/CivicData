"""Offline controls against the pinned core engine; all network responses are synthetic."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import zipfile
import io
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_role_term_integration import fixture
from civic_gps_extensions.loader import load_resolver_with_extensions
from civic_gps_extensions.legislative import validate_legislative_groups
from civic_gps_extensions.texas_legislative import build_texas_internal_configuration, resolve_texas_internal_preview
from consumers.empowered_vote import representation
import requests


def package():
    p = fixture()
    for chamber, kind, number in (("house", "SLDL", "49"), ("senate", "SLDU", "14")):
        d = next(d for d in p["records"]["divisions"] if chamber in d["division_id"])
        d.update(division_kind=kind, division_name=f"Texas {chamber.title()} District {number}")
        person = next(p for p in p["records"]["people"] if chamber in p["person_id"])
        person["person_full_name"] = person.pop("canonical_name")
        person["identity_resolution_status"] = person.pop("person_status")
    # Deliberately blocked production package; internal preview must not alter this.
    p["qa"]["blocking_gap_count"] = 5
    p["qa"]["address_tests"] = []
    return p


def configuration(p=None):
    return build_texas_internal_configuration(
        package() if p is None else p, house_division_id="test-house-49", senate_division_id="test-senate-14")


class Response:
    def __init__(self, body):
        self.body = copy.deepcopy(body)
    def raise_for_status(self):
        pass
    def json(self):
        return copy.deepcopy(self.body)


class Session:
    def __init__(self):
        self.calls = []
        self.overrides = {}
        self.matches = 1
        self.state = "48"
        self.county = "48999"
        self.coordinates = {"x": -97.7, "y": 30.2}
        self.geographies_override = None
        self.barrier = None
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, copy.deepcopy(params)))
        if "geocoding.geo.census.gov" in url:
            if self.barrier:
                self.barrier.wait(timeout=5)
            row = {"matchedAddress": params["address"].upper(), "coordinates": self.coordinates,
                   "geographies": {"States": [{"GEOID": self.state, "STATE": self.state}],
                                   "Counties": [{"GEOID": self.county}],
                                   "Incorporated Places": [{"GEOID": "4805000"}]}}
            if self.geographies_override is not None:
                row["geographies"] = self.geographies_override
            return Response({"result": {"addressMatches": [row] * self.matches}})
        if "Texas_State_House" in url or "Texas_State_Senate" in url:
            chamber = "house" if "Texas_State_House" in url else "senate"
            phase = "probe" if "distance" in params else "exact"
            body = self.overrides.get((chamber, phase), {
                "features": [{"attributes": {"DIST_NBR": 49 if chamber == "house" else 14, "REP_NM": "POISON GIS NAME"}}]})
            if isinstance(body, Exception):
                raise body
            return Response(body)
        if "gis.traviscountytx.gov" in url:
            return Response({"features": [{"attributes": {"PRECINCT": "1"}}]})
        if "synthetic-city.invalid" in url:
            return Response({"features": [{"attributes": {"CITY_ID": "synthetic-city"}}]})
        raise AssertionError("Unexpected network route: " + url)
    @property
    def geocoder_calls(self):
        return [c for c in self.calls if "geocoding.geo.census.gov" in c[0]]
    @property
    def legislative_calls(self):
        return [c for c in self.calls if "Texas_State_" in c[0]]


class LegislativeRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        data = b"".join(p.read_bytes() for p in sorted((ROOT / "civic_gps_runtime_parts").glob("part.*")))
        assert hashlib.sha256(data).hexdigest() == "a1d323db8ed7eaaa47e3541a42bacef4377e9c41161f7a2ad888ddf86e5fe192"
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(cls.root)
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
    def setUp(self):
        self.session = Session()
        self.groups, self.bindings = configuration()
    def resolver(self, groups=None, extension_path=None):
        return load_resolver_with_extensions(
            self.root, session=self.session, extension_path=extension_path,
            legislative_overlays=self.groups if groups is None else groups)
    def resolve(self):
        return self.resolver().resolve("SYNTHETIC INPUT", observed_on="2026-09-06")
    def assert_suppressed(self, result):
        payload = result["payload"]
        self.assertFalse(any(a["adapter_id"].startswith("DIST-TX-HOUSE") or a["adapter_id"].startswith("DIST-TX-SENATE")
                             for a in payload["district_assignments"]))
        self.assertNotIn("test-jurisdiction", {j["jurisdiction_id"] for j in payload["jurisdictions"]})
        self.assertTrue(payload["known_gaps"])

    def test_one_geocode_two_chambers_no_civic_facts(self):
        before = copy.deepcopy(self.groups)
        r = self.resolve()
        p = r["payload"]
        self.assertEqual(len(self.session.geocoder_calls), 1)
        self.assertEqual(len(self.session.legislative_calls), 4)
        self.assertEqual({a["district_key"] for a in p["district_assignments"]}, {"49", "14"})
        for key in ("offices", "officeholders", "applicable_offices", "action_links"):
            self.assertEqual(p[key], [])
        self.assertNotIn("POISON GIS NAME", json.dumps(r))
        self.assertEqual(self.groups, before)
        self.assertTrue(all(a["status"] == "GEOGRAPHY_ONLY" for a in p["district_assignments"]))
        self.assertTrue(all(c[1]["outFields"] == "DIST_NBR" for c in self.session.legislative_calls))
        self.assertTrue(all(c[1]["where"] == "1=1" for c in self.session.legislative_calls))
        self.assertEqual(len(p["evidence"]), 5)  # One geocode plus four geometry calls.
        self.assertTrue(all(e.get("verified_on") == "2026-09-06" for e in p["evidence"]))

    def test_complete_internal_consumer_keeps_raw_tx_identity_and_qa(self):
        p = package()
        before = copy.deepcopy(p)
        r = resolve_texas_internal_preview(
            p, "SYNTHETIC INPUT", repo_root=self.root, session=self.session,
            house_division_id="test-house-49", senate_division_id="test-senate-14")
        self.assertEqual(r["status"], "PASS")
        self.assertFalse(r["publication_eligible"])
        self.assertEqual(len(r["representation"]["projections"]), 2)
        for projection in r["representation"]["projections"]:
            holder = projection["representation"]["applicable_offices"][0]["holders"][0]
            self.assertEqual(holder["person_status"], "PROVISIONAL")
            self.assertEqual(holder["term_start"], "2025-01-14")
            self.assertIsNone(holder["term_end"])
            self.assertTrue(holder["name"].startswith("Synthetic"))
        self.assertEqual(p, before)

    def test_default_consumer_still_rejects_raw_provisional_person(self):
        r = representation.build_representation_from_civic_gps_result(
            package(), "SYNTHETIC INPUT", self.resolve(), binding=self.bindings[0])
        self.assertEqual(r["error"], "PERSON_IDENTITY_PROVISIONAL")

    def test_exact_multiple_polygons_suppress_both_chambers(self):
        self.session.overrides["senate", "exact"] = {"features": [{"attributes": {"DIST_NBR": n}} for n in (14, 21)]}
        r = self.resolve()
        self.assert_suppressed(r)
        self.assertEqual(len(r["payload"]["evidence"]), 1)  # No partial successful House assertion.
        preview = representation.preview_representation_for_bindings(package(), "SYNTHETIC", r, bindings=self.bindings)
        self.assertEqual(preview["status"], "FAIL-CLOSED")
        self.assertNotIn("projections", preview)

    def test_boundary_probe_ambiguity_suppresses_group(self):
        self.session.overrides["house", "probe"] = {"features": [{"attributes": {"DIST_NBR": n}} for n in (49, 48)]}
        self.assert_suppressed(self.resolve())

    def test_boundary_probe_disagreement_suppresses_group(self):
        self.session.overrides["senate", "probe"] = {"features": [{"attributes": {"DIST_NBR": 21}}]}
        r = self.resolve()
        self.assert_suppressed(r)
        self.assertTrue(any("INCONSISTENT" in g["gap_id"] for g in r["payload"]["known_gaps"]))

    def test_outside_configured_slice_suppresses_group(self):
        for phase in ("exact", "probe"):
            self.session.overrides["senate", phase] = {"features": [{"attributes": {"DIST_NBR": 21}}]}
        r = self.resolve()
        self.assert_suppressed(r)
        self.assertTrue(any(g["status"] == "OUT_OF_SCOPE" for g in r["payload"]["known_gaps"]))

    def test_outside_state_does_not_query_districts(self):
        self.session.state = "01"
        self.assert_suppressed(self.resolve())
        self.assertEqual(len(self.session.legislative_calls), 0)

    def test_bad_or_truncated_features_suppress_group(self):
        bodies = [{}, {"features": None}, {"features": []}, {"features": [None]},
                  {"features": [{"attributes": {"DIST_NBR": True}}]},
                  {"features": [{"attributes": {"DIST_NBR": "14.0"}}]},
                  {"features": [{"attributes": {"DIST_NBR": 14}}], "exceededTransferLimit": True}]
        for body in bodies:
            with self.subTest(body=body):
                self.session.overrides["senate", "exact"] = body
                self.assert_suppressed(self.resolve())

    def test_network_error_suppresses_group(self):
        self.session.overrides["senate", "exact"] = requests.RequestException("synthetic source failure")
        self.assert_suppressed(self.resolve())

    def test_geocoder_zero_or_multiple_matches_stop_before_gis(self):
        for count, error in ((0, "ADDRESS_NOT_MATCHED"), (2, "AMBIGUOUS_ADDRESS")):
            with self.subTest(count=count):
                self.session = Session()
                self.session.matches = count
                self.assertEqual(self.resolve()["error"]["code"], error)
                self.assertEqual(self.session.legislative_calls, [])

    def test_invalid_coordinates_stop_before_gis(self):
        for coordinates in ({"x": float("nan"), "y": 30}, {"x": -181, "y": 30},
                            {"x": True, "y": 30}, {"x": "-97.7", "y": 30}):
            with self.subTest(coordinates=coordinates):
                self.session = Session()
                self.session.coordinates = coordinates
                self.assertEqual(self.resolve()["error"]["code"], "GEOCODER_COORDINATES_INVALID")
                self.assertEqual(self.session.legislative_calls, [])

    def test_new_call_never_reuses_previous_geocode(self):
        resolver = self.resolver()
        a = resolver.resolve("FIRST", observed_on="2026-09-06")
        b = resolver.resolve("SECOND", observed_on="2026-09-06")
        self.assertEqual(len(self.session.geocoder_calls), 2)
        self.assertEqual(a["payload"]["input"]["matched_address"], "FIRST")
        self.assertEqual(b["payload"]["input"]["matched_address"], "SECOND")

    def test_malformed_geographies_stop_before_gis(self):
        self.session.geographies_override = []
        self.assertEqual(self.resolve()["error"]["code"], "GEOCODER_GEOGRAPHIES_INVALID")
        self.assertEqual(self.session.legislative_calls, [])

    def test_ambiguous_or_conflicting_state_stops_legislative_queries(self):
        for states in ([{"GEOID": "48"}, {"GEOID": "01"}], [{"GEOID": "48", "STATE": "01"}], []):
            with self.subTest(states=states):
                self.session = Session()
                self.session.geographies_override = {"States": states}
                self.assert_suppressed(self.resolve())
                self.assertEqual(self.session.legislative_calls, [])

    def test_parallel_calls_keep_geocode_context_isolated(self):
        self.session.barrier = threading.Barrier(2)
        resolver = self.resolver()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(resolver.resolve, ("FIRST", "SECOND")))
        self.assertEqual(len(self.session.geocoder_calls), 2)
        self.assertEqual([r["payload"]["input"]["matched_address"] for r in results], ["FIRST", "SECOND"])

    def test_failed_call_does_not_poison_next_call(self):
        resolver = self.resolver()
        self.session.matches = 0
        self.assertIn("error", resolver.resolve("FIRST"))
        self.session.matches = 1
        self.assertNotIn("error", resolver.resolve("SECOND"))
        self.assertEqual(len(self.session.geocoder_calls), 2)

    def test_existing_county_facts_survive_success_and_group_failure(self):
        self.session.county = "48453"
        base = self.resolver(groups=[]).resolve("SYNTHETIC INPUT", observed_on="2026-09-06")
        for failure in (False, True):
            if failure:
                self.session.overrides["senate", "exact"] = {"features": []}
            routed = self.resolve()
            for key in ("offices", "officeholders", "applicable_offices", "action_links"):
                self.assertEqual(routed["payload"][key], base["payload"][key])

    def test_municipal_overlay_and_legislative_share_one_geocode(self):
        self.session.county = "48453"
        with tempfile.TemporaryDirectory() as tmp:
            release = self.root / "civic_gps/synthetic_city.json"
            release.write_text(json.dumps({"payload": {"jurisdictions": [{"jurisdiction_id": "synthetic-city", "name": "Synthetic city"}]}}))
            ext = Path(tmp) / "extension.json"
            ext.write_text(json.dumps({"extension_version": "0.1", "bundles": [], "municipal_boundary_overlays": [{
                "overlay_id": "MUNI-SYNTHETIC", "parent_jurisdiction_id": "jur-us-tx-travis-county",
                "service_url": "https://synthetic-city.invalid/FeatureServer/0", "where": "CITY_ID='synthetic-city'",
                "identity_field": "CITY_ID", "identity_value": "synthetic-city", "jurisdiction_id": "synthetic-city",
                "division_id": "synthetic-city-division", "division_name": "Synthetic city", "release_file": "synthetic_city.json"
            }]}))
            r = self.resolver(extension_path=ext).resolve("SYNTHETIC INPUT")
            self.assertNotIn("error", r)
            self.assertIn("synthetic-city", {j["jurisdiction_id"] for j in r["payload"]["jurisdictions"]})
            self.assertEqual(len(self.session.geocoder_calls), 1)

    def test_stable_semantic_hash(self):
        a = self.resolve()
        b = self.resolve()
        self.assertEqual(a["meta"]["canonical_content_sha256"], b["meta"]["canonical_content_sha256"])

    def test_explicit_mapping_and_internal_scope_validation(self):
        mutations = [
            lambda g: g[0].update(publication_eligible=True),
            lambda g: g[0].update(scope="RELEASE_BACKED"),
            lambda g: g[0]["jurisdiction"].update(officeholders=[]),
            lambda g: g[0]["district_adapters"][0].update(boundary_probe_distance_meters=0),
            lambda g: g[0]["district_adapters"][1].update(adapter_id=g[0]["district_adapters"][0]["adapter_id"]),
            lambda g: g[0]["district_adapters"][1]["districts"]["14"].update(division_id="test-house-49"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                groups = copy.deepcopy(self.groups)
                mutate(groups)
                with self.assertRaises(ValueError):
                    validate_legislative_groups(groups)
        with self.assertRaises(ValueError):
            validate_legislative_groups(self.groups, ["DIST-TX-HOUSE-H2316"])
        with self.assertRaises(ValueError):
            build_texas_internal_configuration(package(), house_division_id="missing", senate_division_id="test-senate-14")

    def test_result_identity_collision_is_not_silently_deduplicated(self):
        self.groups[0]["district_adapters"][0]["districts"]["49"]["division_id"] = "div-us-tx"
        self.session.county = "48453"
        self.assert_suppressed(self.resolve())

    def test_default_configuration_does_not_activate_texas_legislation(self):
        self.session.county = "48453"
        r = self.resolver(groups=[]).resolve("SYNTHETIC")
        self.assertFalse(any("HOUSE" in a["adapter_id"] or "SENATE" in a["adapter_id"] for a in r["payload"]["district_assignments"]))
        self.assertEqual(len(self.session.legislative_calls), 0)


if __name__ == "__main__":
    unittest.main()
