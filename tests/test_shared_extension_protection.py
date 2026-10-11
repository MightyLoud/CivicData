from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.ev_maui_activation_diff import (
    PROTECTED_EXTENSION_BUNDLES,
    verify_extension_registry_delta,
)

REGISTRY = ROOT / "civic_gps_extensions/registry_bundles.v0.1.json"


class SharedExtensionProtectionTests(unittest.TestCase):
    def registry(self):
        return json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_unrelated_bundle_and_overlay_additions_are_allowed(self):
        old = self.registry()
        new = deepcopy(old)
        new["bundles"].append(
            {
                "adapter_id": "BASE-CO-UNRELATED-TEST",
                "mode": "BASE",
            }
        )
        new.setdefault("governed_local_district_overlays", []).append(
            {
                "overlay_id": "LOCAL-CO-UNRELATED-TEST",
            }
        )
        verify_extension_registry_delta(old, new)

    def test_each_protected_hawaii_bundle_is_immutable(self):
        old = self.registry()
        by_id = {
            row["adapter_id"]: row
            for row in old["bundles"]
            if row.get("adapter_id")
        }
        self.assertTrue(PROTECTED_EXTENSION_BUNDLES.issubset(by_id))

        for bundle_id in sorted(PROTECTED_EXTENSION_BUNDLES):
            with self.subTest(bundle_id=bundle_id):
                new = deepcopy(old)
                target = next(
                    row
                    for row in new["bundles"]
                    if row.get("adapter_id") == bundle_id
                )
                target["priority"] = int(target.get("priority", 0)) + 1
                with self.assertRaisesRegex(
                    ValueError,
                    "Protected Hawaii Civic GPS bundle changed",
                ):
                    verify_extension_registry_delta(old, new)

    def test_removing_protected_bundle_fails_closed(self):
        old = self.registry()
        new = deepcopy(old)
        victim = sorted(PROTECTED_EXTENSION_BUNDLES)[0]
        new["bundles"] = [
            row
            for row in new["bundles"]
            if row.get("adapter_id") != victim
        ]
        with self.assertRaisesRegex(
            ValueError,
            "Protected Hawaii Civic GPS bundle missing",
        ):
            verify_extension_registry_delta(old, new)

    def test_extension_version_change_fails_closed(self):
        old = self.registry()
        new = deepcopy(old)
        new["extension_version"] = "999"
        with self.assertRaisesRegex(
            ValueError,
            "Civic GPS extension version changed",
        ):
            verify_extension_registry_delta(old, new)


if __name__ == "__main__":
    unittest.main(verbosity=2)
