"""Receipt-bound Maui Mayor/Council representation; publication remains held."""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from consumers.empowered_vote import maui_countywide_candidate as candidate

PROFILE_ID = "maui_countywide_mayor_council_v0.1"
ENTRY_ID = "hi-maui-countywide-representation-v0.1"
SPEC_PATH = Path("onboarding/ev/maui-county.v0.1.json")
RECEIPT_PATH = "acceptance/ev/maui_countywide.v0.1.json"
REVIEW_REFERENCE = {"path": "acceptance/ev/maui_source_review.v0.1.json",
    "sha256": "b85827b4056d70e70ebb8e1e69bb02a60da3009854d5d80840a2edfe00c4b6b2"}
FLAGS = {"candidate_only": False, "production_eligible": True,
         "publication_eligible": False, "complete_jurisdiction": False}
ROUTING = {"strategy": "REUSE_GOVERNED_ROUTE", "adapter_id": "BASE-HI-MAUI-COUNTY", "geoid": "15009",
    "route_sha256": "695d2f3c0b7cb5d84bf4328c0cdc735ad8623101bd66b01032361a56d65359d2",
    "release_path": "civic_gps_extensions/hi_maui_county_release_v0.1.json",
    "release_sha256": "9ae1e0872ee347e0bbbe7a57721ecc67ac39cebc2c2d4b29cf06c04c8d3fe781"}
ADDRESSES = ["200 South High Street, Wailuku, HI 96793", "814 Fraser Avenue, Lanai City, HI 96763"]
NEGATIVE = {"address": "25 Aupuni Street, Hilo, HI 96720",
            "expected_civic_jurisdiction_id": "jur-us-hi-hawaii-county"}
EXPECTED = {"office_rows": 10, "current_holders": 10, "address_controls": 2,
            "qa_fail_count": 0, "blocking_gap_count": 0, "parity_ok": True}


class MauiProductionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(ok, code):
    if not ok:
        raise MauiProductionError(code)


def digest(value):
    return hashlib.sha256(candidate.preview.package_source.canonical_json_bytes(value)).hexdigest()


def candidate_entry(entry):
    result = copy.deepcopy(entry)
    result.pop("countywide_profile", None)
    result.update(candidate.FLAGS)
    result["entry_id"] = candidate.ENTRY_ID
    result["countywide_binding"]["binding_id"] = candidate.ENTRY_ID
    result["countywide_binding"]["mode"] = "MAUI_COUNTYWIDE_RESIDENCY_CANDIDATE"
    return result


def validate_entry(entry):
    require(isinstance(entry, dict) and entry.get("entry_id") == ENTRY_ID, "MAUI_PRODUCTION_ENTRY_INVALID")
    require(all(entry.get(k) is v for k, v in FLAGS.items()), "MAUI_PRODUCTION_FLAGS_INVALID")
    binding = entry.get("countywide_binding")
    require(isinstance(binding, dict) and binding.get("binding_id") == ENTRY_ID
        and binding.get("mode") == "MAUI_COUNTYWIDE_RESIDENCY_REPRESENTATION", "MAUI_PRODUCTION_BINDING_INVALID")
    profile = entry.get("countywide_profile")
    require(isinstance(profile, dict) and set(profile) == {"profile_id", "acceptance_receipt"}
        and profile.get("profile_id") == PROFILE_ID, "MAUI_PRODUCTION_PROFILE_INVALID")
    reference = profile.get("acceptance_receipt")
    require(isinstance(reference, dict) and set(reference) == {"path", "sha256"}
        and reference.get("path") == RECEIPT_PATH
        and re.fullmatch(r"[a-f0-9]{64}", str(reference.get("sha256"))) is not None,
        "MAUI_PRODUCTION_RECEIPT_REFERENCE_INVALID")
    try:
        candidate.validate_entry(candidate_entry(entry))
    except (candidate.MauiCandidateError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise MauiProductionError("MAUI_PRODUCTION_CONTRACT_INVALID") from exc


def read_bound(root, reference, code):
    path = (root / reference["path"]).resolve()
    require(path.is_relative_to(root.resolve()), code + "_PATH_INVALID")
    try:
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == reference["sha256"], code + "_HASH_DRIFT")
        result = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise MauiProductionError(code + "_UNAVAILABLE") from exc
    require(isinstance(result, dict), code + "_INVALID")
    return result


