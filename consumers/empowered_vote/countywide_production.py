"""Receipt-bound Kauaʻi Mayor/Council production representation; publication held."""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from consumers.empowered_vote import countywide_candidate as candidate

PROFILE_ID = "kauai_countywide_mayor_council_v0.1"
ENTRY_ID = "hi-kauai-countywide-representation-v0.1"
SPEC_PATH = Path("onboarding/ev/kauai-county.v0.1.json")
RECEIPT_PATH = "acceptance/ev/kauai_countywide.v0.1.json"
FLAGS = {"candidate_only": False, "production_eligible": True,
         "publication_eligible": False, "complete_jurisdiction": False}


class CountywideProductionError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(ok: bool, code: str) -> None:
    if not ok:
        raise CountywideProductionError(code)


def digest(value: Any) -> str:
    return hashlib.sha256(candidate.preview.package_source.canonical_json_bytes(value)).hexdigest()


def candidate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(entry)
    value.pop("countywide_profile", None)
    value.update(candidate.FLAGS)
    value["entry_id"] = candidate.ENTRY_ID
    binding = value["countywide_binding"]
    binding["binding_id"] = candidate.ENTRY_ID
    binding["mode"] = "COUNTYWIDE_CANDIDATE"
    return value


def validate_entry(entry: dict[str, Any]) -> None:
    require(isinstance(entry, dict) and entry.get("entry_id") == ENTRY_ID,
            "COUNTYWIDE_PRODUCTION_ENTRY_INVALID")
    require(all(entry.get(k) is v for k, v in FLAGS.items()), "COUNTYWIDE_PRODUCTION_FLAGS_INVALID")
    binding = entry.get("countywide_binding")
    require(isinstance(binding, dict) and binding.get("binding_id") == ENTRY_ID
            and binding.get("mode") == "COUNTYWIDE_REPRESENTATION", "COUNTYWIDE_PRODUCTION_BINDING_INVALID")
    profile = entry.get("countywide_profile")
    require(isinstance(profile, dict) and set(profile) == {"profile_id", "acceptance_receipt"}
            and profile.get("profile_id") == PROFILE_ID, "COUNTYWIDE_PRODUCTION_PROFILE_INVALID")
    receipt = profile.get("acceptance_receipt")
    require(isinstance(receipt, dict) and set(receipt) == {"path", "sha256"}
            and receipt.get("path") == RECEIPT_PATH
            and re.fullmatch(r"[a-f0-9]{64}", str(receipt.get("sha256"))) is not None,
            "COUNTYWIDE_PRODUCTION_RECEIPT_REFERENCE_INVALID")
    try:
        candidate.validate_entry(candidate_entry(entry))
    except (candidate.CountywideCandidateError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CountywideProductionError("COUNTYWIDE_PRODUCTION_CONTRACT_INVALID") from exc


def load_receipt(entry: dict[str, Any], root: Path, *, today: date | None = None) -> dict[str, Any]:
    validate_entry(entry)
    reference = entry["countywide_profile"]["acceptance_receipt"]
    path = (root / reference["path"]).resolve()
    require(path.is_relative_to(root.resolve()), "COUNTYWIDE_PRODUCTION_RECEIPT_PATH_INVALID")
    try:
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == reference["sha256"], "COUNTYWIDE_PRODUCTION_RECEIPT_HASH_DRIFT")
        receipt = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CountywideProductionError("COUNTYWIDE_PRODUCTION_RECEIPT_UNAVAILABLE") from exc
    require(isinstance(receipt, dict) and receipt.get("receipt_schema") == "kauai-countywide-acceptance/0.1"
            and receipt.get("status") == "PASS" and receipt.get("profile_id") == PROFILE_ID
            and receipt.get("scope") == candidate.SCOPE
            and receipt.get("archive_sha256") == candidate.ARCHIVE_SHA256
            and receipt.get("binding_sha256") == digest(entry["countywide_binding"])
            and receipt.get("publication_authorized") is False
            and receipt.get("deployment_authorized") is False
            and receipt.get("complete_jurisdiction") is False,
            "COUNTYWIDE_PRODUCTION_RECEIPT_CONTRACT_INVALID")
    review = receipt.get("source_review", {})
    try:
        reviewed = date.fromisoformat(review["reviewed_on"])
        expires = date.fromisoformat(review["expires_on"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CountywideProductionError("COUNTYWIDE_PRODUCTION_REVIEW_DATES_INVALID") from exc
    current = datetime.now(timezone.utc).date() if today is None else today
    require(reviewed <= current < expires and 0 < (expires-reviewed).days <= 90
            and expires <= date(2026, 12, 1), "COUNTYWIDE_PRODUCTION_SOURCE_REVIEW_EXPIRED_OR_FUTURE")
    require(review.get("identity_policy") == "PRESERVE_LEGACY_ACTIVE_REJECT_EXPLICIT_PROVISIONAL"
            and review.get("tenure_policy") == "PRESERVE_UNRESOLVED_INTERVALS"
            and review.get("known_omitted_offices") == ["Prosecuting Attorney"]
            and review.get("roster_matches_package") is True
            and review.get("leadership_matches_package") is True
            and isinstance(review.get("sources"), list) and len(review["sources"]) >= 4
            and all(isinstance(row, dict) and row.get("authority") == "PRIMARY_OFFICIAL"
                    and row.get("reviewed_on") == review["reviewed_on"]
                    and str(row.get("url", "")).startswith(("https://elections.hawaii.gov/", "https://www.kauai.gov/"))
                    for row in review["sources"]), "COUNTYWIDE_PRODUCTION_SOURCE_REVIEW_INVALID")
    require(receipt.get("positive_addresses") == ["4444 Rice Street, Lihue, HI 96766", "4396 Rice Street, Lihue, HI 96766"]
            and receipt.get("negative_control") == {"address": "25 Aupuni Street, Hilo, HI 96720",
                "expected_civic_jurisdiction_id": "jur-us-hi-hawaii-county"}, "COUNTYWIDE_PRODUCTION_CONTROLS_INVALID")
    require(receipt.get("onboarding_expected") == {"office_rows": 2, "current_holders": 8,
            "address_controls": 2, "qa_fail_count": 0, "blocking_gap_count": 0, "parity_ok": True},
            "COUNTYWIDE_PRODUCTION_EXPECTED_COUNTS_INVALID")
    return receipt


def existing_route(root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    reference = receipt.get("routing")
    require(isinstance(reference, dict), "COUNTYWIDE_PRODUCTION_ROUTE_REFERENCE_INVALID")
    require(reference.get("strategy") == "REUSE_GOVERNED_ROUTE"
            and reference.get("adapter_id") == "BASE-HI-KAUAI-COUNTY"
            and reference.get("geoid") == "15007"
            and reference.get("release_path") == "civic_gps_extensions/hi_kauai_county_release_v0.1.json",
            "COUNTYWIDE_PRODUCTION_ROUTE_REFERENCE_INVALID")
    try:
        registry = json.loads((root / "civic_gps_extensions/registry_bundles.v0.1.json").read_text())
        matches = [row for row in registry["bundles"] if row.get("adapter_id") == reference["adapter_id"]]
        require(len(matches) == 1, "COUNTYWIDE_PRODUCTION_ROUTE_AMBIGUOUS_OR_MISSING")
        route = matches[0]
        require(digest(route) == reference.get("route_sha256") and route.get("ev_onboarding_status") == "ROUTING_ONLY"
                and route.get("scope_match") == {"all": [
                    {"geography": "state", "fields": ["GEOID", "STATE"], "equals": "15"},
                    {"geography": "county", "fields": ["GEOID"], "equals": "15007"}]}
                and route.get("release_files") == ["../" + reference["release_path"]],
                "COUNTYWIDE_PRODUCTION_ROUTE_DRIFT")
        raw = (root / reference["release_path"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == reference.get("release_sha256"), "COUNTYWIDE_PRODUCTION_RELEASE_DRIFT")
        payload = json.loads(raw)["payload"]
        require(payload["offices"] == [] and payload["officeholders"] == [], "COUNTYWIDE_PRODUCTION_ROUTING_FACTS_INVALID")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CountywideProductionError("COUNTYWIDE_PRODUCTION_ROUTE_INVALID") from exc
    return copy.deepcopy(route)


def validate_package(entry: dict[str, Any], root: Path, package: dict[str, Any]) -> dict[str, Any]:
    receipt = load_receipt(entry, root)
    require(digest(package) == receipt.get("package_sha256"), "COUNTYWIDE_PRODUCTION_PACKAGE_DRIFT")
    existing_route(root, receipt)
    return receipt


def build_representation(package: dict[str, Any], address: str, geographic: Any,
                         entry: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        receipt = validate_package(entry, root, package)
        result = candidate.build_representation(package, address, geographic, candidate_entry(entry))
        if result.get("status") == "PASS":
            result.pop("candidate_gate", None)
            result.update(FLAGS)
            result.update({"preview_only": False, "production_profile_id": PROFILE_ID,
                           "package_catalog_entry_id": ENTRY_ID,
                           "source_reviewed_on": receipt["source_review"]["reviewed_on"],
                           "source_review_expires_on": receipt["source_review"]["expires_on"],
                           "acceptance_receipt_sha256": entry["countywide_profile"]["acceptance_receipt"]["sha256"]})
    except CountywideProductionError as exc:
        result = {"status": "FAIL-CLOSED", "error": exc.code, "canonical_writes": 0,
                  "publication_eligible": False, "production_eligible": False, "complete_jurisdiction": False}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        result = {"status": "FAIL-CLOSED", "error": "COUNTYWIDE_PRODUCTION_INPUT_INVALID", "canonical_writes": 0,
                  "publication_eligible": False, "production_eligible": False, "complete_jurisdiction": False}
    result.pop("deterministic_sha256", None)
    result["deterministic_sha256"] = digest(result)
    return result


def validate_spec(spec: dict[str, Any], root: Path) -> dict[str, Any]:
    # Lazy import keeps the package loader independent of onboarding initialization.
    from consumers.empowered_vote import package_catalog
    from tools.ev_jurisdiction_onboarding import build_catalog_entry
    entry = build_catalog_entry(spec)
    validate_entry(entry)
    package = package_catalog.reconstruct_package(entry, root)
    receipt = validate_package(entry, root, package)
    require(spec.get("spec_version") == "0.1" and spec.get("routing") == receipt["routing"]
            and spec.get("live_addresses") == receipt["positive_addresses"]
            and spec.get("expected") == receipt["onboarding_expected"], "COUNTYWIDE_PRODUCTION_SPEC_DRIFT")
    return receipt


def installed_spec(root: Path) -> dict[str, Any] | None:
    """Recognize only an explicit, valid catalog/spec pair; never auto-promote a route."""
    from consumers.empowered_vote import package_catalog
    from tools.ev_jurisdiction_onboarding import build_catalog_entry
    catalog = package_catalog.load_catalog(root / "consumers/empowered_vote/package_catalog.v0.1.json")
    rows = [row for row in catalog["entries"] if row.get("package_jurisdiction_id") == candidate.preview.PACKAGE_ID]
    path = root / SPEC_PATH
    if not rows and not path.exists():
        return None
    require(len(rows) == 1 and path.is_file(), "COUNTYWIDE_PRODUCTION_INSTALLATION_INCOMPLETE")
    spec = json.loads(path.read_text())
    validate_spec(spec, root)
    require(rows[0] == build_catalog_entry(spec), "COUNTYWIDE_PRODUCTION_CATALOG_SPEC_DRIFT")
    return spec
