#!/usr/bin/env python3
"""Batch gate for governed Empowered.Vote jurisdiction onboarding specs.

EV-IMP-008 turns the single-jurisdiction EV-IMP-006 contract into a catalog-wide
production gate. It discovers every production onboarding spec, rejects routing
or identity collisions, replays each spec against the governed package/catalog,
and emits one deterministic acceptance matrix. It never creates civic facts or
writes canonical CivicData records.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SINGLE_TOOL = ROOT / "tools" / "ev_jurisdiction_onboarding.py"
_spec = importlib.util.spec_from_file_location("ev_jurisdiction_onboarding_for_batch", SINGLE_TOOL)
if _spec is None or _spec.loader is None:
    raise ImportError("unable to load EV jurisdiction onboarding tool")
single = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(single)


class BatchOnboardingError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def discover_specs(repo_root: Path) -> list[Path]:
    root = repo_root / "onboarding" / "ev"
    specs = [p for p in sorted(root.glob("*.v0.1.json")) if not p.name.startswith("TEMPLATE")]
    if not specs:
        raise BatchOnboardingError("no production onboarding specs found")
    return specs


def load_specs(paths: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        data = single.load_json(path)
        rows.append((path, data))
    return rows


def routing_identity(spec: dict[str, Any]) -> str:
    strategy = single.routing_strategy(spec)
    routing = spec.get("routing", {})
    if strategy == "CENSUS_GEOID":
        value = routing.get("adapter_id")
    elif strategy == "MUNICIPAL_BOUNDARY_OVERLAY":
        value = routing.get("overlay_id")
    else:
        raise BatchOnboardingError(f"unsupported routing strategy: {strategy}")
    if not value:
        raise BatchOnboardingError(f"routing identity missing for {spec.get('entry_id')}")
    return f"{strategy}:{value}"


def _unique(rows: list[tuple[Path, dict[str, Any]]], key: str) -> None:
    seen: dict[str, Path] = {}
    for path, spec in rows:
        value = str(spec.get(key) or "")
        if not value:
            raise BatchOnboardingError(f"missing {key}: {path}")
        if value in seen:
            raise BatchOnboardingError(f"duplicate {key}: {value}: {seen[value]} and {path}")
        seen[value] = path


def validate_batch(rows: list[tuple[Path, dict[str, Any]]]) -> None:
    for key in ("entry_id", "civic_gps_jurisdiction_id", "package_jurisdiction_id"):
        _unique(rows, key)

    seen_geoid: dict[str, Path] = {}
    seen_route: dict[str, Path] = {}
    seen_artifact: dict[str, Path] = {}
    for path, spec in rows:
        routing = spec.get("routing")
        artifact = spec.get("artifact")
        if not isinstance(routing, dict) or not isinstance(artifact, dict):
            raise BatchOnboardingError(f"routing/artifact object missing: {path}")
        geoid = str(routing.get("geoid") or "")
        if not geoid:
            raise BatchOnboardingError(f"routing GEOID missing: {path}")
        if geoid in seen_geoid:
            raise BatchOnboardingError(f"duplicate governed GEOID: {geoid}: {seen_geoid[geoid]} and {path}")
        seen_geoid[geoid] = path

        route = routing_identity(spec)
        if route in seen_route:
            raise BatchOnboardingError(f"duplicate routing identity: {route}: {seen_route[route]} and {path}")
        seen_route[route] = path

        parts = str(artifact.get("parts_glob") or "")
        if not parts:
            raise BatchOnboardingError(f"package parts_glob missing: {path}")
        if parts in seen_artifact:
            raise BatchOnboardingError(f"duplicate package artifact route: {parts}")
        seen_artifact[parts] = path

        live = spec.get("live_addresses")
        if not isinstance(live, list) or len(live) < 2 or any(not str(x).strip() for x in live):
            raise BatchOnboardingError(f"production spec requires at least two live address controls: {path}")


def run(repo_root: Path, out: Path, *, verify_current: bool = True) -> dict[str, Any]:
    paths = discover_specs(repo_root)
    rows = load_specs(paths)
    validate_batch(rows)

    results: list[dict[str, Any]] = []
    for path, spec in rows:
        spec_out = out / path.stem
        report = single.run(path, repo_root, spec_out, verify_current)
        results.append({
            "spec": str(path.relative_to(repo_root)),
            "entry_id": report["entry_id"],
            "profile": report["profile"],
            "routing_strategy": report["routing_strategy"],
            "package_schema_version": report["package_schema_version"],
            "civic_gps_jurisdiction_id": report["civic_gps_jurisdiction_id"],
            "live_address_controls": len(spec["live_addresses"]),
            "observed": report["observed"],
            "capabilities": report["capabilities"],
            "matches_current_governed_artifacts": report["matches_current_governed_artifacts"],
            "canonical_writes": report["canonical_writes"],
        })

    profiles = Counter(row["profile"] for row in results)
    strategies = Counter(row["routing_strategy"] for row in results)
    matrix: dict[str, Any] = {
        "gate": "EV-IMP-008",
        "status": "PASS",
        "production_specs": len(results),
        "profiles": dict(sorted(profiles.items())),
        "routing_strategies": dict(sorted(strategies.items())),
        "live_address_controls": sum(row["live_address_controls"] for row in results),
        "all_current_artifacts_match": all(row["matches_current_governed_artifacts"] is True for row in results) if verify_current else None,
        "canonical_writes": 0,
        "jurisdictions": sorted(results, key=lambda row: row["entry_id"]),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "acceptance-matrix.json").write_text(canonical(matrix), encoding="utf-8")
    return matrix


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--no-verify-current", action="store_true")
    args = ap.parse_args()
    report = run(args.repo_root.resolve(), args.output, verify_current=not args.no_verify_current)
    print(canonical(report).strip())


if __name__ == "__main__":
    main()