def load_receipt(entry, root, *, today=None):
    validate_entry(entry)
    receipt = read_bound(root, entry["countywide_profile"]["acceptance_receipt"], "MAUI_PRODUCTION_RECEIPT")
    require(receipt.get("receipt_schema") == "maui-countywide-acceptance/0.1"
        and receipt.get("status") == "PASS" and receipt.get("profile_id") == PROFILE_ID
        and receipt.get("scope") == candidate.SCOPE
        and receipt.get("archive_sha256") == candidate.ARTIFACT["archive_sha256"]
        and receipt.get("package_sha256") == candidate.PACKAGE_SHA256
        and receipt.get("binding_sha256") == digest(entry["countywide_binding"])
        and receipt.get("source_review") == REVIEW_REFERENCE
        and receipt.get("source_correction") == candidate.SOURCE_CORRECTION
        and receipt.get("publication_authorized") is False
        and receipt.get("deployment_authorized") is False
        and receipt.get("complete_jurisdiction") is False
        and receipt.get("routing") == ROUTING
        and receipt.get("positive_addresses") == ADDRESSES and receipt.get("negative_control") == NEGATIVE
        and receipt.get("onboarding_expected") == EXPECTED, "MAUI_PRODUCTION_RECEIPT_CONTRACT_INVALID")
    review = read_bound(root, REVIEW_REFERENCE, "MAUI_PRODUCTION_SOURCE_REVIEW")
    require(review.get("review_schema") == "maui-activation-source-review/0.1"
        and review.get("reviewed_on") == "2026-09-12" and review.get("expires_on") == "2026-10-12"
        and review.get("scope") == candidate.SCOPE and review.get("package_sha256") == candidate.PACKAGE_SHA256,
        "MAUI_PRODUCTION_SOURCE_REVIEW_INVALID")
    current = datetime.now(timezone.utc).date() if today is None else today
    require(date(2026, 9, 12) <= current < date(2026, 10, 12), "MAUI_PRODUCTION_SOURCE_REVIEW_EXPIRED_OR_FUTURE")
    observations, assertions = review["source_observations"], review["normalized_assertions"]
    ids = {row["source_id"] for row in observations}
    require(len(observations) == len(ids) == 13 and len(assertions) == 25
        and all(row["authority"] == "PRIMARY_OFFICIAL" and row["http_status"] == 200
            and row["reviewed_on"] == review["reviewed_on"]
            and hashlib.sha256(row["raw_excerpt"].encode()).hexdigest() == row["raw_excerpt_sha256"]
            for row in observations)
        and all(row["status"] == "NORMALIZED" and row["confidence"] == "HIGH"
            and row["source_ids"] and set(row["source_ids"]) <= ids for row in assertions)
        and review.get("qa") == {"status": "PASS", "raw_count": 13, "normalized_count": 25,
            "holder_parity": 10, "residency_parity": 9, "leadership_parity": 2,
            "source_joins_valid": True, "parity_ok": True, "blocking_gap_count": 0},
        "MAUI_PRODUCTION_SOURCE_PARITY_INVALID")
    read_bound(root, candidate.SOURCE_CORRECTION, "MAUI_PRODUCTION_SOURCE_CORRECTION")
    return receipt


