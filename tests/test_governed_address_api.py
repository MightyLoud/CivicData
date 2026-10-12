"""Offline HTTP controls through real governed polygons and package facts."""
from __future__ import annotations

from contextlib import redirect_stderr
from datetime import timezone
import http.client
import io
import json
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import uvicorn

from services.governed_address_api import main as api
from services.governed_address_api import __main__ as launcher
from tests.governed_district_controls import load_district_controls
from tests.test_governed_address_lookup import Provider, candidate, STAMP
from tools.geocoding_boundary import ArcGISWorldGeocoder

ROOT = Path(__file__).resolve().parents[1]


class AddressApiTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for relative in ("data/reference/co", "data/normalized/co/jurisdiction-co-alamosa",
                "data/normalized/co/jurisdiction-co-arvada"):
            shutil.copytree(ROOT / relative, self.root / relative)
        self.controls = load_district_controls(self.root)
        self.control = self.controls[0][2]
        provider = patch("urllib.request.urlopen", side_effect=AssertionError("offline API tests must not call a provider"))
        provider.start()
        self.addCleanup(provider.stop)

    def provider(self, control=None):
        row = self.control if control is None else control
        return Provider([candidate(row["geocoded_address"], row["longitude"], row["latitude"])])

    def client(self, provider=None, **kwargs):
        return TestClient(api.create_app(repo_root=self.root,
            geocoder=self.provider() if provider is None else provider, **kwargs))

    def post(self, client, address=None):
        with patch.object(api, "datetime") as clock:
            clock.now.return_value = STAMP
            response = client.post("/v1/representation", json={
                "address": self.control["address_input"] if address is None else address})
            clock.now.assert_called_once_with(timezone.utc)
        return response

    def assert_failure(self, response, status, error):
        self.assertEqual(response.status_code, status, response.text)
        model = response.json()
        self.assertEqual(model["status"], "FAIL-CLOSED")
        self.assertEqual(model["error"], error)
        self.assertEqual(model["canonical_writes"], 0)
        self.assertNotIn("applicable_offices", model)

    def test_eight_districts_return_exact_offices_holders_and_provenance(self):
        for _, package, control in self.controls:
            with self.subTest(control=control["test_id"]):
                provider = self.provider(control)
                with self.client(provider) as client:
                    response = self.post(client, control["address_input"])
                self.assertEqual(response.status_code, 200, response.text)
                model = response.json()
                divisions = {r["division_id"]: r["ocd_division_id"] for r in package["records"]["divisions"]}
                self.assertEqual(model["resolved_division_ocdid"], divisions[control["expected_division_id"]])
                offices = set(control["expected_office_ids"].split(";"))
                self.assertEqual({r["office_id"] for r in model["applicable_offices"]}, offices)
                expected_people = {r["person_id"] for r in package["records"]["role_terms"]
                    if r["office_id"] in offices and r["status"] == "CURRENT"}
                actual_people = {h["person_id"] for r in model["applicable_offices"] for h in r["holders"]}
                self.assertEqual(actual_people, expected_people)
                self.assertEqual(model["governed_geography"]["resolution_source"], "GOVERNED_GEOMETRY_PIP")
                for field in ("source_url", "snapshot_path", "source_snapshot_id"):
                    self.assertTrue(model["governed_geography"][field])
                self.assertEqual(model["canonical_writes"], 0)
                self.assertEqual(provider.calls, [(control["address_input"], 5)])
                self.assertEqual(model["geocoding"]["policy"]["min_score"], 95)
                self.assertEqual(model["geocoding"]["policy"]["min_margin"], 5)
                self.assertEqual(response.headers["cache-control"], "no-store")

    def test_health_is_process_only_and_never_geocodes(self):
        provider = Provider([])
        shutil.rmtree(self.root / "data")
        with self.client(provider) as client:
            response = client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service_id"], api.SERVICE_ID)
        self.assertEqual(provider.calls, [])

    def test_invalid_json_shapes_types_and_fields_are_rejected_before_geocoding(self):
        provider = Provider([])
        with self.client(provider) as client:
            for body in ({}, {"address": None}, {"address": 123}, {"address": True},
                    {"address": ""}, {"address": " \n\t "}, {"address": "a" * 501}, [], "A",
                    {"address": "A", "expected_division": "ward-1"},
                    {"address": "A", "latitude": 37.4, "longitude": -105.8},
                    {"address": "A", "repo_root": "/tmp"},
                    {"address": "A", "min_score": 1}, {"address": ["A"]}):
                with self.subTest(body=body):
                    self.assert_failure(client.post("/v1/representation", json=body), 422, "ADDRESS_REQUEST_INVALID")
            self.assert_failure(client.post("/v1/representation", content="{broken",
                headers={"content-type": "application/json"}), 422, "ADDRESS_REQUEST_INVALID")
        self.assertEqual(provider.calls, [])

    def test_whitespace_normalization_matches_cli(self):
        provider = self.provider()
        with self.client(provider) as client:
            response = self.post(client, " 500  Cottonwood Dr,\nAlamosa, CO 81101 ")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(provider.calls[0][0], self.control["address_input"])

    def test_no_match_and_outside_coverage_are_http_404(self):
        for rows, error in (([], "ADDRESS_NOT_MATCHED"),
                ([candidate("Outside", -100, 40)], "POINT_OUTSIDE_ALL_GOVERNED_GEOMETRY")):
            with self.subTest(error=error), self.client(Provider(rows)) as client:
                self.assert_failure(self.post(client), 404, error)

    def test_ambiguity_and_weak_matches_are_http_422(self):
        cases = (([candidate("A", -105, 39), candidate("B", -105.1, 39.1, score=98)], "AMBIGUOUS_ADDRESS"),
            ([candidate("Weak", -105, 39, score=90)], "GEOCODER_SCORE_BELOW_POLICY"),
            ([candidate("Postal", -105, 39, addr_type="Postal")], "GEOCODER_ADDRESS_TYPE_NOT_ALLOWED"))
        for rows, error in cases:
            with self.subTest(error=error), self.client(Provider(rows)) as client:
                self.assert_failure(self.post(client), 422, error)

    def test_actual_adapter_request_failure_is_http_503(self):
        with self.client(ArcGISWorldGeocoder()) as client, patch("urllib.request.urlopen", side_effect=TimeoutError()):
            self.assert_failure(self.post(client), 503, "GEOCODER_PROVIDER_REQUEST_FAILED")

    def test_missing_governed_geometry_is_http_503(self):
        (self.root / "data/reference/co/district_geometry_sources_v0.1.json").unlink()
        with self.client() as client:
            self.assert_failure(self.post(client), 503, "GOVERNED_GEOMETRY_SOURCE_REGISTRY_INVALID")

    def test_default_provider_timeout_and_utc_stamp_reach_existing_runtime(self):
        provider = self.provider()
        with patch.object(api, "ArcGISWorldGeocoder", return_value=provider) as factory:
            with patch.object(api, "build_representation_for_address", wraps=api.build_representation_for_address) as runtime:
                with TestClient(api.create_app(repo_root=self.root, timeout_seconds=20)) as client:
                    response = self.post(client)
        self.assertEqual(response.status_code, 200, response.text)
        factory.assert_called_once_with(timeout_seconds=20)
        self.assertEqual(runtime.call_args.kwargs["generated_at"], "2026-10-12T14:10:00Z")
        self.assertEqual(runtime.call_args.kwargs["root"], self.root.resolve())
        self.assertNotIn("policy", runtime.call_args.kwargs)

    def test_unexpected_exception_and_invalid_models_return_complete_failure_json(self):
        with self.client() as client:
            with patch.object(api, "build_representation_for_address", side_effect=RuntimeError("internal details")):
                self.assert_failure(self.post(client), 503, "ADDRESS_API_EXECUTION_FAILED")
            for model in (None, {"status": "UNKNOWN", "canonical_writes": 0},
                    {"status": "PASS", "canonical_writes": False}, {"status": "PASS", "canonical_writes": 1},
                    {"status": "FAIL-CLOSED", "canonical_writes": 0}):
                with self.subTest(model=model), patch.object(api, "build_representation_for_address", return_value=model):
                    self.assert_failure(self.post(client), 503, "ADDRESS_API_RUNTIME_RESULT_INVALID")
            with patch.object(api, "build_representation_for_address", return_value={"status": "PASS", "canonical_writes": 0, "bad": float("nan")}):
                self.assert_failure(self.post(client), 503, "ADDRESS_API_EXECUTION_FAILED")

    def test_get_cannot_supply_lookup_and_documentation_routes_are_absent(self):
        provider = Provider([])
        with self.client(provider) as client:
            self.assertEqual(client.get("/v1/representation?address=A").status_code, 405)
            for path in ("/docs", "/redoc", "/openapi.json"):
                self.assertEqual(client.get(path).status_code, 404)
        self.assertEqual(provider.calls, [])

    def test_launcher_binds_loopback_and_rejects_host_override(self):
        with patch.object(launcher.uvicorn, "run") as server:
            self.assertEqual(launcher.main(["--port", "8123", "--repo-root", str(self.root)]), 0)
        self.assertEqual(server.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(server.call_args.kwargs["port"], 8123)
        self.assertFalse(server.call_args.kwargs["access_log"])
        for args in (["--host", "0.0.0.0"], ["--port", "0"], ["--port", "65536"],
                ["--timeout-seconds", "nan"], ["--timeout-seconds", "0"],
                ["--repo-root", str(self.root / "missing")]):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), patch.object(launcher.uvicorn, "run") as server:
                with self.assertRaises(SystemExit) as exc:
                    launcher.main(args)
                self.assertEqual(exc.exception.code, 2)
                server.assert_not_called()

    def test_timeout_config_rejects_nonfinite_invalid_and_boolean_values(self):
        for timeout in (0, -1, 121, float("nan"), float("inf"), True, "30"):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, "ADDRESS_API_TIMEOUT_INVALID"):
                api.create_app(repo_root=self.root, timeout_seconds=timeout)

    def test_real_loopback_http_request_through_uvicorn(self):
        provider = self.provider()
        app = api.create_app(repo_root=self.root, geocoder=provider)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off"))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        connection = None
        try:
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(server.started)
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("POST", "/v1/representation", json.dumps({"address": self.control["address_input"]}),
                {"Content-Type": "application/json"})
            response = connection.getresponse()
            model = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(model["status"], "PASS")
            self.assertEqual(model["resolved_division_ocdid"], "ocd-division/country:us/state:co/place:alamosa/ward:1")
            self.assertEqual(model["canonical_writes"], 0)
        finally:
            if connection:
                connection.close()
            server.should_exit = True
            thread.join(timeout=5)
            sock.close()
        self.assertFalse(thread.is_alive())
        self.assertEqual(provider.calls, [(self.control["address_input"], 5)])

    def test_http_lookup_does_not_change_governed_data(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.client() as client:
            self.assertEqual(self.post(client).status_code, 200)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
