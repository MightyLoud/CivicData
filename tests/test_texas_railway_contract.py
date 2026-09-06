"""Static contract controls for the bounded Texas Railway deployment target."""
from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TexasRailwayContractTests(unittest.TestCase):
    def test_railway_config_uses_exact_hosted_service_contract(self):
        config = tomllib.loads((ROOT / "railway.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["build"]["builder"], "DOCKERFILE")
        self.assertEqual(
            config["build"]["dockerfilePath"],
            "services/texas_bounded_api/Dockerfile",
        )
        self.assertEqual(config["deploy"]["healthcheckPath"], "/readyz")
        self.assertGreaterEqual(config["deploy"]["healthcheckTimeout"], 120)
        self.assertEqual(config["deploy"]["restartPolicyType"], "ON_FAILURE")
        self.assertGreaterEqual(config["deploy"]["restartPolicyMaxRetries"], 3)

    def test_dockerfile_uses_provider_port_and_git_sha_fallback_is_present(self):
        dockerfile = (ROOT / "services/texas_bounded_api/Dockerfile").read_text(encoding="utf-8")
        main = (ROOT / "services/texas_bounded_api/main.py").read_text(encoding="utf-8")
        self.assertIn("${PORT:-8080}", dockerfile)
        self.assertIn("os.environ.get('PORT', '8080')", dockerfile)
        self.assertIn('os.environ.get("RAILWAY_GIT_COMMIT_SHA")', main)
        self.assertIn('os.environ.get("CIVICDATA_SERVICE_HEAD_SHA")', main)


if __name__ == "__main__":
    unittest.main(verbosity=2)
