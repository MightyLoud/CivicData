#!/usr/bin/env python3
"""Read-only freshness inventory for catalog-bound countywide source reviews."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from consumers.empowered_vote import countywide_production, package_catalog

CATALOG_PATH = "consumers/empowered_vote/package_catalog.v0.1.json"
SCOPE = "CATALOG_BOUND_COUNTYWIDE_SOURCE_REVIEWS_ONLY"
FAIL_STATES = {"INVALID", "EXPIRED", "NOT_YET_VALID"}
WARN_STATES = {"EXPIRING_14_DAYS", "EXPIRING_7_DAYS"}


class FreshnessError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise FreshnessError(code)


def _read_bound(root, reference):
    _require(isinstance(reference, dict) and set(reference) == {"path", "sha256"}
        and isinstance(reference["path"], str)
        and re.fullmatch(r"[a-f0-9]{64}", str(reference["sha256"])) is not None,
        "SOURCE_FRESHNESS_REFERENCE_INVALID")
    path = (root / reference["path"]).resolve()
    _require(not Path(reference["path"]).is_absolute() and path.is_relative_to(root),
        "SOURCE_FRESHNESS_PATH_INVALID")
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == reference["sha256"],
        "SOURCE_FRESHNESS_HASH_DRIFT")
    value = json.loads(raw)
    _require(isinstance(value, dict), "SOURCE_FRESHNESS_DOCUMENT_INVALID")
    return value


def _dates(review):
    _require(isinstance(review, dict), "SOURCE_FRESHNESS_REVIEW_INVALID")
    reviewed = date.fromisoformat(review["reviewed_on"])
    expires = date.fromisoformat(review["expires_on"])
    _require(reviewed.isoformat() == review["reviewed_on"]
        and expires.isoformat() == review["expires_on"] and reviewed < expires,
        "SOURCE_FRESHNESS_DATES_INVALID")
    return reviewed, expires


def _review_row(entry, root, current):
    row = {"entry_id": entry["entry_id"],
        "profile_id": entry["countywide_profile"]["profile_id"],
        "status": "INVALID", "contract_verified": False}
    try:
        acceptance = entry["countywide_profile"]["acceptance_receipt"]
        receipt = _read_bound(root, acceptance)
        review = receipt["source_review"]
        references = {"acceptance": acceptance}
        if isinstance(review, dict) and "path" in review:
            references["source_review"] = review
            review = _read_bound(root, review)
            storage = "SEPARATE_BOUND_RECEIPT"
        else:
            storage = "EMBEDDED_IN_BOUND_ACCEPTANCE"
        reviewed, expires = _dates(review)
        # Validate the entire existing contract at its start date. This lets an
        # expired, otherwise valid receipt be distinguished from corrupt evidence.
        # The effective status below always uses current, never this validation date.
        countywide_production.load_receipt(entry, root, today=reviewed)
        remaining = (expires - current).days
        if current < reviewed:
            status = "NOT_YET_VALID"
        elif remaining <= 0:
            status = "EXPIRED"
        elif remaining <= 7:
            status = "EXPIRING_7_DAYS"
        elif remaining <= 14:
            status = "EXPIRING_14_DAYS"
        else:
            status = "CURRENT"
        row.update(status=status, contract_verified=True, bound_references=references,
            review_storage=storage, reviewed_on=reviewed.isoformat(),
            expires_on=expires.isoformat(), days_remaining=remaining)
    except (FreshnessError, countywide_production.CountywideProductionError,
            OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        row["error"] = getattr(exc, "code", "SOURCE_FRESHNESS_INPUT_INVALID")
    return row


def build_report(repo_root, *, today=None):
    """Verify bound review contracts without geocoding, package reconstruction or writes."""
    current = datetime.now(timezone.utc).date() if today is None else today
    if type(current) is not date:
        raise ValueError("SOURCE_FRESHNESS_AS_OF_DATE_INVALID")
    root = Path(repo_root).resolve()
    report = {"report_schema": "source-review-freshness/0.1", "scope": SCOPE,
        "as_of_utc": current.isoformat(), "expiry_is_exclusive": True,
        "warning_days": [14, 7], "canonical_writes": 0,
        "status": "FAIL", "reviews": [], "not_covered_entry_ids": []}
    try:
        catalog_path = (root / CATALOG_PATH).resolve()
        _require(catalog_path.is_relative_to(root), "SOURCE_FRESHNESS_CATALOG_PATH_INVALID")
        catalog = package_catalog.load_catalog(catalog_path)
        for entry in sorted(catalog["entries"], key=lambda r: r["entry_id"]):
            if "countywide_profile" in entry:
                report["reviews"].append(_review_row(entry, root, current))
            else:
                report["not_covered_entry_ids"].append(entry["entry_id"])
        _require(bool(report["reviews"]), "SOURCE_FRESHNESS_INVENTORY_EMPTY")
        states = {row["status"] for row in report["reviews"]}
        report["status"] = ("FAIL" if states & FAIL_STATES else
            "WARN" if states & WARN_STATES else "PASS")
    except (FreshnessError, package_catalog.PackageCatalogError, OSError,
            KeyError, TypeError, ValueError, AttributeError) as exc:
        report["error"] = getattr(exc, "code", "SOURCE_FRESHNESS_CATALOG_INVALID")
    report["review_count"] = len(report["reviews"])
    return report


def _cell(value):
    return html.escape(str(value)).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_markdown(report):
    lines = ["## Bound source-review freshness", "",
        f"Status: **{report['status']}**. As of {report['as_of_utc']} UTC. "
        "Expiry is exclusive at 00:00 UTC.", "",
        "| Catalog entry | Status | Reviewed | Expires (UTC) | Days remaining | Error |",
        "|---|---|---|---|---|---|"]
    for row in report["reviews"]:
        lines.append("| " + " | ".join(_cell(row.get(key, "—")) for key in
            ("entry_id", "status", "reviewed_on", "expires_on", "days_remaining", "error")) + " |")
    if report.get("error"):
        lines.extend(["", "Inventory error: " + _cell(report["error"])])
    lines.extend(["", "Scope: catalog-bound countywide source reviews only. "
        "Other entries are outside this report; a passing report does not validate "
        "their sources, package coverage, officeholders or publication eligibility."])
    if report["not_covered_entry_ids"]:
        lines.append("Not covered: " + ", ".join(_cell(x) for x in report["not_covered_entry_ids"]) + ".")
    return "\n".join(lines) + "\n"


def _command_text(value):
    return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def emit_github_actions(report):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as stream:
            stream.write(render_markdown(report))
    for row in report["reviews"]:
        level = "error" if row["status"] in FAIL_STATES else "warning" if row["status"] in WARN_STATES else None
        if level:
            message = f"{row['entry_id']}: {row['status']}"
            if row.get("contract_verified"):
                message += f"; expires {row['expires_on']} 00:00 UTC; {row['days_remaining']} days remaining"
            if row.get("error"):
                message += "; " + row["error"]
            print(f"::{level}::{_command_text(message)}", file=sys.stderr)
    if report.get("error"):
        print("::error::" + _command_text(report["error"]), file=sys.stderr)


def _cli_date(value):
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError()
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--as-of", type=_cli_date, help="UTC date for explicit simulation; CI uses the current UTC date")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--github-actions", action="store_true", help="append the step summary and emit escaped annotations")
    args = parser.parse_args(argv)
    report = build_report(args.repo_root, today=args.as_of)
    print(json.dumps(report, indent=2, sort_keys=True) if args.format == "json" else render_markdown(report), end="\n")
    if args.github_actions:
        emit_github_actions(report)
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
