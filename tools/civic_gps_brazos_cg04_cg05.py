#!/usr/bin/env python3
"""Live, fail-closed Brazos County CG-04 and CG-05 proof.

The proof reads a frozen candidate and assertion manifest, verifies the
canonical roster only against the official Brazos County elections page, then
verifies the county-page -> ArcGIS webmap -> feature item -> layer provenance
chain and the shared Commissioner/JP/Constable adapter contract. It does not
geocode or run interior, outside-negative, boundary, package, or promotion
controls.
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
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

SCHEMA_VERSION = "civic-gps-brazos-cg04-cg05-proof/0.1.0"
USER_AGENT = "CivicData-CivicGPS-CG04-CG05/0.1 (+https://github.com/MightyLoud/CivicData)"


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


def _fetch(url: str, *, attempts: int = 3) -> tuple[bytes, str, int]:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                },
            )
            with urlopen(request, timeout=30) as response:
                body = response.read()
                status = int(getattr(response, "status", 200))
                final_url = response.geturl()
            if status != 200 or not body:
                raise RuntimeError(f"HTTP {status} or empty response for {url}")
            return body, final_url, status
        except Exception as exc:  # fail closed after bounded retries
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1 + attempt)
    raise RuntimeError(f"TRANSIENT_UPSTREAM_FAILURE: {url}: {last}")


def _require_official(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in allowed_hosts:
        raise ValueError(f"non-official or unbound source URL: {url}")


def _candidate_roster(candidate: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for office in candidate["scope"]["countywide_offices"]:
        rows.append({key: str(office[key]) for key in ("office_id", "title", "holder")})
    for family in candidate["district_families"]:
        for district in sorted((str(key) for key in family["district_keys"]), key=int):
            rows.append({
                "office_id": str(family["office_id_template"]).format(district=district),
                "title": str(family["office_title_template"]).format(district=district),
                "holder": str(family["holders"][district]),
            })
    return sorted(rows, key=lambda row: row["office_id"])


def _prove_roster(candidate: dict[str, Any], proof: dict[str, Any]) -> dict[str, Any]:
    roster = proof["canonical_roster"]
    records = roster["records"]
    expected = int(roster["expected_total_offices"])
    if roster["identity_source_rule"] != "CANONICAL_RELEASE_ONLY":
        raise ValueError("CG-04 identity_source_rule must be CANONICAL_RELEASE_ONLY")
    if candidate["sources"].get("identity_conflicts"):
        raise ValueError("CG-04 unresolved source identity conflict")
    if candidate["scope"]["expected_total_offices"] != expected or len(records) != expected:
        raise ValueError("CG-04 expected office total mismatch")

    frozen = _candidate_roster(candidate)
    asserted = sorted(
        ({key: str(row[key]) for key in ("office_id", "title", "holder")} for row in records),
        key=lambda row: row["office_id"],
    )
    if frozen != asserted:
        raise ValueError("CG-04 proof roster does not exactly match the frozen candidate")

    allowed_hosts = {str(host).casefold() for host in roster["official_hosts"]}
    urls = sorted({str(row["source_url"]) for row in records})
    for url in urls:
        _require_official(url, allowed_hosts)

    def fetch_page(url: str) -> tuple[str, tuple[str, str, int]]:
        body, final_url, status = _fetch(url)
        _require_official(final_url, allowed_hosts)
        return url, (_visible_text(body), final_url, status)

    with ThreadPoolExecutor(max_workers=min(6, len(urls))) as pool:
        cache = dict(pool.map(fetch_page, urls))

    evidence: list[dict[str, Any]] = []
    for row in sorted(records, key=lambda item: str(item["office_id"])):
        normalized, final_url, status = cache[str(row["source_url"])]
        fragments = [str(value) for value in row["required_fragments"]]
        missing = [value for value in fragments if _normalize_text(value) not in normalized]
        if missing:
            raise ValueError(f"CG-04 missing official roster assertions for {row['office_id']}: {missing}")
        evidence.append({
            "office_id": row["office_id"],
            "title": row["title"],
            "holder": row["holder"],
            "source_url": row["source_url"],
            "final_url": final_url,
            "http_status": status,
            "source_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "assertions": fragments,
            "status": "PASS",
        })
    return {
        "status": "PASS",
        "expected_total_offices": expected,
        "verified_total_offices": len(evidence),
        "identity_source_rule": "CANONICAL_RELEASE_ONLY",
        "identity_conflicts": 0,
        "source_page_count": len(urls),
        "records": evidence,
    }


def _json_fetch(url: str) -> tuple[dict[str, Any], str, int]:
    body, final_url, status = _fetch(url)
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON from {url}: {exc}") from exc
    if not isinstance(value, dict) or value.get("error"):
        error = value.get("error") if isinstance(value, dict) else value
        raise RuntimeError(f"ArcGIS error from {url}: {error}")
    return value, final_url, status


def _prove_gis(candidate: dict[str, Any], proof: dict[str, Any]) -> dict[str, Any]:
    gis = proof["gis"]
    service_url = str(gis["service_url"]).rstrip("/")
    provenance_url = str(gis["provenance_url"])
    allowed_hosts = {str(host).casefold() for host in gis["official_hosts"]}
    for url in (service_url, provenance_url, gis["webmap_data_url"], gis["feature_item_url"]):
        _require_official(str(url), allowed_hosts)

    families = candidate["district_families"]
    if [str(row["family"]) for row in families] != list(gis["families"]):
        raise ValueError("CG-05 district-family order/scope mismatch")
    for family in families:
        geometry = family["geometry"]
        checks = {
            "service_url": geometry["service_url"] == service_url,
            "district_field": geometry["district_field"] == gis["district_field"],
            "district_field_type": geometry["district_field_type"] == gis["district_field_type"],
            "district_keys": [str(value) for value in family["district_keys"]] == list(gis["district_keys"]),
            "official": geometry["official"] is True,
            "numeric": geometry["numeric"] is True,
            "resolver_kind": family["resolver_kind"] == gis["resolver_kind"],
            "provenance_url": geometry["endpoint_provenance_url"] == provenance_url,
        }
        failed = sorted(key for key, passed in checks.items() if not passed)
        if failed:
            raise ValueError(f"CG-05 frozen adapter mismatch for {family['family']}: {failed}")

    provenance_body, final_provenance_url, provenance_status = _fetch(provenance_url)
    _require_official(final_provenance_url, allowed_hosts)
    provenance_text = _visible_text(provenance_body)
    missing = [value for value in gis["provenance_fragments"] if _normalize_text(str(value)) not in provenance_text]
    if missing:
        raise ValueError(f"CG-05 county provenance assertions missing: {missing}")
    raw_provenance = provenance_body.decode("utf-8", errors="replace").casefold()
    if str(gis["webmap_item_id"]).casefold() not in raw_provenance:
        raise ValueError("CG-05 county page no longer links the frozen ArcGIS webmap")

    webmap, final_webmap_url, webmap_status = _json_fetch(str(gis["webmap_data_url"]))
    _require_official(final_webmap_url, allowed_hosts)
    layer_matches = [
        row for row in webmap.get("operationalLayers", [])
        if str(row.get("url", "")).rstrip("/") == service_url
        and str(row.get("itemId", "")) == gis["feature_item_id"]
        and str(row.get("title", "")) == gis["webmap_layer_title"]
    ]
    if len(layer_matches) != 1:
        raise ValueError(f"CG-05 webmap provenance layer mismatch: {len(layer_matches)} matches")

    feature_item, final_feature_item_url, feature_item_status = _json_fetch(str(gis["feature_item_url"]))
    _require_official(final_feature_item_url, allowed_hosts)
    feature_service_url = service_url.rsplit("/", 1)[0]
    item_checks = {
        "id": str(feature_item.get("id")) == gis["feature_item_id"],
        "title": str(feature_item.get("title")) == gis["feature_item_title"],
        "type": str(feature_item.get("type")) == "Feature Service",
        "url": str(feature_item.get("url", "")).rstrip("/") == feature_service_url,
    }
    failed_item = sorted(key for key, passed in item_checks.items() if not passed)
    if failed_item:
        raise ValueError(f"CG-05 feature item provenance mismatch: {failed_item}")

    metadata_url = service_url + "?" + urlencode({"f": "json"})
    metadata, final_metadata_url, metadata_status = _json_fetch(metadata_url)
    _require_official(final_metadata_url, allowed_hosts)
    fields = {str(row.get("name")): str(row.get("type")) for row in metadata.get("fields", [])}
    live_checks = {
        "layer_name": str(metadata.get("name")) == gis["layer_name"],
        "layer_type": str(metadata.get("type")) == "Feature Layer",
        "geometry_type": str(metadata.get("geometryType")) == gis["geometry_type"],
        "district_field_type": fields.get(str(gis["district_field"])) == gis["district_field_type"],
        "query_capability": "query" in str(metadata.get("capabilities", "")).casefold(),
    }
    failed_live = sorted(key for key, passed in live_checks.items() if not passed)
    if failed_live:
        raise ValueError(f"CG-05 live layer metadata mismatch: {failed_live}")

    query_url = service_url + "/query?" + urlencode({
        "where": "1=1",
        "outFields": gis["district_field"],
        "returnGeometry": "false",
        "orderByFields": gis["district_field"],
        "f": "json",
    })
    query, final_query_url, query_status = _json_fetch(query_url)
    _require_official(final_query_url, allowed_hosts)
    features = query.get("features", [])
    live_keys = sorted({str(row["attributes"][gis["district_field"]]) for row in features}, key=int)
    if live_keys != list(gis["district_keys"]) or len(features) != len(live_keys):
        raise ValueError(f"CG-05 live district keys/features mismatch: {live_keys}")

    return {
        "status": "PASS",
        "shared_geometry": True,
        "families": list(gis["families"]),
        "adapter_ids": [row["adapter_id"] for row in families],
        "service_url": service_url,
        "layer_name": metadata["name"],
        "geometry_type": metadata["geometryType"],
        "district_field": gis["district_field"],
        "district_field_type": fields[gis["district_field"]],
        "district_keys": live_keys,
        "feature_count": len(features),
        "resolver_kind": gis["resolver_kind"],
        "failure_scope": gis["failure_scope"],
        "officeholder_identity_source": "CANONICAL_RELEASE_ONLY",
        "boundary_policy": gis["boundary_policy"],
        "provenance_chain": [
            {"kind": "OFFICIAL_COUNTY_PAGE", "url": final_provenance_url, "http_status": provenance_status},
            {"kind": "ARCGIS_WEBMAP", "url": final_webmap_url, "item_id": gis["webmap_item_id"], "http_status": webmap_status},
            {"kind": "ARCGIS_FEATURE_ITEM", "url": final_feature_item_url, "item_id": gis["feature_item_id"], "http_status": feature_item_status},
            {"kind": "ARCGIS_FEATURE_LAYER", "url": final_metadata_url, "http_status": metadata_status},
            {"kind": "ARCGIS_KEY_QUERY", "url": final_query_url, "http_status": query_status},
        ],
        "metadata_sha256": _sha(metadata),
        "query_sha256": _sha(query),
        "webmap_sha256": _sha(webmap),
        "feature_item_sha256": _sha(feature_item),
        "provenance_text_sha256": hashlib.sha256(provenance_text.encode("utf-8")).hexdigest(),
    }


def run(candidate_path: Path, proof_path: Path, output_dir: Path) -> dict[str, Any]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    if proof.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"proof schema_version must be {SCHEMA_VERSION}")
    if candidate["county"]["name"] != proof["county"] or str(candidate["county"]["geoid"]) != proof["county_geoid"]:
        raise ValueError("candidate/proof county identity mismatch")
    candidate_sha = _sha(candidate)
    if candidate_sha != proof.get("candidate_spec_sha256"):
        raise ValueError(f"candidate spec SHA mismatch: {candidate_sha}")
    if proof.get("stop_before") != "CG-06":
        raise ValueError("proof must stop before CG-06")

    roster = _prove_roster(candidate, proof)
    gis = _prove_gis(candidate, proof)
    report = {
        "schema_version": SCHEMA_VERSION,
        "county": proof["county"],
        "county_geoid": proof["county_geoid"],
        "observed_on": proof["observed_on"],
        "candidate_spec_sha256": candidate_sha,
        "proof_spec_sha256": _sha(proof),
        "decision": "GO",
        "result": "SUPPORTED_V0_1",
        "stop_class": "NONE",
        "architecture_change": "NO",
        "gates": [
            {"gate": "CG-01", "status": "PASS"},
            {"gate": "CG-02", "status": "PASS"},
            {"gate": "CG-03", "status": "PASS"},
            {"gate": "CG-04", "status": "PASS"},
            {"gate": "CG-05", "status": "PASS"},
            {"gate": "CG-06", "status": "READY"},
            {"gate": "CG-07", "status": "READY"},
            {"gate": "CG-08", "status": "READY"},
            {"gate": "CG-09", "status": "READY"},
            {"gate": "CG-10", "status": "READY"},
        ],
        "cg04_canonical_roster": roster,
        "cg05_gis_adapter": gis,
        "stopped_before": "CG-06",
        "packaged": False,
        "actions": "NOT_YET_RELEASED",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "cg04_cg05_evidence.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "gates": "CG-04,CG-05",
        "verified_offices": roster["verified_total_offices"],
        "district_keys": gis["district_keys"],
        "provenance_hops": len(gis["provenance_chain"]),
        "stopped_before": report["stopped_before"],
        "evidence_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("proof", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.candidate, args.proof, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
