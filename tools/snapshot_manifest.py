#!/usr/bin/env python3
"""Build and validate interoperable representation snapshot manifests."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CERTIFICATION_STATUSES = {
    "uncertified",
    "evidence_review",
    "external_blocker",
    "rule_fix",
    "certified",
}


class SnapshotManifestError(ValueError):
    """Fail-closed manifest contract violation."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def payload_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return canonical_json_bytes(value)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _valid_timestamp(value: Any) -> bool:
    text = _clean(value)
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _manifest_without_fingerprint(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(manifest))
    value.pop("manifest_sha256", None)
    return value


def manifest_fingerprint(manifest: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(_manifest_without_fingerprint(manifest)))


def validate_manifest(manifest: Mapping[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not isinstance(manifest, Mapping):
        return ["MANIFEST_INVALID"]

    required = {
        "manifest_version",
        "schema_version",
        "generated_at",
        "producer",
        "source_snapshots",
        "scope",
        "certification",
        "canonical_data_versions",
        "payload",
        "manifest_sha256",
    }
    if set(manifest) != required:
        missing = required - set(manifest)
        extra = set(manifest) - required
        if missing:
            errors.add("MANIFEST_REQUIRED_FIELDS")
        if extra:
            errors.add("MANIFEST_EXTRA_FIELDS")

    if manifest.get("manifest_version") != "0.1":
        errors.add("MANIFEST_VERSION_INVALID")
    if not _clean(manifest.get("schema_version")):
        errors.add("SCHEMA_VERSION_REQUIRED")
    if not _valid_timestamp(manifest.get("generated_at")):
        errors.add("GENERATED_AT_INVALID")

    producer = manifest.get("producer")
    if not isinstance(producer, Mapping) or set(producer) != {"system", "adapter_version"}:
        errors.add("PRODUCER_INVALID")
    elif not _clean(producer.get("system")) or not _clean(producer.get("adapter_version")):
        errors.add("PRODUCER_REQUIRED_FIELDS")

    snapshots = manifest.get("source_snapshots")
    if not isinstance(snapshots, list) or not snapshots:
        errors.add("SOURCE_SNAPSHOT_REQUIRED")
    else:
        for row in snapshots:
            if not isinstance(row, Mapping) or set(row) != {"system", "snapshot_id", "locator"}:
                errors.add("SOURCE_SNAPSHOT_INVALID")
                continue
            if not all(_clean(row.get(k)) for k in ("system", "snapshot_id", "locator")):
                errors.add("SOURCE_SNAPSHOT_INVALID")

    scope = manifest.get("scope")
    if not isinstance(scope, Mapping) or set(scope) != {
        "jurisdiction_ocdid",
        "division_ocdids",
        "complete_jurisdiction",
    }:
        errors.add("SCOPE_INVALID")
    else:
        jurisdiction = _clean(scope.get("jurisdiction_ocdid"))
        if not jurisdiction.startswith("ocd-jurisdiction/"):
            errors.add("JURISDICTION_OCDID_INVALID")
        divisions = scope.get("division_ocdids")
        if not isinstance(divisions, list) or len(divisions) != len(set(divisions)):
            errors.add("DIVISION_OCDIDS_INVALID")
        elif any(
            not isinstance(value, str) or not value.startswith("ocd-division/")
            for value in divisions
        ):
            errors.add("DIVISION_OCDIDS_INVALID")
        if not isinstance(scope.get("complete_jurisdiction"), bool):
            errors.add("COMPLETE_JURISDICTION_INVALID")

    certification = manifest.get("certification")
    cert_keys = {
        "status",
        "raw_complete",
        "normalized_complete",
        "qa_passed",
        "parity_ok",
        "verified_at",
    }
    if not isinstance(certification, Mapping) or set(certification) != cert_keys:
        errors.add("CERTIFICATION_INVALID")
    else:
        status = certification.get("status")
        if status not in CERTIFICATION_STATUSES:
            errors.add("CERTIFICATION_STATUS_INVALID")
        gates = [
            certification.get("raw_complete"),
            certification.get("normalized_complete"),
            certification.get("qa_passed"),
            certification.get("parity_ok"),
        ]
        if any(not isinstance(value, bool) for value in gates):
            errors.add("CERTIFICATION_GATES_INVALID")
        if status == "certified" and gates != [True, True, True, True]:
            errors.add("CERTIFIED_GATES_INCOMPLETE")
        if not _valid_timestamp(certification.get("verified_at")):
            errors.add("CERTIFICATION_VERIFIED_AT_INVALID")

    versions = manifest.get("canonical_data_versions")
    if not isinstance(versions, Mapping) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or not value
        for key, value in (versions.items() if isinstance(versions, Mapping) else [])
    ):
        errors.add("CANONICAL_DATA_VERSIONS_INVALID")

    payload = manifest.get("payload")
    payload_keys = {"media_type", "locator", "bytes", "content_sha256"}
    if not isinstance(payload, Mapping) or set(payload) != payload_keys:
        errors.add("PAYLOAD_INVALID")
    else:
        if not _clean(payload.get("media_type")) or not _clean(payload.get("locator")):
            errors.add("PAYLOAD_REQUIRED_FIELDS")
        size = payload.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            errors.add("PAYLOAD_BYTES_INVALID")
        digest = payload.get("content_sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            errors.add("PAYLOAD_HASH_INVALID")

    fingerprint = manifest.get("manifest_sha256")
    if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
        errors.add("MANIFEST_HASH_INVALID")
    elif fingerprint != manifest_fingerprint(manifest):
        errors.add("MANIFEST_HASH_MISMATCH")

    return sorted(errors)


def build_manifest(
    *,
    payload: Any,
    payload_locator: str,
    payload_media_type: str,
    schema_version: str,
    generated_at: str,
    producer_system: str,
    adapter_version: str,
    source_snapshots: Sequence[Mapping[str, Any]],
    jurisdiction_ocdid: str,
    division_ocdids: Sequence[str],
    complete_jurisdiction: bool,
    certification: Mapping[str, Any],
    canonical_data_versions: Mapping[str, str],
) -> dict[str, Any]:
    data = payload_bytes(payload)
    manifest: dict[str, Any] = {
        "manifest_version": "0.1",
        "schema_version": _clean(schema_version),
        "generated_at": _clean(generated_at),
        "producer": {
            "system": _clean(producer_system),
            "adapter_version": _clean(adapter_version),
        },
        "source_snapshots": [dict(row) for row in source_snapshots],
        "scope": {
            "jurisdiction_ocdid": _clean(jurisdiction_ocdid),
            "division_ocdids": list(division_ocdids),
            "complete_jurisdiction": complete_jurisdiction,
        },
        "certification": dict(certification),
        "canonical_data_versions": dict(canonical_data_versions),
        "payload": {
            "media_type": _clean(payload_media_type),
            "locator": _clean(payload_locator),
            "bytes": len(data),
            "content_sha256": sha256_bytes(data),
        },
    }
    manifest["manifest_sha256"] = manifest_fingerprint(manifest)
    errors = validate_manifest(manifest)
    if errors:
        raise SnapshotManifestError("MANIFEST_INVALID:" + ",".join(errors))
    return manifest


def verify_payload(manifest: Mapping[str, Any], payload: Any) -> None:
    errors = validate_manifest(manifest)
    if errors:
        raise SnapshotManifestError("MANIFEST_INVALID:" + ",".join(errors))
    data = payload_bytes(payload)
    expected = manifest["payload"]
    if len(data) != expected["bytes"]:
        raise SnapshotManifestError("PAYLOAD_BYTES_MISMATCH")
    if sha256_bytes(data) != expected["content_sha256"]:
        raise SnapshotManifestError("PAYLOAD_HASH_MISMATCH")


def same_governed_snapshot(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    if validate_manifest(left) or validate_manifest(right):
        raise SnapshotManifestError("MANIFEST_INVALID")
    return left["manifest_sha256"] == right["manifest_sha256"]