def existing_route(root, receipt):
    require(receipt.get("profile_id") == PROFILE_ID and receipt.get("routing") == ROUTING,
            "MAUI_PRODUCTION_ROUTE_REFERENCE_INVALID")
    try:
        registry = json.loads((root / "civic_gps_extensions/registry_bundles.v0.1.json").read_text())
        matches = [row for row in registry["bundles"] if row.get("adapter_id") == ROUTING["adapter_id"]]
        require(len(matches) == 1, "MAUI_PRODUCTION_ROUTE_AMBIGUOUS_OR_MISSING")
        route = matches[0]
        require(digest(route) == ROUTING["route_sha256"] and route.get("ev_onboarding_status") == "ROUTING_ONLY",
                "MAUI_PRODUCTION_ROUTE_DRIFT")
        raw = (root / ROUTING["release_path"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == ROUTING["release_sha256"], "MAUI_PRODUCTION_RELEASE_DRIFT")
        payload = json.loads(raw)["payload"]
        require(payload["offices"] == [] and payload["officeholders"] == []
            and [r["jurisdiction_id"] for r in payload["jurisdictions"]] == [candidate.preview.CIVIC_ID],
            "MAUI_PRODUCTION_ROUTING_FACTS_INVALID")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MauiProductionError("MAUI_PRODUCTION_ROUTE_INVALID") from exc
    return copy.deepcopy(route)


def spec_contract(spec, entry, receipt):
    from tools.ev_jurisdiction_onboarding import build_catalog_entry
    require(isinstance(spec, dict) and build_catalog_entry(spec) == entry
        and spec.get("spec_version") == "0.1" and spec.get("routing") == receipt["routing"]
        and spec.get("live_addresses") == receipt["positive_addresses"]
        and spec.get("expected") == receipt["onboarding_expected"], "MAUI_PRODUCTION_SPEC_DRIFT")


def validate_package(entry, root, package):
    receipt = load_receipt(entry, root)
    require(digest(package) == candidate.PACKAGE_SHA256, "MAUI_PRODUCTION_PACKAGE_DRIFT")
    existing_route(root, receipt)
    try:
        spec = json.loads((root / SPEC_PATH).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise MauiProductionError("MAUI_PRODUCTION_SPEC_UNAVAILABLE") from exc
    spec_contract(spec, entry, receipt)
    return receipt


def build_representation(package, address, geographic, entry, root):
    try:
        validate_package(entry, root, package)
        result = candidate.build_representation(package, address, geographic, candidate_entry(entry))
        if result.get("status") == "PASS":
            result.pop("candidate_gate", None)
            result.update(FLAGS)
            result.update({"preview_only": False, "production_profile_id": PROFILE_ID,
                "package_catalog_entry_id": ENTRY_ID, "source_reviewed_on": "2026-09-12",
                "source_review_expires_on": "2026-10-12",
                "acceptance_receipt_sha256": entry["countywide_profile"]["acceptance_receipt"]["sha256"]})
    except MauiProductionError as exc:
        result = {"status": "FAIL-CLOSED", "error": exc.code, "canonical_writes": 0,
            "production_eligible": False, "publication_eligible": False, "complete_jurisdiction": False}
    except (KeyError, TypeError, ValueError, AttributeError):
        result = {"status": "FAIL-CLOSED", "error": "MAUI_PRODUCTION_INPUT_INVALID", "canonical_writes": 0,
            "production_eligible": False, "publication_eligible": False, "complete_jurisdiction": False}
    result.pop("deterministic_sha256", None)
    result["deterministic_sha256"] = digest(result)
    return result


def validate_spec(spec, root):
    from consumers.empowered_vote import package_catalog
    from tools.ev_jurisdiction_onboarding import build_catalog_entry
    entry = build_catalog_entry(spec)
    validate_entry(entry)
    package = package_catalog.reconstruct_package(entry, root)
    receipt = validate_package(entry, root, package)
    spec_contract(spec, entry, receipt)
    return receipt


def installed_spec(root):
    from consumers.empowered_vote import package_catalog
    from tools.ev_jurisdiction_onboarding import build_catalog_entry
    path = root / SPEC_PATH
    catalog_path = root / "consumers/empowered_vote/package_catalog.v0.1.json"
    if not path.exists() and not catalog_path.exists():
        return None
    catalog = package_catalog.load_catalog(catalog_path)
    rows = [r for r in catalog["entries"] if r.get("package_jurisdiction_id") == candidate.preview.PACKAGE_ID]
    if not rows and not path.exists():
        return None
    require(len(rows) == 1 and path.is_file(), "MAUI_PRODUCTION_INSTALLATION_INCOMPLETE")
    spec = json.loads(path.read_text())
    validate_spec(spec, root)
    require(rows[0] == build_catalog_entry(spec), "MAUI_PRODUCTION_CATALOG_SPEC_DRIFT")
    return spec
