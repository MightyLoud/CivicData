#!/usr/bin/env python3
"""Materialize a READY EV onboarding proposal into a deterministic staging bundle.

This tool does not edit repository files in place. It converts a validated
EV-IMP-009 READY proposal into candidate file contents plus a patch manifest.
Existing matching production files become NOOP; conflicting files fail closed.
Routing authority must already be governed by EV-IMP-009.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROPOSAL_TOOL = ROOT / "tools" / "ev_onboarding_proposal.py"
_spec = importlib.util.spec_from_file_location("ev_onboarding_proposal_for_materialize", PROPOSAL_TOOL)
if _spec is None or _spec.loader is None:
    raise ImportError("unable to load onboarding proposal tool")
proposal_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proposal_tool)


class MaterializeError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializeError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MaterializeError(f"expected JSON object: {path}")
    return value


def spec_filename(spec: dict[str, Any]) -> str:
    civic = str(spec["civic_gps_jurisdiction_id"])
    slug = civic.removeprefix("jur-us-")
    parts = slug.split("-", 1)
    if len(parts) != 2:
        raise MaterializeError("unsupported civic GPS jurisdiction id for spec filename")
    return f"{parts[1]}.v0.1.json"


def catalog_entry(spec: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "entry_id": spec["entry_id"],
        "profile": spec["profile"],
        "civic_gps_jurisdiction_id": spec["civic_gps_jurisdiction_id"],
        "package_jurisdiction_id": spec["package_jurisdiction_id"],
        "package_schema_version": spec["package_schema_version"],
        "artifact": spec["artifact"],
    }
    if spec.get("district_binding"):
        entry["district_binding"] = spec["district_binding"]
    return entry


def routing_record(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    routing = spec["routing"]
    strategy = str(routing.get("strategy", "CENSUS_GEOID")).upper()
    if strategy == "CENSUS_GEOID":
        geoid = str(routing["geoid"])
        geography = str(routing.get("geography", "place"))
        return "bundles", {
            "adapter_id": routing["adapter_id"],
            "mode": "BASE",
            "priority": int(routing.get("priority", 80)),
            "scope_match": {"geography": geography, "fields": ["GEOID"], "equals": geoid},
            "division_rules": [{
                "division_id": routing["division_id"],
                "name": routing["division_name"],
                "type": routing.get("division_type", "municipality"),
                "when": {"geography": geography, "fields": ["GEOID"], "equals": geoid},
            }],
            "jurisdictions": [{
                "jurisdiction_id": spec["civic_gps_jurisdiction_id"],
                "activation": {"geography": geography, "fields": ["GEOID"], "equals": geoid},
            }],
            "release_files": list(routing.get("release_files", [])),
            "district_adapters": list(routing.get("district_adapters", [])),
            "applicable_office_rules": [],
            "action_registry_files": [],
            "known_gaps": list(routing.get("known_gaps", [])),
        }
    if strategy == "MUNICIPAL_BOUNDARY_OVERLAY":
        row = {
            "overlay_id": routing["overlay_id"],
            "parent_jurisdiction_id": routing["parent_jurisdiction_id"],
            "service_url": routing["service_url"],
            "where": routing["where"],
            "identity_field": routing["identity_field"],
            "identity_value": str(routing["identity_value"]),
            "jurisdiction_id": spec["civic_gps_jurisdiction_id"],
            "division_id": routing["division_id"],
            "division_name": routing["division_name"],
            "division_type": routing.get("division_type", "municipality"),
            "release_file": routing["release_file"],
        }
        for key in ("parent_division_id", "authority", "reference_url"):
            if routing.get(key):
                row[key] = routing[key]
        return "municipal_boundary_overlays", row
    raise MaterializeError(f"unsupported routing strategy: {strategy}")


def _upsert_unique(rows: list[dict[str, Any]], candidate: dict[str, Any], id_key: str) -> tuple[list[dict[str, Any]], str]:
    cid = str(candidate[id_key])
    matches = [row for row in rows if str(row.get(id_key)) == cid]
    if len(matches) > 1:
        raise MaterializeError(f"duplicate existing {id_key}: {cid}")
    if matches:
        if compact(matches[0]) != compact(candidate):
            raise MaterializeError(f"conflicting existing {id_key}: {cid}")
        return rows, "NOOP"
    out = [dict(row) for row in rows] + [candidate]
    out.sort(key=lambda row: str(row.get(id_key) or ""))
    return out, "ADD"


def materialize(repo_root: Path, package_jurisdiction_id: str, out: Path) -> dict[str, Any]:
    proposal = proposal_tool.propose(repo_root, package_jurisdiction_id)
    if proposal.get("status") != "READY" or not isinstance(proposal.get("production_spec"), dict):
        raise MaterializeError(f"proposal is not READY: {proposal.get('status')}")
    spec = proposal["production_spec"]

    targets: list[dict[str, Any]] = []

    spec_rel = Path("onboarding") / "ev" / spec_filename(spec)
    spec_target = repo_root / spec_rel
    desired_spec = canonical(spec)
    if spec_target.exists():
        existing = load_json(spec_target)
        if compact(proposal_tool.normalize_spec(existing)) != compact(proposal_tool.normalize_spec(spec)):
            raise MaterializeError(f"conflicting onboarding spec: {spec_rel.as_posix()}")
        spec_action = "NOOP"
    else:
        spec_action = "ADD"
    targets.append({"path": spec_rel.as_posix(), "action": spec_action, "content": desired_spec})

    catalog_rel = Path("consumers") / "empowered_vote" / "package_catalog.v0.1.json"
    catalog = load_json(repo_root / catalog_rel)
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        raise MaterializeError("package catalog entries must be a list")
    updated_entries, catalog_action = _upsert_unique(entries, catalog_entry(spec), "entry_id")
    catalog_out = dict(catalog)
    catalog_out["entries"] = updated_entries
    targets.append({"path": catalog_rel.as_posix(), "action": catalog_action, "content": canonical(catalog_out)})

    registry_rel = Path("civic_gps_extensions") / "registry_bundles.v0.1.json"
    registry = load_json(repo_root / registry_rel)
    bucket, route = routing_record(spec)
    rows = registry.get(bucket, [])
    if not isinstance(rows, list):
        raise MaterializeError(f"registry {bucket} must be a list")
    route_key = "adapter_id" if bucket == "bundles" else "overlay_id"
    updated_routes, route_action = _upsert_unique(rows, route, route_key)
    registry_out = dict(registry)
    registry_out[bucket] = updated_routes
    targets.append({"path": registry_rel.as_posix(), "action": route_action, "content": canonical(registry_out)})

    out.mkdir(parents=True, exist_ok=True)
    staged_root = out / "staged"
    for target in targets:
        destination = staged_root / target["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(target["content"], encoding="utf-8")

    manifest = {
        "gate": "EV-IMP-010",
        "status": "PASS",
        "package_jurisdiction_id": package_jurisdiction_id,
        "entry_id": spec["entry_id"],
        "proposal_status": proposal["status"],
        "routing_strategy": proposal["routing_candidate"]["strategy"],
        "changes": [{"path": row["path"], "action": row["action"]} for row in targets],
        "changes_required": sum(row["action"] == "ADD" for row in targets),
        "conflicts": 0,
        "repository_mutated": False,
        "canonical_writes": 0,
        "publication_authorized": False,
    }
    (out / "materialization-manifest.json").write_text(canonical(manifest), encoding="utf-8")
    return manifest


def verify_all_production(repo_root: Path, out: Path) -> dict[str, Any]:
    specs = [p for p in sorted((repo_root / "onboarding" / "ev").glob("*.v0.1.json")) if not p.name.startswith("TEMPLATE")]
    results = []
    for path in specs:
        current = load_json(path)
        result = materialize(repo_root, str(current["package_jurisdiction_id"]), out / path.stem)
        if result["changes_required"] != 0:
            raise MaterializeError(f"production onboarding is not idempotent: {path.name}")
        results.append({"entry_id": result["entry_id"], "status": "PASS", "changes_required": 0})
    report = {
        "gate": "EV-IMP-010",
        "status": "PASS",
        "production_specs_verified": len(results),
        "all_idempotent": True,
        "jurisdictions": results,
        "repository_mutated": False,
        "canonical_writes": 0,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "production-idempotence.json").write_text(canonical(report), encoding="utf-8")
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
        report = verify_all_production(root, args.output)
    else:
        if not args.package_jurisdiction_id:
            raise SystemExit("--package-jurisdiction-id required unless --verify-production")
        report = materialize(root, args.package_jurisdiction_id, args.output)
    print(compact(report).strip())


if __name__ == "__main__":
    main()
