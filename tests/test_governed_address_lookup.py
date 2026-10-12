"""Offline CLI regressions using real governed polygons and package facts."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.governed_district_controls import load_district_controls
from tools import governed_address_lookup as lookup
from tools.geocoding_boundary import ArcGISWorldGeocoder

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime(2026, 10, 12, 14, 10, tzinfo=timezone.utc)


class Provider:
    provider_id = "OFFLINE_INJECTED_PROVIDER"

    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = []

    def find_candidates(self, address, *, max_locations):
        self.calls.append((address, max_locations))
        return self.candidates


def candidate(address, longitude, latitude, score=100, addr_type="PointAddress"):
    return {"address": address, "score": score, "location": {"x": longitude, "y": latitude},
        "attributes": {"Addr_type": addr_type}}


class LookupTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for relative in ("data/reference/co", "data/normalized/co/jurisdiction-co-alamosa",
                "data/normalized/co/jurisdiction-co-arvada"):
            shutil.copytree(ROOT / relative, self.root / relative)
        self.controls = load_district_controls(self.root)
        self.control = self.controls[0][2]
        # Every in-process test fails if it accidentally contacts a provider.
        network = patch("urllib.request.urlopen", side_effect=AssertionError("offline tests must not use the network"))
        network.start()
        self.addCleanup(network.stop)

    def provider(self, control=None):
        row = self.control if control is None else control
        return Provider([candidate(row["geocoded_address"], row["longitude"], row["latitude"])])

    def invoke(self, provider, address=None, extra=()):
        out, err = io.StringIO(), io.StringIO()
        args = [self.control["address_input"] if address is None else address,
            "--repo-root", str(self.root), *extra]
        with patch.object(lookup, "datetime") as clock, redirect_stdout(out), redirect_stderr(err):
            clock.now.return_value = STAMP
            code = lookup.main(args, geocoder=provider)
            clock.now.assert_called_once_with(timezone.utc)
        self.assertEqual(err.getvalue(), "")
        return code, json.loads(out.getvalue())

    def assert_closed(self, code, model, error):
        self.assertEqual(code, 1)
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], error)
        self.assertEqual(model["canonical_writes"], 0)
        self.assertNotIn("applicable_offices", model)

    def test_all_eight_districts_return_exact_offices_holders_and_provenance(self):
        for _, package, control in self.controls:
            with self.subTest(control=control["test_id"]):
                provider = self.provider(control)
                code, model = self.invoke(provider, control["address_input"])
                self.assertEqual(code, 0, model)
                self.assertEqual(model["status"], "PASS")
                divisions = {r["division_id"]: r["ocd_division_id"] for r in package["records"]["divisions"]}
                self.assertEqual(model["resolved_division_ocdid"], divisions[control["expected_division_id"]])
                expected_offices = set(control["expected_office_ids"].split(";"))
                self.assertEqual({r["office_id"] for r in model["applicable_offices"]}, expected_offices)
                people = {r["person_id"]: r for r in package["records"]["people"]}
                expected_people = {r["person_id"] for r in package["records"]["role_terms"]
                    if r["office_id"] in expected_offices and r["status"] == "CURRENT"}
                holders = [h for office in model["applicable_offices"] for h in office["holders"]]
                self.assertEqual({h["person_id"] for h in holders}, expected_people)
                self.assertEqual(model["current_holder_count"], len(holders))
                for holder in holders:
                    self.assertEqual(holder["name"], people[holder["person_id"]]["canonical_name"])
                self.assertEqual(model["address_resolution_source"], "GOVERNED_ADDRESS_GEOCODE_PIP")
                self.assertEqual(model["governed_geography"]["resolution_source"], "GOVERNED_GEOMETRY_PIP")
                for key in ("snapshot_path", "source_url", "source_snapshot_id"):
                    self.assertTrue(model["governed_geography"][key])
                self.assertEqual(model["canonical_writes"], 0)
                self.assertTrue(model["source_evidence"])
                self.assertTrue(model["source_assertions"])
                self.assertEqual(provider.calls, [(control["address_input"], 5)])
                self.assertEqual(model["geocoding"]["policy"]["min_score"], 95)
                self.assertEqual(model["geocoding"]["policy"]["min_margin"], 5)

    def test_geocoder_ambiguity_is_preserved_without_office_output(self):
        provider = Provider([candidate("A", -105, 39), candidate("B", -105.1, 39.1, score=98)])
        self.assert_closed(*self.invoke(provider), "AMBIGUOUS_ADDRESS")

    def test_uncovered_coordinate_fails_closed(self):
        self.assert_closed(*self.invoke(Provider([candidate("Outside", -100, 40)])),
            "POINT_OUTSIDE_ALL_GOVERNED_GEOMETRY")

    def test_missing_match_and_weak_score_preserve_provider_errors(self):
        for rows, error in (([], "ADDRESS_NOT_MATCHED"),
                ([candidate("Weak", -105, 39, score=90)], "GEOCODER_SCORE_BELOW_POLICY")):
            with self.subTest(error=error):
                self.assert_closed(*self.invoke(Provider(rows)), error)

    def test_default_adapter_and_timeout_use_current_policy(self):
        provider = self.provider()
        with patch.object(lookup, "ArcGISWorldGeocoder", return_value=provider) as factory:
            code, model = self.invoke(None, extra=("--timeout-seconds", "20"))
        self.assertEqual(code, 0, model)
        factory.assert_called_once_with(timeout_seconds=20.0)
        self.assertEqual(provider.calls[0][1], 5)

    def test_actual_adapter_request_failure_is_json_not_traceback(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("request timed out")):
            self.assert_closed(*self.invoke(ArcGISWorldGeocoder()), "GEOCODER_PROVIDER_REQUEST_FAILED")

    def test_utc_generation_timestamp_reaches_existing_runtime(self):
        with patch.object(lookup, "build_representation_for_address", wraps=lookup.build_representation_for_address) as runtime:
            code, model = self.invoke(self.provider())
        self.assertEqual(code, 0, model)
        self.assertEqual(runtime.call_args.kwargs["generated_at"], "2026-10-12T14:10:00Z")
        self.assertEqual(runtime.call_args.kwargs["root"], self.root.resolve())
        self.assertNotIn("policy", runtime.call_args.kwargs)

    def test_address_whitespace_is_normalized(self):
        address = " \n 500  Cottonwood Dr,\tAlamosa, CO 81101  "
        provider = self.provider()
        code, model = self.invoke(provider, address)
        self.assertEqual(code, 0, model)
        self.assertEqual(provider.calls[0][0], self.control["address_input"])

    def test_invalid_arguments_never_call_provider(self):
        provider = self.provider()
        loop = self.root / "loop"
        loop.symlink_to(loop)
        bad_args = ([], [""], [" "], ["a" * 501], ["A", "--timeout-seconds", "nan"],
            ["A", "--timeout-seconds", "inf"], ["A", "--timeout-seconds", "0"],
            ["A", "--timeout-seconds", "-1"], ["A", "--timeout-seconds", "121"],
            ["A", "--repo-root", str(self.root / "missing")], ["A", "--repo-root", str(loop)],
            ["A", "--expected-division", "ward-1"],
            ["A", "--min-score", "1"])
        for args in bad_args:
            with self.subTest(args=args), redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as exc:
                    lookup.main(args, geocoder=provider)
                self.assertEqual(exc.exception.code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertIn("error:", err.getvalue())
        self.assertEqual(provider.calls, [])

    def test_missing_registry_and_package_fail_with_runtime_codes(self):
        path = self.root / "data/reference/co/district_geometry_sources_v0.1.json"
        raw = path.read_bytes()
        path.unlink()
        self.assert_closed(*self.invoke(self.provider()), "GOVERNED_GEOMETRY_SOURCE_REGISTRY_INVALID")
        path.write_bytes(raw)
        shutil.rmtree(self.root / "data/normalized/co/jurisdiction-co-alamosa")
        self.assert_closed(*self.invoke(self.provider()), "GOVERNED_JURISDICTION_PACKAGE_MISSING")

    def test_unexpected_execution_failure_has_no_partial_output(self):
        with patch.object(lookup, "build_representation_for_address", side_effect=RuntimeError("internal problem")):
            self.assert_closed(*self.invoke(self.provider()), "LOOKUP_EXECUTION_FAILED")

    def test_invalid_runtime_envelopes_and_nonfinite_output_fail(self):
        for value, error in ((None, "LOOKUP_RUNTIME_RESULT_INVALID"),
                ({"status": "UNKNOWN", "canonical_writes": 0}, "LOOKUP_RUNTIME_RESULT_INVALID"),
                ({"status": "PASS", "canonical_writes": False}, "LOOKUP_RUNTIME_RESULT_INVALID"),
                ({"status": "PASS", "canonical_writes": 1}, "LOOKUP_RUNTIME_RESULT_INVALID"),
                ({"status": "PASS", "canonical_writes": 0, "bad": float("nan")}, "LOOKUP_EXECUTION_FAILED")):
            with self.subTest(error=error), patch.object(lookup, "build_representation_for_address", return_value=value):
                self.assert_closed(*self.invoke(self.provider()), error)

    def test_interrupt_returns_json_and_exit_130(self):
        with patch.object(lookup, "build_representation_for_address", side_effect=KeyboardInterrupt()):
            code, model = self.invoke(self.provider())
        self.assertEqual(code, 130)
        self.assertEqual(model["error"], "LOOKUP_INTERRUPTED")

    def test_entrypoint_works_outside_checkout_with_default_adapter(self):
        payload = json.dumps({"candidates": self.provider().candidates})
        # Patch transport inside the subprocess; the real adapter, parser and
        # script entrypoint still execute. No test-data flags exist on the CLI.
        for explicit_root in (False, True):
            with self.subTest(explicit_root=explicit_root):
                args = [str(ROOT / "tools/governed_address_lookup.py"), self.control["address_input"]]
                if explicit_root:
                    args.extend(["--repo-root", str(self.root)])
                script = (
                    "import io,json,runpy,sys\nfrom unittest.mock import patch\n"
                    f"sys.argv = {args!r}\n"
                    f"raw = {payload.encode()!r}\n"
                    "with patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(raw)):\n"
                    f"    runpy.run_path({str(ROOT / 'tools/governed_address_lookup.py')!r}, run_name='__main__')\n"
                )
                result = subprocess.run([sys.executable, "-c", script], cwd=self.root,
                    capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                self.assertEqual(result.returncode, 0, result.stderr)
                model = json.loads(result.stdout)
                self.assertEqual(model["status"], "PASS")
                self.assertEqual(model["geocoding"]["provider"], "ARCGIS_WORLD_GEOCODER")
                self.assertEqual(model["resolved_division_ocdid"], "ocd-division/country:us/state:co/place:alamosa/ward:1")

    def test_lookup_does_not_write_governed_data(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.invoke(self.provider())
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
