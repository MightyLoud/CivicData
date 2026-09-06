"""Governed hosted runtime for the bounded Texas legislative representation service."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from civic_gps_extensions.loader import load_resolver_with_extensions
from civic_gps_extensions.texas_legislative import build_texas_production_configuration
from consumers.empowered_vote import package_catalog, production_profile, representation_catalog
from tools.jurisdiction_package import canonical_json

SERVICE_DIR = Path(__file__).resolve().parent
DEFAULT_CONTRACT = SERVICE_DIR / "service_contract.v0.1.json"
DATA_REL = Path("data/packages/tx/legislative")
META_NAME = "successor-package-metadata-v0.1.json"
RECEIPT_NAME = "acceptance-v0.1.json"
DEFAULT_EXTENSION_REL = Path("civic_gps_extensions/registry_bundles.v0.1.json")


class HostedRuntimeError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


def _require(condition: bool, code: str, detail: str | None = None) -> None:
    if not condition:
        raise HostedRuntimeError(code, detail)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_json(value: Any) -> str:
    return _sha_bytes(canonical_json(value).encode("utf-8"))


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostedRuntimeError(code, str(exc)) from exc
    _require(isinstance(value, dict), code, "expected JSON object")
    return value


def _identity_status(person: dict[str, Any]) -> str:
    value = person.get("person_status") or person.get("identity_resolution_status")
    return str(value or "").strip().upper()


def _default_routes_inactive(repo_root: Path, jurisdiction_id: str) -> None:
    catalog = package_catalog.load_catalog(repo_root / "consumers/empowered_vote/package_catalog.v0.1.json")
    for row in catalog["entries"]:
        if row.get("package_jurisdiction_id") == jurisdiction_id and (
            row.get("profile") == "state_legislative_representation"
            or (row.get("production_profile") or {}).get("profile_id") == production_profile.PROFILE_ID
        ):
            raise HostedRuntimeError("HOSTED_RUNTIME_DEFAULT_CATALOG_ALREADY_ACTIVE")

    extension = _read_json(repo_root / DEFAULT_EXTENSION_REL, "HOSTED_RUNTIME_DEFAULT_EXTENSION_INVALID")
    expected_adapters = {"DIST-TX-HOUSE-H2316", "DIST-TX-SENATE-S2168"}
    for group in extension.get("legislative_boundary_overlays", []):
        if not isinstance(group, dict):
            continue
        adapters = {
            str(row.get("adapter_id"))
            for row in group.get("district_adapters", [])
            if isinstance(row, dict)
        }
        if group.get("group_id") == "GEO-TX-LEGISLATIVE-TWO-DISTRICTS" or adapters & expected_adapters:
            raise HostedRuntimeError("HOSTED_RUNTIME_DEFAULT_REGISTRY_ALREADY_ACTIVE")


class TexasBoundedRuntime:
    """One exact successor package + production-bounded resolver instance."""

    def __init__(
        self,
        *,
        repo_root: Path,
        head_sha: str,
        environment: str,
        contract: dict[str, Any],
        contract_sha256: str,
        meta: dict[str, Any],
        receipt: dict[str, Any],
        package: dict[str, Any],
        resolver: Any,
        catalog_temp: tempfile.TemporaryDirectory[str],
        catalog_path: Path,
        group: dict[str, Any],
    ):
        self.repo_root = repo_root
        self.head_sha = head_sha
        self.environment = environment
        self.contract = contract
        self.contract_sha256 = contract_sha256
        self.meta = meta
        self.receipt = receipt
        self.package = package
        self.resolver = resolver
        self._catalog_temp = catalog_temp
        self.catalog_path = catalog_path
        self.group = group

    @classmethod
    def build(
        cls,
        repo_root: str | Path,
        *,
        head_sha: str,
        environment: str,
        contract_path: str | Path = DEFAULT_CONTRACT,
        session: Any = None,
        timeout_seconds: float = 30.0,
    ) -> "TexasBoundedRuntime":
        root = Path(repo_root).resolve()
        head = str(head_sha).strip().lower()
        env = str(environment).strip().lower()
        _require(re.fullmatch(r"[a-f0-9]{40}", head) is not None, "HOSTED_RUNTIME_HEAD_SHA_INVALID")
        _require(bool(env), "HOSTED_RUNTIME_ENVIRONMENT_REQUIRED")

        contract_file = Path(contract_path)
        contract = _read_json(contract_file, "HOSTED_RUNTIME_CONTRACT_INVALID")
        _require(contract.get("schema_version") == "texas-hosted-runtime-service/0.1",
                 "HOSTED_RUNTIME_CONTRACT_VERSION_UNSUPPORTED")
        _require(contract.get("profile_id") == production_profile.PROFILE_ID,
                 "HOSTED_RUNTIME_PROFILE_DRIFT")
        _require(contract.get("repository_activation") == "NOT_ACTIVATED"
                 and contract.get("activation_authorized") is False
                 and contract.get("canonical_writes") == 0,
                 "HOSTED_RUNTIME_ACTIVATION_BOUNDARY_INVALID")

        data = root / DATA_REL
        meta_path = data / META_NAME
        receipt_path = data / RECEIPT_NAME
        meta = _read_json(meta_path, "HOSTED_RUNTIME_METADATA_INVALID")
        receipt = _read_json(receipt_path, "HOSTED_RUNTIME_RECEIPT_INVALID")
        expected = contract.get("expected")
        _require(isinstance(expected, dict), "HOSTED_RUNTIME_EXPECTED_PINS_INVALID")
        for key in (
            "jurisdiction_json_sha256",
            "archive_sha256",
            "acceptance_receipt_sha256",
            "acceptance_deterministic_sha256",
            "runtime_zip_sha256",
        ):
            _require(expected.get(key) == meta.get(key) or (
                key == "runtime_zip_sha256" and expected.get(key) == receipt.get("inputs", {}).get(key)
            ), "HOSTED_RUNTIME_PIN_DRIFT", key)
        _require(_sha_bytes(receipt_path.read_bytes()) == expected["acceptance_receipt_sha256"],
                 "HOSTED_RUNTIME_RECEIPT_FILE_HASH_DRIFT")
        _require(receipt.get("deterministic_sha256") == expected["acceptance_deterministic_sha256"],
                 "HOSTED_RUNTIME_RECEIPT_DIGEST_DRIFT")

        entry = contract.get("catalog_entry")
        _require(isinstance(entry, dict), "HOSTED_RUNTIME_CATALOG_ENTRY_INVALID")
        _require(entry.get("artifact", {}).get("archive_sha256") == expected["archive_sha256"],
                 "HOSTED_RUNTIME_ARCHIVE_PIN_DRIFT")
        _require(entry.get("production_profile", {}).get("acceptance_receipt", {}).get("sha256")
                 == expected["acceptance_receipt_sha256"],
                 "HOSTED_RUNTIME_ACCEPTANCE_POINTER_DRIFT")

        catalog_temp = tempfile.TemporaryDirectory(prefix="civicdata-tx-hosted-")
        catalog_path = Path(catalog_temp.name) / "catalog.json"
        catalog_path.write_text(canonical_json({"catalog_version": "0.1", "entries": [entry]}), encoding="utf-8")
        try:
            catalog = package_catalog.load_catalog(catalog_path)
            package = package_catalog.reconstruct_package(catalog["entries"][0], root)
        except Exception:
            catalog_temp.cleanup()
            raise

        package_sha = _sha_json(package)
        _require(package_sha == expected["jurisdiction_json_sha256"],
                 "HOSTED_RUNTIME_PACKAGE_HASH_DRIFT", package_sha)
        identity = {
            str(row.get("person_id") or row.get("id")): _identity_status(row)
            for row in package["records"]["people"]
        }
        _require(identity == receipt.get("person_identity_status") and set(identity.values()) == {"AUTHORITATIVE"},
                 "HOSTED_RUNTIME_PUBLIC_IDENTITY_INVALID")

        divisions = {row.get("division_kind"): row.get("division_id") for row in package["records"]["divisions"]}
        _require(isinstance(divisions.get("SLDL"), str) and isinstance(divisions.get("SLDU"), str),
                 "HOSTED_RUNTIME_DIVISION_SCOPE_INVALID")
        groups, bindings = build_texas_production_configuration(
            package,
            house_division_id=divisions["SLDL"],
            senate_division_id=divisions["SLDU"],
        )
        _require(bindings == receipt.get("scope", {}).get("bindings"),
                 "HOSTED_RUNTIME_BINDING_DRIFT")
        _default_routes_inactive(root, package["jurisdiction"]["jurisdiction_id"])

        try:
            resolver = load_resolver_with_extensions(
                root,
                legislative_overlays=groups,
                session=session,
                timeout_seconds=timeout_seconds,
            )
        except Exception:
            catalog_temp.cleanup()
            raise

        return cls(
            repo_root=root,
            head_sha=head,
            environment=env,
            contract=contract,
            contract_sha256=_sha_bytes(contract_file.read_bytes()),
            meta=meta,
            receipt=receipt,
            package=package,
            resolver=resolver,
            catalog_temp=catalog_temp,
            catalog_path=catalog_path,
            group=groups[0],
        )

    def close(self) -> None:
        self._catalog_temp.cleanup()

    def service_metadata(self) -> dict[str, Any]:
        return {
            "service_id": self.contract["service_id"],
            "schema_version": self.contract["schema_version"],
            "environment": self.environment,
            "head_sha": self.head_sha,
            "profile_id": production_profile.PROFILE_ID,
            "service_contract_sha256": self.contract_sha256,
            "jurisdiction_json_sha256": self.meta["jurisdiction_json_sha256"],
            "archive_sha256": self.meta["archive_sha256"],
            "acceptance_receipt_sha256": self.meta["acceptance_receipt_sha256"],
            "acceptance_deterministic_sha256": self.receipt["deterministic_sha256"],
            "runtime_zip_sha256": self.receipt["inputs"]["runtime_zip_sha256"],
            "production_group_sha256": _sha_json(self.group),
            "repository_activation": "NOT_ACTIVATED",
            "activation_authorized": False,
            "canonical_writes": 0,
        }

    def readiness(self) -> dict[str, Any]:
        return {
            "status": "PASS",
            "checks": {
                "package-profile-reconstruction": "PASS",
                "public-identity-gate": "PASS",
                "geometry-governance-preflight": "PASS",
                "default-catalog-inactive": "PASS",
                "default-registry-inactive": "PASS",
            },
            "service": self.service_metadata(),
        }

    def represent(self, address: str) -> dict[str, Any]:
        value = str(address).strip()
        _require(bool(value), "HOSTED_RUNTIME_ADDRESS_REQUIRED")
        try:
            geography = self.resolver.resolve(value, observed_on=None)
            result = representation_catalog.build_representation_from_catalog(
                value,
                geography,
                repo_root=self.repo_root,
                catalog_path=self.catalog_path,
                profile="state_legislative_representation",
            )
        except Exception as exc:
            result = {
                "status": "FAIL-CLOSED",
                "consumer_gate": "EV-IMP-005",
                "input_address": value,
                "error": "HOSTED_RUNTIME_RESOLUTION_EXCEPTION",
                "detail": str(exc),
                "canonical_writes": 0,
            }
        return {
            "service": self.service_metadata(),
            "result": result,
        }
