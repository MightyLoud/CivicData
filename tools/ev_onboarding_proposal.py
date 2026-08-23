#!/usr/bin/env python3
"""Derive safe Empowered.Vote onboarding proposals from governed packages.

EV-IMP-009 removes most hand-authored onboarding configuration without
inventing geography authority. It discovers staged package artifacts, validates
them, derives package/profile/count/address fields, and reuses an already
governed routing record when one exists. If routing authority is not already
governed, it stops at REVIEW_REQUIRED and emits a bounded routing research
candidate instead of fabricating a production spec.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from consumers.empowered_vote import package_source


class ProposalError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def slug(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not out:
        raise ProposalError("jurisdiction name cannot produce a routing slug")
    return out


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProposalError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProposalError(f"expected JSON object: {path}")
    return value


def _artifact_groups(repo_root: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in sorted((repo_root / "data" / "packages").glob("**/*.zip.b64.part*")):
        rel = path.relative_to(repo_root).as_posix()
        marker = ".zip.b64.part"
        if marker not in rel:
            continue
        prefix = rel.split(marker, 1)[0] + marker
        groups.setdefault(prefix, []).append(path)
    return groups


def _decode_group(paths: list[Path], label: str) -> bytes:
    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in sorted(paths))
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ProposalError(f"invalid package base64: {label}") from exc


def _inspect_archive(raw: bytes, label: str) -> tuple[str, dict[str, Any]]:
    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / "package.zip"
        archive.write_bytes(raw)
        try:
            with zipfile.ZipFile(archive) as zf:
                candidates = sorted(name for name in zf.namelist() if name.endswith("/package/jurisdiction.json"))
                if len(candidates) != 1:
                    raise ProposalError(f"package archive must contain exactly one jurisdiction.json: {label}")
                data = json.loads(zf.read(candidates[0]).decode("utf-8"))
        except zipfile.BadZipFile as exc:
            raise ProposalError(f"invalid package ZIP: {label}") from exc
    if not isinstance(data, dict):
        raise ProposalError(f"invalid package jurisdiction object: {label}")
    return candidates[0].removesuffix("/jurisdiction.json"), data


def discover_package(repo_root: Path, package_jurisdiction_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    matches: list[tuple[str, list[Path], bytes, str]] = []
    for prefix, paths in _artifact_groups(repo_root).items():
        raw = _decode_group(paths, prefix)
        package_subdir, summary = _inspect_archive(raw, prefix)
        if summary.get("jurisdiction", {}).get("jurisdiction_id") == package_jurisdiction_id:
            matches.append((prefix, paths, raw, package_subdir))
    if not matches:
        raise ProposalError(f"no staged governed package found for {package_jurisdiction_id}")
    if len(matches) != 1:
        raise ProposalError(f"multiple staged governed packages found for {package_jurisdiction_id}")

    prefix, paths, raw, package_subdir = matches[0]
    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / "package.zip"
        archive.write_bytes(raw)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(Path(td) / "expanded")
        package = package_source.load_jurisdiction_package(Path(td) / "expanded" / package_subdir)

    artifact = {
        "encoding": "base64-parts",
        "parts_glob": prefix + "*",
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "package_subdir": package_subdir,
    }
    return package, artifact


def derive_profile(package: dict[str, Any]) -> str:
    caps = package_source.package_capabilities(package)
    if caps.get("full_essentials"):
        return "municipal_essentials"
    if caps.get("representation"):
        return "municipal_representation"
    raise ProposalError("governed package does not satisfy an EV consumer profile")


def derive_live_addresses(package: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for row in package.get("qa", {}).get("address_tests", []):
        if not isinstance(row, dict):
            continue
        value = row.get("input") or row.get("address_input") or row.get("normalized_address")
        if value and str(value).strip() and str(value).strip() not in values:
            values.append(str(value).strip())
    if len(values) < 2:
        raise ProposalError("governed package does not expose two reusable live address controls")
    return values


def expected_counts(package: dict[str, Any]) -> dict[str, Any]:
    records = package["records"]
    current_holders = sum(
        1 for row in records.get("role_terms", [])
        if str(row.get("status") or row.get("currentness_status") or "").upper().startswith("CURRENT")
    )
    return {
        "office_rows": len(records.get("offices", [])),
        "current_holders": current_holders,
        "address_controls": len(package["qa"]["address_tests"]),
        "qa_fail_count": package["qa"]["qa_fail_count"],
        "blocking_gap_count": package["qa"]["blocking_gap_count"],
        "parity_ok": package["qa"]["parity_ok"],
    }


def full_essentials_counts(package: dict[str, Any]) -> dict[str, int] | None:
    if derive_profile(package) != "municipal_essentials":
        return None
    records = package["records"]
    candidacies = records.get("candidacies", [])
    return {
        "elections": len(records.get("elections", [])),
        "contests": len(records.get("contests", [])),
        "candidacies": len(candidacies),
        "named_person_candidacies": sum(row.get("candidate_kind") == "PERSON" for row in candidacies),
        "write_in_buckets": sum(row.get("candidate_kind") == "WRITE_IN_BUCKET" for row in candidacies),
    }


def _routing_matches(repo_root: Path, geoid: str) -> list[tuple[str, dict[str, Any]]]:
    registry = load_json(repo_root / "civic_gps_extensions" / "registry_bundles.v0.1.json")
    matches: list[tuple[str, dict[str, Any]]] = []
    for row in registry.get("bundles", []):
        if not isinstance(row, dict):
            continue
        scope = row.get("scope_match") or {}
        if str(scope.get("equals")) == geoid:
            matches.append(("CENSUS_GEOID", row))
    for row in registry.get("municipal_boundary_overlays", []):
        if isinstance(row, dict) and str(row.get("identity_value")) == geoid:
            matches.append(("MUNICIPAL_BOUNDARY_OVERLAY", row))
    return matches


def _routing_from_bundle(bundle: dict[str, Any], geoid: str) -> tuple[str, dict[str, Any]]:
    jurisdictions = bundle.get("jurisdictions") or []
    divisions = bundle.get("division_rules") or []
    if len(jurisdictions) != 1 or len(divisions) != 1:
        raise ProposalError("Census routing candidate must expose exactly one jurisdiction and one division")
    scope = bundle.get("scope_match") or {}
    routing = {
        "adapter_id": bundle["adapter_id"],
        "priority": int(bundle.get("priority", 80)),
        "geography": scope.get("geography", "place"),
        "geoid": geoid,
        "division_id": divisions[0]["division_id"],
        "division_name": divisions[0]["name"],
        "division_type": divisions[0].get("type", "municipality"),
        "release_files": list(bundle.get("release_files", [])),
        "district_adapters": list(bundle.get("district_adapters", [])),
        "known_gaps": list(bundle.get("known_gaps", [])),
    }
    return str(jurisdictions[0]["jurisdiction_id"]), routing


def _routing_from_overlay(row: dict[str, Any], geoid: str) -> tuple[str, dict[str, Any]]:
    routing: dict[str, Any] = {
        "strategy": "MUNICIPAL_BOUNDARY_OVERLAY",
        "geoid": geoid,
        "overlay_id": row["overlay_id"],
        "parent_jurisdiction_id": row["parent_jurisdiction_id"],
        "service_url": row["service_url"],
        "where": row["where"],
        "identity_field": row["identity_field"],
        "identity_value": str(row["identity_value"]),
        "division_id": row["division_id"],
        "division_name": row["division_name"],
        "division_type": row.get("division_type", "municipality"),
        "release_file": row["release_file"],
    }
    for key in ("parent_division_id", "authority", "reference_url"):
        if row.get(key):
            routing[key] = row[key]
    return str(row["jurisdiction_id"]), routing


def normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(spec))
    routing = value.get("routing")
    if isinstance(routing, dict) and routing.get("adapter_id") and "strategy" not in routing:
        routing["strategy"] = "CENSUS_GEOID"
    return value


def propose(repo_root: Path, package_jurisdiction_id: str) -> dict[str, Any]:
    package, artifact = discover_package(repo_root, package_jurisdiction_id)
    jurisdiction = package["jurisdiction"]
    geoid = str(jurisdiction["geoid"])
    state = str(jurisdiction["state_abbr"]).lower()
    name_slug = slug(str(jurisdiction["name"]))
    profile = derive_profile(package)
    candidate_civic_id = f"jur-us-{state}-{name_slug}"
    entry_id = f"{state}-{name_slug}-{profile.replace('municipal_', 'municipal-')}-v{package['schema_version']}"
    addresses = derive_live_addresses(package)

    matches = _routing_matches(repo_root, geoid)
    if len(matches) > 1:
        raise ProposalError(f"multiple governed routing records match GEOID {geoid}")

    base: dict[str, Any] = {
        "gate": "EV-IMP-009",
        "package_jurisdiction_id": package_jurisdiction_id,
        "package_schema_version": package["schema_version"],
        "package_geoid": geoid,
        "profile": profile,
        "artifact": artifact,
        "expected": expected_counts(package),
        "live_addresses": addresses,
        "canonical_writes": 0,
    }
    full = full_essentials_counts(package)
    if full is not None:
        base["full_essentials_expected"] = full

    if not matches:
        base.update({
            "status": "REVIEW_REQUIRED",
            "candidate_entry_id": entry_id,
            "candidate_civic_gps_jurisdiction_id": candidate_civic_id,
            "routing_candidate": {
                "status": "RESEARCH_REQUIRED",
                "governed_geoid": geoid,
                "first_probe": "CENSUS_GEOID",
                "fallback": "MUNICIPAL_BOUNDARY_OVERLAY",
                "reason": "No governed Civic GPS routing metadata currently matches this package GEOID.",
            },
            "production_spec": None,
        })
        return base

    strategy, route = matches[0]
    if strategy == "CENSUS_GEOID":
        civic_id, routing = _routing_from_bundle(route, geoid)
    else:
        civic_id, routing = _routing_from_overlay(route, geoid)

    spec: dict[str, Any] = {
        "spec_version": "0.1",
        "entry_id": entry_id,
        "profile": profile,
        "civic_gps_jurisdiction_id": civic_id,
        "package_jurisdiction_id": package_jurisdiction_id,
        "package_schema_version": package["schema_version"],
        "artifact": artifact,
        "routing": routing,
        "expected": expected_counts(package),
    }
    if full is not None:
        spec["full_essentials_expected"] = full
    spec["live_addresses"] = addresses

    catalog = load_json(repo_root / "consumers" / "empowered_vote" / "package_catalog.v0.1.json")
    entry_collision = next((row for row in catalog.get("entries", []) if row.get("entry_id") == entry_id and row.get("package_jurisdiction_id") != package_jurisdiction_id), None)
    civic_collision = next((row for row in catalog.get("entries", []) if row.get("civic_gps_jurisdiction_id") == civic_id and row.get("package_jurisdiction_id") != package_jurisdiction_id), None)
    if entry_collision or civic_collision:
        base.update({"status": "REVIEW_REQUIRED", "routing_candidate": {"status": "COLLISION"}, "production_spec": None})
        return base

    base.update({
        "status": "READY",
        "candidate_entry_id": entry_id,
        "candidate_civic_gps_jurisdiction_id": civic_id,
        "routing_candidate": {"status": "GOVERNED_MATCH", "strategy": strategy},
        "production_spec": spec,
    })
    return base


def verify_all_production(repo_root: Path, out: Path) -> dict[str, Any]:
    spec_paths = [p for p in sorted((repo_root / "onboarding" / "ev").glob("*.v0.1.json")) if not p.name.startswith("TEMPLATE")]
    rows = []
    for path in spec_paths:
        existing = load_json(path)
        proposal = propose(repo_root, str(existing["package_jurisdiction_id"]))
        if proposal.get("status") != "READY" or not proposal.get("production_spec"):
            raise ProposalError(f"production onboarding spec no longer regenerates: {path.name}")
        if canonical(normalize_spec(proposal["production_spec"])) != canonical(normalize_spec(existing)):
            raise ProposalError(f"generated onboarding spec drift: {path.name}")
        rows.append({
            "spec": path.relative_to(repo_root).as_posix(),
            "package_jurisdiction_id": existing["package_jurisdiction_id"],
            "profile": proposal["profile"],
            "routing_strategy": proposal["routing_candidate"]["strategy"],
            "status": "PASS",
            "canonical_writes": 0,
        })

    report = {
        "gate": "EV-IMP-009",
        "status": "PASS",
        "production_specs_regenerated": len(rows),
        "jurisdictions": rows,
        "routing_authority_inferred": False,
        "canonical_writes": 0,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "proposal-roundtrip.json").write_text(canonical(report), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--package-jurisdiction-id")
    ap.add_argument("--verify-production", action="store_true")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.repo_root.resolve()
    if args.verify_production:
        result = verify_all_production(root, args.output)
    else:
        if not args.package_jurisdiction_id:
            raise SystemExit("--package-jurisdiction-id is required unless --verify-production is used")
        result = propose(root, args.package_jurisdiction_id)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "proposal.json").write_text(canonical(result), encoding="utf-8")
    print(canonical(result).strip())


if __name__ == "__main__":
    main()
