#!/usr/bin/env python3
"""Run every production EV onboarding spec through live Civic GPS.

The resolver contributes geography. The catalog-selected governed package
contributes representation/election facts. The runner chooses the consumer from
the declarative profile and rejects any failed control or acceptance-count drift.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from civic_gps_extensions.loader import load_resolver_with_extensions
from consumers.empowered_vote import full_essentials_catalog, representation_catalog
from tools import ev_onboarding_batch


class LiveBatchError(RuntimeError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def run(repo_root: Path, out: Path, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    paths = ev_onboarding_batch.discover_specs(repo_root)
    rows = ev_onboarding_batch.load_specs(paths)
    ev_onboarding_batch.validate_batch(rows)
    resolver = load_resolver_with_extensions(repo_root, timeout_seconds=timeout_seconds)

    jurisdiction_results: list[dict[str, Any]] = []
    for path, spec in rows:
        expected = spec.get("expected", {})
        full_expected = spec.get("full_essentials_expected", {})
        controls: list[dict[str, Any]] = []
        for address in spec["live_addresses"]:
            try:
                geography = resolver.resolve(str(address), observed_on=None)
            except Exception as exc:
                raise LiveBatchError(f"{spec['entry_id']} resolver exception for {address}: {exc}") from exc
            if "error" in geography:
                raise LiveBatchError(f"{spec['entry_id']} Civic GPS error for {address}: {geography['error']}")
            payload = geography.get("payload") or {}
            jurisdictions = {
                str(row.get("jurisdiction_id"))
                for row in payload.get("jurisdictions", [])
                if isinstance(row, dict) and row.get("jurisdiction_id")
            }
            if spec["civic_gps_jurisdiction_id"] not in jurisdictions:
                raise LiveBatchError(
                    f"{spec['entry_id']} jurisdiction not resolved for {address}: {sorted(jurisdictions)}"
                )

            profile = spec["profile"]
            if profile == "municipal_representation":
                model = representation_catalog.build_representation_from_catalog(
                    str(address), geography, repo_root=repo_root
                )
                if model.get("status") != "PASS":
                    raise LiveBatchError(f"{spec['entry_id']} representation failed for {address}: {model}")
                if model.get("package_catalog_entry_id") != spec["entry_id"]:
                    raise LiveBatchError(f"{spec['entry_id']} catalog selection drift")
                office_rows = len(model.get("applicable_offices", []))
                holders = int(model.get("current_holder_count", 0))
                if "office_rows" in expected and office_rows != expected["office_rows"]:
                    raise LiveBatchError(f"{spec['entry_id']} office count drift: {office_rows}")
                if "current_holders" in expected and holders != expected["current_holders"]:
                    raise LiveBatchError(f"{spec['entry_id']} holder count drift: {holders}")
                observed = {"office_rows": office_rows, "current_holders": holders}
            elif profile == "municipal_essentials":
                model = full_essentials_catalog.build_full_essentials_from_catalog(
                    str(address), geography, repo_root=repo_root
                )
                if model.get("status") != "PASS":
                    raise LiveBatchError(f"{spec['entry_id']} Full Essentials failed for {address}: {model}")
                if model.get("package_catalog_entry_id") != spec["entry_id"]:
                    raise LiveBatchError(f"{spec['entry_id']} catalog selection drift")
                office_rows = len(model.get("applicable_offices", []))
                contests = model.get("recent_certified_contests", [])
                candidacies = [c for contest in contests for c in contest.get("candidates", [])]
                if "office_rows" in expected and office_rows != expected["office_rows"]:
                    raise LiveBatchError(f"{spec['entry_id']} office count drift: {office_rows}")
                if "contests" in full_expected and len(contests) != full_expected["contests"]:
                    raise LiveBatchError(f"{spec['entry_id']} contest count drift: {len(contests)}")
                if "candidacies" in full_expected and len(candidacies) != full_expected["candidacies"]:
                    raise LiveBatchError(f"{spec['entry_id']} candidacy count drift: {len(candidacies)}")
                write_ins = sum(bool(row.get("is_write_in_bucket")) for row in candidacies)
                if "write_in_buckets" in full_expected and write_ins != full_expected["write_in_buckets"]:
                    raise LiveBatchError(f"{spec['entry_id']} write-in bucket drift: {write_ins}")
                observed = {
                    "office_rows": office_rows,
                    "contests": len(contests),
                    "candidacies": len(candidacies),
                    "write_in_buckets": write_ins,
                }
            else:
                raise LiveBatchError(f"unsupported profile: {profile}")

            if model.get("canonical_writes") != 0:
                raise LiveBatchError(f"{spec['entry_id']} canonical write contract violated")
            controls.append({
                "address": str(address),
                "resolved_jurisdictions": sorted(jurisdictions),
                "observed": observed,
                "deterministic_sha256": model.get("deterministic_sha256"),
                "canonical_writes": 0,
            })

        jurisdiction_results.append({
            "spec": str(path.relative_to(repo_root)),
            "entry_id": spec["entry_id"],
            "profile": spec["profile"],
            "routing_strategy": ev_onboarding_batch.single.routing_strategy(spec),
            "controls": controls,
        })

    report = {
        "gate": "EV-IMP-008-LIVE",
        "status": "PASS",
        "production_specs": len(jurisdiction_results),
        "live_address_controls": sum(len(row["controls"]) for row in jurisdiction_results),
        "canonical_writes": 0,
        "jurisdictions": sorted(jurisdiction_results, key=lambda row: row["entry_id"]),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "live-acceptance-matrix.json").write_text(canonical(report), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--timeout-seconds", type=float, default=30.0)
    args = ap.parse_args()
    print(canonical(run(args.repo_root.resolve(), args.output, timeout_seconds=args.timeout_seconds)).strip())


if __name__ == "__main__":
    main()
