#!/usr/bin/env python3
"""Generic multi-jurisdiction representation export and conformance engine.

This orchestrates existing governed adapters. It does not create a second data
model and performs no partner writes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from adapters.factory.export_representation import (
    ExportError as FactoryContractExportError,
    export_factory_package,
)
from consumers.civicpatch.adapter import (
    CivicPatchAdapterError,
    core_semantic_projection,
    export_core_to_civicpatch,
    round_trip_semantic_projection,
    validate_civicpatch_officials,
)
from consumers.empowered_vote.contract_v1 import validate_contract
from consumers.empowered_vote.runtime_conformance import evaluate_governed_address_runtime
from tools.canonical_representation_core import (
    CanonicalCoreError,
    from_jurisdiction_package,
    validate_core,
)
from tools.jurisdiction_package import validate as validate_jurisdiction_package

ROOT = Path(__file__).resolve().parents[1]
REPORT_VERSION = "0.1"
SUPPORTED_CONSUMERS = (
    "civicpatch",
    "empowered_vote",
    "civic_mirror",
    "seegov",
)
STATUSES = {"PASS", "LOSSY", "BLOCKED", "NOT_TESTED"}


class ConformanceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def pretty_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def discover_packages(root: Path = ROOT) -> list[Path]:
    return sorted(
        path
        for path in (root / "data" / "normalized").glob("**/jurisdiction.json")
        if path.is_file()
    )


def _native_identifier(row: Mapping[str, Any], scheme: str) -> str | None:
    for identifier in row.get("identifiers") or []:
        if (
            isinstance(identifier, Mapping)
            and identifier.get("scheme") == scheme
            and identifier.get("id") not in (None, "")
        ):
            return str(identifier["id"])
    return None


def _contract_semantic_projection(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    organizations = {
        str(row["id"]): row
        for row in contract.get("organizations", [])
        if isinstance(row, Mapping) and row.get("id")
    }
    roles = {
        str(row["id"]): row
        for row in contract.get("roles", [])
        if isinstance(row, Mapping) and row.get("id")
    }
    posts = {
        str(row["id"]): row
        for row in contract.get("posts", [])
        if isinstance(row, Mapping) and row.get("id")
    }
    people = {
        str(row["id"]): row
        for row in contract.get("people", [])
        if isinstance(row, Mapping) and row.get("id")
    }

    out: list[dict[str, Any]] = []
    for membership in contract.get("memberships", []):
        if not isinstance(membership, Mapping) or membership.get("closed_at") is not None:
            continue
        person = people.get(str(membership.get("person_id") or ""))
        post = posts.get(str(membership.get("post_id") or ""))
        organization = organizations.get(str(membership.get("organization_id") or ""))
        if person is None or post is None or organization is None:
            continue
        role = roles.get(str(post.get("role_id") or ""), {})
        out.append(
            {
                "person_id": _native_identifier(person, "civicdata_factory_person"),
                "name": person.get("name"),
                "membership_id": _native_identifier(
                    membership, "civicdata_factory_role_term"
                ),
                "post_id": _native_identifier(post, "civicdata_factory_office"),
                "organization_id": _native_identifier(
                    organization, "civicdata_factory_body"
                ),
                "role_id": post.get("role_id"),
                "role_label": role.get("label"),
                "jurisdiction_ocdid": post.get("jurisdiction_ocdid"),
                "division_ocdid": post.get("division_ocdid"),
                "start_date": membership.get("start_date"),
                "end_date": membership.get("end_date"),
                "internal_label": membership.get("label"),
            }
        )
    return sorted(
        out,
        key=lambda row: (
            str(row.get("person_id") or ""),
            str(row.get("membership_id") or ""),
        ),
    )


def compare_core_contract_semantics(
    core: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    """Compare stable representation semantics across Core and Contract v1.

    A Contract partial date may enrich a Core null date when the Core's evidence
    retained that precision only as an assertion. That is recorded as a note,
    not silently treated as exact-date parity.
    """
    core_rows = {
        row["membership_id"]: row
        for row in core_semantic_projection(core)
    }
    contract_rows = {
        row["membership_id"]: row
        for row in _contract_semantic_projection(contract)
        if row.get("membership_id")
    }

    losses: list[str] = []
    notes: list[str] = []
    if set(core_rows) != set(contract_rows):
        missing = sorted(set(core_rows) - set(contract_rows))
        extra = sorted(set(contract_rows) - set(core_rows))
        if missing:
            losses.append("CONTRACT_MISSING_MEMBERSHIPS:" + ",".join(missing))
        if extra:
            losses.append("CONTRACT_EXTRA_MEMBERSHIPS:" + ",".join(extra))

    stable_fields = (
        "person_id",
        "name",
        "post_id",
        "organization_id",
        "role_id",
        "role_label",
        "jurisdiction_ocdid",
        "division_ocdid",
        "internal_label",
    )
    for membership_id in sorted(set(core_rows) & set(contract_rows)):
        left = core_rows[membership_id]
        right = contract_rows[membership_id]
        for field in stable_fields:
            if left.get(field) != right.get(field):
                losses.append(
                    f"CONTRACT_FIELD_MISMATCH:{membership_id}:{field}"
                )
        for field in ("start_date", "end_date"):
            core_value = left.get(field)
            contract_value = right.get(field)
            if core_value is not None and core_value != contract_value:
                losses.append(
                    f"CONTRACT_FIELD_MISMATCH:{membership_id}:{field}"
                )
            elif core_value is None and contract_value is not None:
                notes.append(
                    f"CONTRACT_PARTIAL_DATE_ENRICHMENT:{membership_id}:{field}:{contract_value}"
                )
    return sorted(set(losses)), sorted(set(notes))


def _identity_gaps_from_contract(contract: Mapping[str, Any]) -> list[str]:
    gaps: list[str] = []
    for row in contract.get("organizations", []):
        if isinstance(row, Mapping) and row.get("shared_identity_id") in (None, ""):
            native = _native_identifier(row, "civicdata_factory_body")
            if native:
                gaps.append("organization:" + native)
    for row in contract.get("people", []):
        if isinstance(row, Mapping) and row.get("shared_identity_id") in (None, ""):
            native = _native_identifier(row, "civicdata_factory_person")
            if native:
                gaps.append("person:" + native)
    return sorted(gaps)


def _consumer_result(
    status: str,
    *,
    mode: str,
    semantic_loss: Sequence[str] = (),
    identity_gaps: Sequence[str] = (),
    geography_gaps: Sequence[str] = (),
    semantic_notes: Sequence[str] = (),
    untested_capabilities: Sequence[str] = (),
    errors: Sequence[str] = (),
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ConformanceError("STATUS_INVALID")
    return {
        "status": status,
        "mode": mode,
        "semantic_loss": list(semantic_loss),
        "identity_gaps": list(identity_gaps),
        "geography_gaps": list(geography_gaps),
        "semantic_notes": list(semantic_notes),
        "untested_capabilities": list(untested_capabilities),
        "errors": list(errors),
        "details": dict(details) if isinstance(details, Mapping) else {},
    }


def evaluate_package(
    package_path: Path,
    *,
    root: Path = ROOT,
    generated_at: str,
    consumers: Sequence[str] = SUPPORTED_CONSUMERS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {
            "package_path": str(package_path.relative_to(root)),
            "jurisdiction_id": None,
            "jurisdiction_name": None,
            "jurisdiction_ocdid": None,
            "source_package": {"status": "BLOCKED", "errors": [type(exc).__name__]},
            "certification": "unknown",
            "canonical_core": {"status": "BLOCKED", "errors": ["SOURCE_PACKAGE_UNREADABLE"]},
            "representation_contract": {"status": "BLOCKED", "errors": ["SOURCE_PACKAGE_UNREADABLE"], "semantic_loss": [], "semantic_notes": []},
            "consumers": {},
        }
        for consumer in consumers:
            result["consumers"][consumer] = _consumer_result(
                "BLOCKED",
                mode="SOURCE_PACKAGE_UNREADABLE",
                errors=["SOURCE_PACKAGE_UNREADABLE"],
            )
        return result, {}

    jurisdiction = package.get("jurisdiction") if isinstance(package, Mapping) else {}
    result: dict[str, Any] = {
        "package_path": str(package_path.relative_to(root)),
        "jurisdiction_id": (
            jurisdiction.get("jurisdiction_id")
            if isinstance(jurisdiction, Mapping)
            else None
        ),
        "jurisdiction_name": (
            jurisdiction.get("name")
            if isinstance(jurisdiction, Mapping)
            else None
        ),
        "jurisdiction_ocdid": (
            jurisdiction.get("ocd_jurisdiction_id")
            or jurisdiction.get("jurisdiction_ocdid")
            if isinstance(jurisdiction, Mapping)
            else None
        ),
        "source_package": {"status": "PASS", "errors": []},
        "certification": "unknown",
        "canonical_core": {"status": "BLOCKED", "errors": []},
        "representation_contract": {
            "status": "BLOCKED",
            "errors": [],
            "semantic_loss": [],
            "semantic_notes": [],
        },
        "consumers": {},
    }
    payloads: dict[str, Any] = {}

    package_errors = validate_jurisdiction_package(package)
    if package_errors:
        result["source_package"] = {
            "status": "BLOCKED",
            "errors": list(package_errors),
        }
        for consumer in consumers:
            result["consumers"][consumer] = _consumer_result(
                "BLOCKED",
                mode="SOURCE_PACKAGE_GATE",
                errors=package_errors,
            )
        return result, payloads

    try:
        core = from_jurisdiction_package(package)
    except (CanonicalCoreError, ValueError, TypeError) as exc:
        result["canonical_core"] = {
            "status": "BLOCKED",
            "errors": [str(exc)],
        }
        for consumer in consumers:
            result["consumers"][consumer] = _consumer_result(
                "BLOCKED",
                mode="CANONICAL_CORE_GATE",
                errors=[str(exc)],
            )
        return result, payloads

    core_errors = validate_core(core)
    if core_errors:
        result["canonical_core"] = {
            "status": "BLOCKED",
            "errors": core_errors,
        }
        for consumer in consumers:
            result["consumers"][consumer] = _consumer_result(
                "BLOCKED",
                mode="CANONICAL_CORE_GATE",
                errors=core_errors,
            )
        return result, payloads

    result["canonical_core"] = {"status": "PASS", "errors": []}
    result["certification"] = core["certification"]["status"]
    payloads["canonical_core"] = core

    try:
        contract = export_factory_package(
            package,
            generated_at=generated_at,
            governed_package=True,
        )
        contract_errors = validate_contract(contract, require_certified=True)
    except (FactoryContractExportError, ValueError, TypeError) as exc:
        contract = None
        contract_errors = [str(exc)]

    if contract is None or contract_errors:
        result["representation_contract"] = {
            "status": "BLOCKED",
            "errors": list(contract_errors),
            "semantic_loss": [],
            "semantic_notes": [],
        }
    else:
        contract_loss, contract_notes = compare_core_contract_semantics(core, contract)
        result["representation_contract"] = {
            "status": "LOSSY" if contract_loss else "PASS",
            "errors": [],
            "semantic_loss": contract_loss,
            "semantic_notes": contract_notes,
        }
        payloads["representation_contract"] = contract

    contract_identity_gaps = (
        _identity_gaps_from_contract(contract)
        if isinstance(contract, Mapping)
        else []
    )

    for consumer in consumers:
        if consumer not in SUPPORTED_CONSUMERS:
            raise ConformanceError("CONSUMER_UNSUPPORTED:" + consumer)

        if consumer == "civicpatch":
            if core["certification"]["status"] != "certified":
                result["consumers"][consumer] = _consumer_result(
                    "BLOCKED",
                    mode="FORWARD_EXPORT_ROUND_TRIP",
                    errors=["SOURCE_CORE_NOT_CERTIFIED"],
                )
                continue
            try:
                bundle = export_core_to_civicpatch(
                    core,
                    generated_at=generated_at,
                    source_package_path=str(package_path.relative_to(root)),
                )
                output_errors = validate_civicpatch_officials(bundle["officials"])
                expected = core_semantic_projection(core)
                actual = round_trip_semantic_projection(bundle)
                losses = []
                if output_errors:
                    losses.extend("CIVICPATCH_SHAPE:" + err for err in output_errors)
                if expected != actual:
                    losses.append("CIVICPATCH_ROUND_TRIP_SEMANTIC_MISMATCH")
                identity_gaps = sorted(
                    row["core_person_id"]
                    for row in bundle["receipt"]["person_crosswalks"]
                    if row.get("status")
                    == "PREVIEW_ONLY_REQUIRES_PARTNER_IDENTITY_REVIEW"
                )
                notes = []
                if any(row.get("internal_label") for row in bundle["receipt"]["membership_crosswalks"]):
                    notes.append("INTERNAL_MEMBERSHIP_LABEL_PRESERVED_IN_SIDECAR")
                result["consumers"][consumer] = _consumer_result(
                    "LOSSY" if losses else "PASS",
                    mode="FORWARD_EXPORT_ROUND_TRIP",
                    semantic_loss=losses,
                    identity_gaps=identity_gaps,
                    semantic_notes=notes,
                    untested_capabilities=["partner_identity_acceptance", "upstream_write"],
                )
                payloads["civicpatch_bundle"] = bundle
            except (CivicPatchAdapterError, ValueError, TypeError) as exc:
                result["consumers"][consumer] = _consumer_result(
                    "BLOCKED",
                    mode="FORWARD_EXPORT_ROUND_TRIP",
                    errors=[str(exc)],
                )

        elif consumer == "empowered_vote":
            if contract is None:
                result["consumers"][consumer] = _consumer_result(
                    "BLOCKED",
                    mode="GOVERNED_ADDRESS_FIXTURE_RUNTIME",
                    errors=result["representation_contract"]["errors"],
                )
                continue
            ev_errors = validate_contract(contract, require_certified=True)
            if ev_errors:
                result["consumers"][consumer] = _consumer_result(
                    "BLOCKED",
                    mode="GOVERNED_ADDRESS_FIXTURE_RUNTIME",
                    errors=ev_errors,
                )
            else:
                runtime = evaluate_governed_address_runtime(package, contract)
                runtime_status = str(runtime.get("status") or "NOT_TESTED")
                contract_loss = list(
                    result["representation_contract"]["semantic_loss"]
                )
                if runtime_status == "BLOCKED":
                    overall_status = "BLOCKED"
                elif runtime_status == "LOSSY" or contract_loss:
                    overall_status = "LOSSY"
                elif runtime_status == "PASS":
                    overall_status = "PASS"
                else:
                    overall_status = "NOT_TESTED"

                untested = list(runtime.get("untested_capabilities") or [])
                if "elections" not in contract:
                    untested.append("election_full_essentials")

                result["consumers"][consumer] = _consumer_result(
                    overall_status,
                    mode="GOVERNED_ADDRESS_FIXTURE_RUNTIME",
                    semantic_loss=contract_loss,
                    identity_gaps=contract_identity_gaps,
                    geography_gaps=runtime.get("geography_gaps") or [],
                    semantic_notes=result["representation_contract"]["semantic_notes"],
                    untested_capabilities=sorted(set(untested)),
                    errors=runtime.get("errors") or [],
                    details={
                        "controls_total": runtime.get("controls_total"),
                        "controls_passed": runtime.get("controls_passed"),
                        "controls_lossy": runtime.get("controls_lossy"),
                        "controls_blocked": runtime.get("controls_blocked"),
                    },
                )
                payloads["empowered_vote_runtime"] = runtime

        elif consumer == "civic_mirror":
            result["consumers"][consumer] = _consumer_result(
                "NOT_TESTED",
                mode="PARTNER_INBOUND_ONLY",
                identity_gaps=contract_identity_gaps,
                untested_capabilities=["factory_to_civic_mirror_forward_export"],
            )

        elif consumer == "seegov":
            result["consumers"][consumer] = _consumer_result(
                "NOT_TESTED",
                mode="PARTNER_INBOUND_ONLY",
                identity_gaps=contract_identity_gaps,
                untested_capabilities=["factory_to_seegov_forward_export"],
            )

    return result, payloads


def summarize(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "jurisdictions": len(results),
        "source_package": dict(Counter(
            str(row.get("source_package", {}).get("status"))
            for row in results
        )),
        "canonical_core": dict(Counter(
            str(row.get("canonical_core", {}).get("status"))
            for row in results
        )),
        "representation_contract": dict(Counter(
            str(row.get("representation_contract", {}).get("status"))
            for row in results
        )),
        "certification": dict(Counter(str(row.get("certification")) for row in results)),
        "consumers": {},
    }
    for consumer in SUPPORTED_CONSUMERS:
        summary["consumers"][consumer] = dict(
            Counter(
                str(row.get("consumers", {}).get(consumer, {}).get("status"))
                for row in results
                if consumer in row.get("consumers", {})
            )
        )
    return summary


def build_report(
    package_paths: Sequence[Path],
    *,
    root: Path = ROOT,
    generated_at: str,
    consumers: Sequence[str] = SUPPORTED_CONSUMERS,
    certified_only: bool = False,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    evaluated: list[dict[str, Any]] = []
    payloads_by_path: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []

    for path in sorted(package_paths):
        result, payloads = evaluate_package(
            path,
            root=root,
            generated_at=generated_at,
            consumers=consumers,
        )
        if certified_only and result.get("certification") != "certified":
            excluded.append(
                {
                    "package_path": result["package_path"],
                    "certification": result.get("certification"),
                    "reason": "NOT_SHARED_CERTIFIED",
                }
            )
            continue
        evaluated.append(result)
        payloads_by_path[result["package_path"]] = payloads

    report = {
        "report_version": REPORT_VERSION,
        "generated_at": generated_at,
        "selection": {
            "certified_only": certified_only,
            "discovered_count": len(package_paths),
            "selected_count": len(evaluated),
            "excluded": excluded,
        },
        "results": evaluated,
        "summary": summarize(evaluated),
    }
    return report, payloads_by_path


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Representation Conformance Report",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "| Jurisdiction | Certified | Core | Contract v1 | CivicPatch | Empowered Vote | Civic Mirror | SeeGov | Identity gaps | Geography gaps | Semantic loss |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.get("results", []):
        consumers = row.get("consumers", {})
        identity_gaps = set()
        semantic_loss = set(row.get("representation_contract", {}).get("semantic_loss", []))
        geography_gaps = set()
        for consumer in consumers.values():
            identity_gaps.update(consumer.get("identity_gaps", []))
            geography_gaps.update(consumer.get("geography_gaps", []))
            semantic_loss.update(consumer.get("semantic_loss", []))
        lines.append(
            "| {name} | {cert} | {core} | {contract} | {cp} | {ev} | {cm} | {sg} | {ig} | {gg} | {sl} |".format(
                name=row.get("jurisdiction_name") or row.get("jurisdiction_id") or row.get("package_path"),
                cert=row.get("certification"),
                core=row.get("canonical_core", {}).get("status"),
                contract=row.get("representation_contract", {}).get("status"),
                cp=consumers.get("civicpatch", {}).get("status", "—"),
                ev=consumers.get("empowered_vote", {}).get("status", "—"),
                cm=consumers.get("civic_mirror", {}).get("status", "—"),
                sg=consumers.get("seegov", {}).get("status", "—"),
                ig=len(identity_gaps),
                gg=len(geography_gaps),
                sl=len(semantic_loss),
            )
        )

    lines.extend(["", "## Summary", ""])
    summary = report.get("summary", {})
    lines.append(f"- Jurisdictions: **{summary.get('jurisdictions', 0)}**")
    lines.append(
        "- Core: " + ", ".join(
            f"{key}={value}"
            for key, value in sorted(summary.get("canonical_core", {}).items())
        )
    )
    lines.append(
        "- Contract v1: " + ", ".join(
            f"{key}={value}"
            for key, value in sorted(summary.get("representation_contract", {}).items())
        )
    )
    for consumer in SUPPORTED_CONSUMERS:
        counts = summary.get("consumers", {}).get(consumer, {})
        lines.append(
            f"- {consumer}: "
            + ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        )
    return "\n".join(lines) + "\n"


def write_artifacts(
    artifact_dir: Path,
    *,
    report: Mapping[str, Any],
    payloads_by_path: Mapping[str, Mapping[str, Any]],
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for result in report.get("results", []):
        package_path = result["package_path"]
        jurisdiction_id = result.get("jurisdiction_id") or Path(package_path).parent.name
        dest = artifact_dir / str(jurisdiction_id)
        dest.mkdir(parents=True, exist_ok=True)
        payloads = payloads_by_path.get(package_path, {})
        if "canonical_core" in payloads:
            (dest / "canonical_core.json").write_text(
                pretty_json(payloads["canonical_core"]),
                encoding="utf-8",
            )
        if "representation_contract" in payloads:
            (dest / "representation_contract_v1.json").write_text(
                pretty_json(payloads["representation_contract"]),
                encoding="utf-8",
            )
        if "civicpatch_bundle" in payloads:
            (dest / "civicpatch_bundle.json").write_text(
                pretty_json(payloads["civicpatch_bundle"]),
                encoding="utf-8",
            )
        if "empowered_vote_runtime" in payloads:
            (dest / "empowered_vote_runtime.json").write_text(
                pretty_json(payloads["empowered_vote_runtime"]),
                encoding="utf-8",
            )
        (dest / "conformance.json").write_text(
            pretty_json(result),
            encoding="utf-8",
        )


def _consumer_selection(value: str) -> tuple[str, ...]:
    if value == "all":
        return SUPPORTED_CONSUMERS
    if value not in SUPPORTED_CONSUMERS:
        raise ConformanceError("CONSUMER_UNSUPPORTED:" + value)
    return (value,)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--package", type=Path)
    group.add_argument("--all-certified", action="store_true")
    parser.add_argument(
        "--consumer",
        default="all",
        choices=("all",) + SUPPORTED_CONSUMERS,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args(argv)

    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    consumers = _consumer_selection(args.consumer)
    if args.package is not None:
        path = args.package
        if not path.is_absolute():
            path = args.root / path
        package_paths = [path]
        certified_only = False
    else:
        package_paths = discover_packages(args.root)
        certified_only = True

    report, payloads = build_report(
        package_paths,
        root=args.root,
        generated_at=generated_at,
        consumers=consumers,
        certified_only=certified_only,
    )
    output = pretty_json(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
    if args.artifact_dir:
        write_artifacts(
            args.artifact_dir,
            report=report,
            payloads_by_path=payloads,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
