#!/usr/bin/env python3
"""Live, fail-closed Lubbock County CG-04 canonical-roster proof.

This proof verifies the frozen County #13 office roster against official
Lubbock County pages. It deliberately stops before CG-05 and does not query
geometry, geocode addresses, package a candidate, or change production data.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html.parser import HTMLParser
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SCHEMA_VERSION = "civic-gps-lubbock-cg04-proof/0.1.0"
USER_AGENT = "Mozilla/5.0 CivicData-CivicGPS-CG04/0.1 (+https://github.com/MightyLoud/CivicData)"


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _visible_text(body: bytes) -> str:
    parser = _VisibleText()
    encoding = "utf-16" if body.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    parser.feed(body.decode(encoding, errors="replace"))
    return _normalize_text(" ".join(parser.parts))


def _require_official(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in allowed_hosts:
        raise ValueError(f"non-official or unbound source URL: {url}")


def _fetch(url: str, *, attempts: int = 3) -> tuple[bytes, str, int]:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.lubbockcounty.gov/",
                },
            )
            with urlopen(request, timeout=30) as response:
                body = response.read()
                status = int(getattr(response, "status", 200))
                final_url = response.geturl()
            if status != 200 or not body:
                raise RuntimeError(f"HTTP {status} or empty response for {url}")
            return body, final_url, status
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1 + attempt)
    raise RuntimeError(f"TRANSIENT_UPSTREAM_FAILURE: {url}: {last}")


def _candidate_roster(candidate: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for office in candidate["scope"]["countywide_offices"]:
        rows.append({key: str(office[key]) for key in ("office_id", "title", "holder")})
    for family in candidate["district_families"]:
        for district in sorted((str(key) for key in family["district_keys"]), key=int):
            rows.append(
                {
                    "office_id": str(family["office_id_template"]).format(district=district),
                    "title": str(family["office_title_template"]).format(district=district),
                    "holder": str(family["holders"][district]),
                }
            )
    return sorted(rows, key=lambda row: row["office_id"])


def _validate(candidate: dict[str, Any], proof: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    if proof.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"proof schema_version must be {SCHEMA_VERSION}")
    if candidate["county"]["name"] != proof.get("county"):
        raise ValueError("candidate/proof county mismatch")
    if str(candidate["county"]["geoid"]) != str(proof.get("county_geoid")):
        raise ValueError("candidate/proof GEOID mismatch")
    candidate_sha = _sha(candidate)
    if candidate_sha != proof.get("candidate_spec_sha256"):
        raise ValueError(f"candidate spec SHA mismatch: {candidate_sha}")
    if proof.get("stop_before") != "CG-05":
        raise ValueError("CG-04 proof must stop before CG-05")
    roster = proof["canonical_roster"]
    if roster.get("identity_source_rule") != "CANONICAL_RELEASE_ONLY":
        raise ValueError("identity_source_rule must be CANONICAL_RELEASE_ONLY")
    if candidate["sources"].get("identity_conflicts"):
        raise ValueError("unresolved identity conflicts are not allowed")
    expected = int(roster["expected_total_offices"])
    records = list(roster["records"])
    if expected != 18 or candidate["scope"]["expected_total_offices"] != expected or len(records) != expected:
        raise ValueError("CG-04 expected office total mismatch")
    frozen = _candidate_roster(candidate)
    asserted = sorted(
        ({key: str(row[key]) for key in ("office_id", "title", "holder")} for row in records),
        key=lambda row: row["office_id"],
    )
    if frozen != asserted:
        raise ValueError("CG-04 proof roster does not exactly match the frozen candidate")
    if len({row["office_id"] for row in asserted}) != expected:
        raise ValueError("CG-04 office identifiers are not unique")
    allowed_hosts = {str(host).casefold() for host in roster["official_hosts"]}
    for row in records:
        _require_official(str(row["source_url"]), allowed_hosts)
        fragments = [str(value).strip() for value in row.get("required_fragments", [])]
        if len(fragments) < 2 or any(not value for value in fragments):
            raise ValueError(f"insufficient source assertions for {row['office_id']}")
    return records, allowed_hosts


def run(candidate_path: Path, proof_path: Path, output_dir: Path | None, *, validate_only: bool) -> dict[str, Any]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    records, allowed_hosts = _validate(candidate, proof)
    candidate_sha = _sha(candidate)
    proof_sha = _sha(proof)
    if validate_only:
        summary = {
            "status": "VALID",
            "candidate_spec_sha256": candidate_sha,
            "proof_spec_sha256": proof_sha,
            "record_count": len(records),
            "source_page_count": len({str(row["source_url"]) for row in records}),
            "stopped_before": "CG-05",
        }
        print(json.dumps(summary, sort_keys=True))
        return summary

    urls = sorted({str(row["source_url"]) for row in records})

    def fetch_page(url: str) -> tuple[str, tuple[str, str, int]]:
        body, final_url, status = _fetch(url)
        _require_official(final_url, allowed_hosts)
        return url, (_visible_text(body), final_url, status)

    with ThreadPoolExecutor(max_workers=min(5, len(urls))) as pool:
        cache = dict(pool.map(fetch_page, urls))

    evidence: list[dict[str, Any]] = []
    for row in sorted(records, key=lambda item: str(item["office_id"])):
        normalized, final_url, status = cache[str(row["source_url"])]
        fragments = [str(value) for value in row["required_fragments"]]
        missing = [value for value in fragments if _normalize_text(value) not in normalized]
        if missing:
            raise ValueError(f"CG-04 missing official assertions for {row['office_id']}: {missing}")
        evidence.append(
            {
                "office_id": row["office_id"],
                "title": row["title"],
                "holder": row["holder"],
                "source_url": row["source_url"],
                "final_url": final_url,
                "http_status": status,
                "source_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                "assertions": fragments,
                "status": "PASS",
            }
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "county": proof["county"],
        "county_geoid": proof["county_geoid"],
        "observed_on": proof["observed_on"],
        "candidate_spec_sha256": candidate_sha,
        "proof_spec_sha256": proof_sha,
        "decision": "GO",
        "result": "SUPPORTED_V0_1",
        "stop_class": "NONE",
        "architecture_change": "NO",
        "gates": [
            {"gate": "CG-01", "status": "PASS"},
            {"gate": "CG-02", "status": "PASS"},
            {"gate": "CG-03", "status": "PASS"},
            {"gate": "CG-04", "status": "PASS"},
            {"gate": "CG-05", "status": "READY"},
            {"gate": "CG-06", "status": "READY"},
            {"gate": "CG-07", "status": "READY"},
            {"gate": "CG-08", "status": "READY"},
            {"gate": "CG-09", "status": "READY"},
            {"gate": "CG-10", "status": "READY"},
        ],
        "cg04_canonical_roster": {
            "status": "PASS",
            "expected_total_offices": 18,
            "verified_total_offices": len(evidence),
            "identity_source_rule": "CANONICAL_RELEASE_ONLY",
            "identity_conflicts": 0,
            "source_page_count": len(urls),
            "records": evidence,
        },
        "stopped_before": "CG-05",
        "packaged": False,
        "actions": "NOT_YET_RELEASED",
        "production_runtime_changed": False,
    }
    if output_dir is None:
        raise ValueError("--output-dir is required unless --validate-only is set")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "lubbock-cg04-evidence.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "CG-04",
                "verified_offices": len(evidence),
                "source_pages": len(urls),
                "stopped_before": "CG-05",
                "evidence_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("proof", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    run(args.candidate, args.proof, args.output_dir, validate_only=args.validate_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
