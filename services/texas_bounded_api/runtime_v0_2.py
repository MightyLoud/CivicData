"""Governed post-activation runtime for bounded Texas legislative representation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from civic_gps_extensions.loader import load_resolver_with_extensions
from civic_gps_extensions.texas_legislative import build_texas_production_configuration
from consumers.empowered_vote import package_catalog, production_profile, representation_catalog
from tools.jurisdiction_package import canonical_json

SERVICE_DIR = Path(__file__).resolve().parent
DEFAULT_CONTRACT = SERVICE_DIR / "service_contract.v0.2.json"
DEFAULT_CATALOG_REL = Path("consumers/empowered_vote/package_catalog.v0.1.json")
DEFAULT_EXTENSION_REL = Path("civic_gps_extensions/registry_bundles.v0.1.json")
DATA_REL = Path("data/packages/tx/legislative")
META_NAME = "successor-package-metadata-v0.1.json"
RECEIPT_NAME = "acceptance-v0.1.json"
ACTIVATION_NAME = "activation-v0.1.json"
GROUP_ID = "GEO-TX-LEGISLATIVE-TWO-DISTRICTS"


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


def _active_entry(catalog: dict[str, Any]) -> dict[str, Any]:
    matches = [
        row for row in catalog.get("entries", [])
        if isinstance(row, dict)
        and row.get("profile") == "state_legislative_representation"
        and (row.get("production_profile") or {}).get("profile_id") == production_profile.PROFILE_ID
    ]
    _require(len(matches) == 1, "HOSTED_RUNTIME_ACTIVATED_CATALOG_CARDINALITY_INVALID", str(len(matches)))
    return matches[0]


def _active_group(extension: dict[str, Any]) -> dict[str, Any]:
    matches = [
        row for row in extension.get("legislative_boundary_overlays", [])
        if isinstance(row, dict) and row.get("group_id") == GROUP_ID
    ]
    _require(len(matches) == 1, "HOSTED_RUNTIME_ACTIVATED_REGISTRY_CARDINALITY_INVALID", str(len(matches)))
    return matches[0]


class TexasBoundedRuntimeV02:
    """Exact activated default catalog + registry route with bounded Texas scope."""

    def __init__(
        self,
        *,
        repo_root: Path,
        head_sha: str,
        environment: str,
        contract: dict[str, Any],
        contract_sha256: str,
        meta: dict[str, Any],
        acceptance: dict[str, Any],
        activation: dict[str, Any],
        package: dict[str, Any],
        catalog_entry: dict[str, Any],
        legislative_group: dict[str, Any],
        resolver: Any,
    ):
        self.repo_root = repo_root
        self.head_sha = head_sha
        self.environment = environment
        self.contract = contract
        self.contract_sha256 = contract_sha256
        self.meta = meta
        self.acceptance = acceptance
        self.activation = activation
        self.package = package
        self.catalog_entry = catalog_entry
        self.legislative_group = legislative_group
        self.resolver = resolver

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
    ) -> "TexasBoundedRuntimeV02":
        root = Path(repo_root).resolve()
        head = str(head_sha).strip().lower()
        env = str(environment).strip().lower()
        _require(re.fullmatch(r"[a-f0-9]{40}", head) is not None, "HOSTED_RUNTIME_HEAD_SHA_INVALID")
        _require(bool(env), "HOSTED_RUNTIME_ENVIRONMENT_REQUIRED")

        contract_file = Path(contract_path)
        contract = _read_json(contract_file, "HOSTED_RUNTIME_CONTRACT_INVALID")
        _require(contract.get("schema_version") == "texas-hosted-runtime-service/0.2",
                 "HOSTED_RUNTIME_CONTRACT_VERSION_UNSUPPORTED")
        _require(contract.get("profile_id") == production_profile.PROFILE_ID,
                 "HOSTED_RUNTIME_PROFILE_DRIFT")
        _require(contract.get("repository_activation") == "ACTIVATED_BOUNDED"
                 and contract.get("activation_authorized") is True
                 and contract.get("release_authorized") is False
                 and contract.get("publication_workflow_authorized") is False
                 and contract.get("canonical_writes") == 0,
                 "HOSTED_RUNTIME_ACTIVATION_BOUNDARY_INVALID")
        expected = contract.get("expected")
        _require(isinstance(expected, dict), "HOSTED_RUNTIME_EXPECTED_PINS_INVALID")

        data = root / DATA_REL
        meta = _read_json(data / META_NAME, "HOSTED_RUNTIME_METADATA_INVALID")
        acceptance = _read_json(data / RECEIPT_NAME, "HOSTED_RUNTIME_ACCEPTANCE_INVALID")
        activation = _read_json(data / ACTIVATION_NAME, "HOSTED_RUNTIME_ACTIVATION_RECEIPT_INVALID")
        _require(activation.get("status") == "ACTIVATED_BOUNDED"
                 and activation.get("repository_activation") == "ACTIVATED_BOUNDED"
                 and activation.get("activation_authorized") is True,
                 "HOSTED_RUNTIME_ACTIVATION_RECEIPT_STATE_INVALID")
        boundaries = activation.get("boundaries") or {}
        _require(boundaries.get("release_authorized") is False
                 and boundaries.get("publication_workflow_authorized") is False
                 and boundaries.get("canonical_writes") == 0,
                 "HOSTED_RUNTIME_RELEASE_BOUNDARY_INVALID")
        _require(activation.get("deterministic_sha256") == expected.get("activation_receipt_deterministic_sha256"),
                 "HOSTED_RUNTIME_ACTIVATION_RECEIPT_DIGEST_DRIFT")

        for key in ("jurisdiction_json_sha256", "archive_sha256", "acceptance_receipt_sha256"):
            _require(expected.get(key) == meta.get(key), "HOSTED_RUNTIME_PIN_DRIFT", key)
        _require(acceptance.get("deterministic_sha256") == expected.get("acceptance_deterministic_sha256"),
                 "HOSTED_RUNTIME_ACCEPTANCE_DIGEST_DRIFT")
        _require(acceptance.get("inputs", {}).get("runtime_zip_sha256") == expected.get("runtime_zip_sha256"),
                 "HOSTED_RUNTIME_ENGINE_HASH_DRIFT")

        catalog_path = root / DEFAULT_CATALOG_REL
        catalog = package_catalog.load_catalog(catalog_path)
        entry = _active_entry(catalog)
        _require(entry == contract.get("catalog_entry"), "HOSTED_RUNTIME_ACTIVATED_CATALOG_DRIFT")
        _require(_sha_json(entry) == expected.get("catalog_entry_sha256"),
                 "HOSTED_RUNTIME_ACTIVATED_CATALOG_HASH_DRIFT")
        _require(activation.get("inputs", {}).get("catalog_entry_sha256") == expected.get("catalog_entry_sha256"),
                 "HOSTED_RUNTIME_ACTIVATION_CATALOG_CHAIN_DRIFT")

        package = package_catalog.reconstruct_package(entry, root)
        package_sha = _sha_json(package)
        _require(package_sha == expected.get("jurisdiction_json_sha256"),
                 "HOSTED_RUNTIME_PACKAGE_HASH_DRIFT", package_sha)
        identity = {
            str(row.get("person_id") or row.get("id")): _identity_status(row)
            for row in package["records"]["people"]
        }
        _require(identity == acceptance.get("person_identity_status") and set(identity.values()) == {"AUTHORITATIVE"},
                 "HOSTED_RUNTIME_PUBLIC_IDENTITY_INVALID")

        divisions = {row.get("division_kind"): row.get("division_id") for row in package["records"]["divisions"]}
        _require(isinstance(divisions.get("SLDL"), str) and isinstance(divisions.get("SLDU"), str),
                 "HOSTED_RUNTIME_DIVISION_SCOPE_INVALID")
        expected_groups, expected_bindings = build_texas_production_configuration(
            package,
            house_division_id=divisions["SLDL"],
            senate_division_id=divisions["SLDU"],
        )
        _require(expected_bindings == acceptance.get("scope", {}).get("bindings"),
                 "HOSTED_RUNTIME_BINDING_DRIFT")

        extension = _read_json(root / DEFAULT_EXTENSION_REL, "HOSTED_RUNTIME_DEFAULT_EXTENSION_INVALID")
        group = _active_group(extension)
        _require(group == expected_groups[0], "HOSTED_RUNTIME_ACTIVATED_REGISTRY_DRIFT")
        _require(_sha_json(group) == expected.get("legislative_group_sha256"),
                 "HOSTED_RUNTIME_ACTIVATED_REGISTRY_HASH_DRIFT")
        _require(activation.get("inputs", {}).get("legislative_group_sha256") == expected.get("legislative_group_sha256"),
                 "HOSTED_RUNTIME_ACTIVATION_REGISTRY_CHAIN_DRIFT")

        try:
            resolver = load_resolver_with_extensions(
                root,
                session=session,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            raise HostedRuntimeError("HOSTED_RUNTIME_RESOLVER_LOAD_FAILED", str(exc)) from exc

        return cls(
            repo_root=root,
            head_sha=head,
            environment=env,
            contract=contract,
            contract_sha256=_sha_bytes(contract_file.read_bytes()),
            meta=meta,
            acceptance=acceptance,
            activation=activation,
            package=package,
            catalog_entry=entry,
            legislative_group=group,
            resolver=resolver,
        )

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
            "acceptance_deterministic_sha256": self.acceptance["deterministic_sha256"],
            "runtime_zip_sha256": self.acceptance["inputs"]["runtime_zip_sha256"],
            "catalog_entry_sha256": _sha_json(self.catalog_entry),
            "legislative_group_sha256": _sha_json(self.legislative_group),
            "activation_receipt_deterministic_sha256": self.activation["deterministic_sha256"],
            "repository_activation": "ACTIVATED_BOUNDED",
            "activation_authorized": True,
            "release_authorized": False,
            "publication_workflow_authorized": False,
            "canonical_writes": 0,
        }

    def readiness(self) -> dict[str, Any]:
        return {
            "status": "PASS",
            "checks": {
                "activation-receipt": "PASS",
                "activated-default-catalog": "PASS",
                "activated-default-registry": "PASS",
                "package-profile-reconstruction": "PASS",
                "public-identity-gate": "PASS",
                "geometry-governance-preflight": "PASS",
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
                catalog_path=self.repo_root / DEFAULT_CATALOG_REL,
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
        return {"service": self.service_metadata(), "result": result}
