#!/usr/bin/env python3
"""Classify and stage governed EV packages independently for throughput.

EV-IMP-017 scans staged governed packages (or an explicit jurisdiction list),
runs the existing proposal gate for each package, and materializes only READY
proposals into the requested output directory. A research-required or broken
jurisdiction is isolated to its own result row and never blocks classification
of the remaining targets.

This tool does not infer routing authority, mutate repository files, publish
artifacts, or write canonical CivicData records.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proposal = _load("ev_proposal_batch", ROOT / "tools" / "ev_onboarding_proposal.py")
materialize = _load("ev_materialize_batch", ROOT / "tools" / "ev_onboarding_materialize.py")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def discover_ids(root: Path) -> list[str]:
    """Return unique jurisdiction IDs found in staged governed package parts."""
    ids: list[str] = []
    for prefix, paths in proposal._artifact_groups(root).items():
        try:
            raw = proposal._decode_group(paths, prefix)
            _, summary = proposal._inspect_archive(raw, prefix)
            jurisdiction_id = str(summary.get("jurisdiction", {}).get("jurisdiction_id") or "")
            if jurisdiction_id and jurisdiction_id not in ids:
                ids.append(jurisdiction_id)
        except Exception:
            # Discovery cannot safely name a malformed archive's jurisdiction.
            # Explicitly supplied IDs still receive row-level fail-closed handling.
            continue
    return sorted(ids)


def _materialization_fields(plan: Any) -> tuple[list[dict[str, Any]], int]:
    """Validate the EV-IMP-010 materialization manifest shape fail-closed."""
    if not isinstance(plan, dict):
        raise ValueError("materialization manifest must be an object")
    changes = plan.get("changes")
    changes_required = plan.get("changes_required")
    if not isinstance(changes, list) or any(not isinstance(row, dict) for row in changes):
        raise ValueError("materialization manifest changes must be a list of objects")
    if type(changes_required) is not int or changes_required < 0:
        raise ValueError("materialization manifest changes_required must be a nonnegative integer")
    observed_adds = sum(row.get("action") == "ADD" for row in changes)
    if observed_adds != changes_required:
        raise ValueError("materialization manifest change count mismatch")
    return changes, changes_required


def run(root: Path, out: Path, ids: list[str] | None = None) -> dict[str, Any]:
    targets = sorted(set(ids if ids is not None else discover_ids(root)))
    rows: list[dict[str, Any]] = []

    for jurisdiction_id in targets:
        row: dict[str, Any] = {
            "package_jurisdiction_id": jurisdiction_id,
            "canonical_writes": 0,
        }
        try:
            proposed = proposal.propose(root, jurisdiction_id)
            row["proposal_status"] = proposed.get("status")
            row["profile"] = proposed.get("profile")
            row["routing_candidate"] = proposed.get("routing_candidate")

            if proposed.get("status") == "READY":
                try:
                    destination = out / "jurisdictions" / jurisdiction_id.replace(":", "_").replace("/", "_")
                    plan = materialize.materialize(root, jurisdiction_id, destination)
                    changes, changes_required = _materialization_fields(plan)
                    row["materialization_status"] = "ADD" if changes_required else "NOOP"
                    row["changes_required"] = changes_required
                    row["changed_files"] = [
                        change.get("path") for change in changes if change.get("action") == "ADD"
                    ]
                    row["disposition"] = "READY"
                except Exception as exc:
                    row.update(
                        materialization_status="ERROR",
                        disposition="BLOCKED",
                        error=f"{type(exc).__name__}: {exc}",
                    )
            elif proposed.get("status") == "REVIEW_REQUIRED":
                row.update(materialization_status="NOT_RUN", disposition="REVIEW_REQUIRED")
            else:
                row.update(materialization_status="NOT_RUN", disposition="BLOCKED")
        except Exception as exc:
            row.update(
                proposal_status="ERROR",
                materialization_status="NOT_RUN",
                disposition="BLOCKED",
                error=f"{type(exc).__name__}: {exc}",
            )
        rows.append(row)

    counts = Counter(row["disposition"] for row in rows)
    report: dict[str, Any] = {
        "gate": "EV-IMP-017",
        "status": "PASS",
        "targets": len(rows),
        "ready": counts["READY"],
        "review_required": counts["REVIEW_REQUIRED"],
        "blocked": counts["BLOCKED"],
        "repository_mutated": False,
        "canonical_writes": 0,
        "jurisdictions": rows,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "throughput-report.json").write_text(canonical(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-jurisdiction-id", action="append", dest="ids")
    args = parser.parse_args()
    report = run(args.repo_root.resolve(), args.output, args.ids)
    print(canonical(report).strip())


if __name__ == "__main__":
    main()
