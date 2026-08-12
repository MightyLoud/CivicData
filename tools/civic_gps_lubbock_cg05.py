#!/usr/bin/env python3
"""Live, fail-closed Lubbock County CG-05 GIS-adapter proof.

The proof follows the official Lubbock County page to its public ArcGIS app,
then resolves the app's web map, Reference Layers MapServer, precinct polygon
layer, field contract, and live district keys. It stops before CG-06 and does
not geocode, resolve an address, package a candidate, or change production.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


SCHEMA_VERSION = "civic-gps-lubbock-cg05-proof/0.1.0"
USER_AGENT = "Mozilla/5.0 CivicData-CivicGPS-CG05/0.1 (+https://github.com/MightyLoud/CivicData)"


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
                    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
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


def _json_fetch(url: str, allowed_hosts: set[str]) -> tuple[dict[str, Any], str, int]:
    body, final_url, status = _fetch(url)
    _require_official(final_url, allowed_hosts)
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON from {url}: {exc}") from exc
    if not isinstance(value, dict) or value.get("error"):
        error = value.get("error") if isinstance(value, dict) else value
        raise RuntimeError(f"upstream JSON error from {url}: {error}")
    return value, final_url, status


def _same_url(left: str, right: str) -> bool:
    return left.rstrip("/").casefold() == right.rstrip("/").casefold()


def _validate(candidate: dict[str, Any], proof: dict[str, Any]) -> set[str]:
    if proof.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"proof schema_version must be {SCHEMA_VERSION}")
    if candidate["county"]["name"] != proof.get("county"):
        raise ValueError("candidate/proof county mismatch")
    if str(candidate["county"]["geoid"]) != str(proof.get("county_geoid")):
        raise ValueError("candidate/proof GEOID mismatch")
    candidate_sha = _sha(candidate)
    if candidate_sha != proof.get("candidate_spec_sha256"):
        raise ValueError(f"candidate spec SHA mismatch: {candidate_sha}")
    if proof.get("stop_before") != "CG-06":
        raise ValueError("CG-05 proof must stop before CG-06")

    prior = proof.get("prior_cg04") or {}
    if prior.get("status") != "PASS" or prior.get("verified_offices") != 18:
        raise ValueError("CG-05 requires the frozen 18-office CG-04 PASS")
    if prior.get("evidence_sha256") != "2d1e5d06563915f7026b272cadad1a43c5c7cab85f8d9f22fef64da67c9304da":
        raise ValueError("unexpected CG-04 evidence SHA")

    gis = proof["gis"]
    families = candidate["district_families"]
    expected_families = ["commissioner", "justice_of_the_peace", "constable"]
    if [str(row["family"]) for row in families] != expected_families:
        raise ValueError("CG-05 district-family order or scope changed")
    approved_provenance = {str(url) for url in gis["approved_candidate_provenance_urls"]}
    for family in families:
        geometry = family["geometry"]
        checks = {
            "service_url": _same_url(str(geometry["service_url"]), str(gis["service_url"])),
            "district_field": geometry["district_field"] == gis["district_field"],
            "district_field_type": geometry["district_field_type"] == gis["district_field_type"],
            "district_keys": [str(value) for value in family["district_keys"]] == list(gis["district_keys"]),
            "official": geometry["official"] is True,
            "numeric": geometry["numeric"] is True,
            "resolver_kind": family["resolver_kind"] == gis["resolver_kind"],
            "provenance_url": str(geometry["endpoint_provenance_url"]) in approved_provenance,
        }
        failed = sorted(key for key, passed in checks.items() if not passed)
        if failed:
            raise ValueError(f"CG-05 frozen adapter mismatch for {family['family']}: {failed}")
    if candidate["controls"]["boundary"]["policy"] != gis["boundary_policy"]:
        raise ValueError("CG-05 boundary policy changed")
    if candidate["controls"]["boundary"]["shared_geometry_families"] != expected_families:
        raise ValueError("CG-05 shared-geometry family contract changed")

    allowed_hosts = {str(host).casefold() for host in gis["official_hosts"]}
    for key in (
        "county_provenance_url",
        "app_public_url",
        "app_item_url",
        "app_data_url",
        "webmap_item_url",
        "webmap_data_url",
        "mapserver_url",
        "service_url",
    ):
        _require_official(str(gis[key]), allowed_hosts)
    return allowed_hosts


def run(candidate_path: Path, proof_path: Path, output_dir: Path | None, *, validate_only: bool) -> dict[str, Any]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    allowed_hosts = _validate(candidate, proof)
    candidate_sha = _sha(candidate)
    proof_sha = _sha(proof)
    if validate_only:
        summary = {
            "status": "VALID",
            "candidate_spec_sha256": candidate_sha,
            "proof_spec_sha256": proof_sha,
            "family_count": len(candidate["district_families"]),
            "district_keys": proof["gis"]["district_keys"],
            "stopped_before": "CG-06",
        }
        print(json.dumps(summary, sort_keys=True))
        return summary

    gis = proof["gis"]
    county_body, final_county_url, county_status = _fetch(str(gis["county_provenance_url"]))
    _require_official(final_county_url, allowed_hosts)
    county_text = _visible_text(county_body)
    missing_fragments = [
        value for value in gis["county_required_fragments"]
        if _normalize_text(str(value)) not in county_text
    ]
    if missing_fragments:
        raise ValueError(f"CG-05 county provenance assertions missing: {missing_fragments}")
    raw_county = county_body.decode("utf-8", errors="replace").casefold()
    if str(gis["app_item_id"]).casefold() not in raw_county:
        raise ValueError("CG-05 county page no longer links the frozen ArcGIS app")

    app_item, final_app_item_url, app_item_status = _json_fetch(
        str(gis["app_item_url"]) + "?" + urlencode({"f": "json"}), allowed_hosts
    )
    app_checks = {
        "id": str(app_item.get("id")) == gis["app_item_id"],
        "owner": str(app_item.get("owner")) == gis["arcgis_owner"],
        "title": str(app_item.get("title")) == gis["app_title"],
        "type": str(app_item.get("type")) == "Web Mapping Application",
        "url": _same_url(str(app_item.get("url", "")), str(gis["app_public_url"])),
        "access": str(app_item.get("access")) == "public",
    }
    failed_app = sorted(key for key, passed in app_checks.items() if not passed)
    if failed_app:
        raise ValueError(f"CG-05 ArcGIS app item mismatch: {failed_app}")

    app_data, final_app_data_url, app_data_status = _json_fetch(
        str(gis["app_data_url"]) + "?" + urlencode({"f": "json"}), allowed_hosts
    )
    app_map = app_data.get("map") or {}
    if str(app_data.get("appItemId")) != gis["app_item_id"]:
        raise ValueError("CG-05 app data item identity changed")
    if str(app_map.get("itemId")) != gis["webmap_item_id"]:
        raise ValueError("CG-05 app no longer resolves to the frozen web map")
    if str((app_map.get("appProxy") or {}).get("mapItemId")) != gis["webmap_item_id"]:
        raise ValueError("CG-05 app proxy web-map identity changed")

    webmap_item, final_webmap_item_url, webmap_item_status = _json_fetch(
        str(gis["webmap_item_url"]) + "?" + urlencode({"f": "json"}), allowed_hosts
    )
    webmap_checks = {
        "id": str(webmap_item.get("id")) == gis["webmap_item_id"],
        "owner": str(webmap_item.get("owner")) == gis["arcgis_owner"],
        "title": str(webmap_item.get("title")) == gis["webmap_title"],
        "type": str(webmap_item.get("type")) == "Web Map",
        "access": str(webmap_item.get("access")) == "public",
    }
    failed_webmap = sorted(key for key, passed in webmap_checks.items() if not passed)
    if failed_webmap:
        raise ValueError(f"CG-05 web-map item mismatch: {failed_webmap}")

    webmap_data, final_webmap_data_url, webmap_data_status = _json_fetch(
        str(gis["webmap_data_url"]) + "?" + urlencode({"f": "json"}), allowed_hosts
    )
    layer_matches = [
        row for row in webmap_data.get("operationalLayers", [])
        if _same_url(str(row.get("url", "")), str(gis["mapserver_url"]))
        and str(row.get("title", "")) == gis["webmap_layer_title"]
        and str(row.get("layerType", "")) == "ArcGISMapServiceLayer"
    ]
    if len(layer_matches) != 1:
        raise ValueError(f"CG-05 Reference Layers web-map mismatch: {len(layer_matches)} matches")
    sublayers = [row for row in layer_matches[0].get("layers", []) if row.get("id") == gis["layer_id"]]
    if len(sublayers) != 1 or str((sublayers[0].get("popupInfo") or {}).get("title")) != gis["layer_name"]:
        raise ValueError("CG-05 precinct sublayer identity changed")

    metadata_url = str(gis["service_url"]) + "?" + urlencode({"f": "json"})
    metadata, final_metadata_url, metadata_status = _json_fetch(metadata_url, allowed_hosts)
    field_matches = [row for row in metadata.get("fields", []) if row.get("name") == gis["district_field"]]
    if len(field_matches) != 1:
        raise ValueError("CG-05 district field is missing or duplicated")
    field = field_matches[0]
    metadata_checks = {
        "layer_id": metadata.get("id") == gis["layer_id"],
        "layer_name": str(metadata.get("name")) == gis["layer_name"],
        "layer_type": str(metadata.get("type")) == "Feature Layer",
        "geometry_type": str(metadata.get("geometryType")) == gis["geometry_type"],
        "field_type": str(field.get("type")) == gis["district_field_type"],
        "field_alias": str(field.get("alias")) == gis["district_field_alias"],
        "capabilities": set(str(metadata.get("capabilities", "")).split(",")) == set(gis["capabilities"]),
    }
    failed_metadata = sorted(key for key, passed in metadata_checks.items() if not passed)
    if failed_metadata:
        raise ValueError(f"CG-05 live layer metadata mismatch: {failed_metadata}")

    query_url = str(gis["service_url"]) + "/query?" + urlencode(
        {
            "where": "1=1",
            "outFields": gis["district_field"],
            "returnGeometry": "false",
            "orderByFields": gis["district_field"],
            "f": "json",
        }
    )
    query, final_query_url, query_status = _json_fetch(query_url, allowed_hosts)
    features = query.get("features", [])
    live_keys = sorted(
        {str(row["attributes"][gis["district_field"]]) for row in features}, key=int
    )
    if live_keys != list(gis["district_keys"]) or len(features) != len(live_keys):
        raise ValueError(f"CG-05 live district keys/features mismatch: {live_keys}/{len(features)}")

    evidence = {
        "status": "PASS",
        "shared_geometry": True,
        "families": [row["family"] for row in candidate["district_families"]],
        "adapter_ids": [row["adapter_id"] for row in candidate["district_families"]],
        "service_url": gis["service_url"],
        "layer_name": metadata["name"],
        "geometry_type": metadata["geometryType"],
        "district_field": gis["district_field"],
        "district_field_alias": field["alias"],
        "district_field_type": field["type"],
        "district_keys": live_keys,
        "feature_count": len(features),
        "resolver_kind": gis["resolver_kind"],
        "failure_scope": "ADAPTER",
        "officeholder_identity_source": "CANONICAL_RELEASE_ONLY",
        "boundary_policy": gis["boundary_policy"],
        "provenance_chain": [
            {"kind": "OFFICIAL_COUNTY_PAGE", "url": final_county_url, "http_status": county_status},
            {"kind": "ARCGIS_APP_ITEM", "url": final_app_item_url, "item_id": gis["app_item_id"], "http_status": app_item_status},
            {"kind": "ARCGIS_APP_DATA", "url": final_app_data_url, "item_id": gis["app_item_id"], "http_status": app_data_status},
            {"kind": "ARCGIS_WEBMAP_ITEM", "url": final_webmap_item_url, "item_id": gis["webmap_item_id"], "http_status": webmap_item_status},
            {"kind": "ARCGIS_WEBMAP_DATA", "url": final_webmap_data_url, "item_id": gis["webmap_item_id"], "http_status": webmap_data_status},
            {"kind": "ARCGIS_FEATURE_LAYER", "url": final_metadata_url, "http_status": metadata_status},
            {"kind": "ARCGIS_KEY_QUERY", "url": final_query_url, "http_status": query_status},
        ],
        "county_text_sha256": hashlib.sha256(county_text.encode("utf-8")).hexdigest(),
        "app_item_sha256": _sha(app_item),
        "app_data_sha256": _sha(app_data),
        "webmap_item_sha256": _sha(webmap_item),
        "webmap_data_sha256": _sha(webmap_data),
        "metadata_sha256": _sha(metadata),
        "query_sha256": _sha(query),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "county": proof["county"],
        "county_geoid": proof["county_geoid"],
        "observed_on": proof["observed_on"],
        "candidate_spec_sha256": candidate_sha,
        "proof_spec_sha256": proof_sha,
        "prior_cg04": proof["prior_cg04"],
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
        "cg05_gis_adapter": evidence,
        "stopped_before": "CG-06",
        "packaged": False,
        "actions": "NOT_YET_RELEASED",
        "production_runtime_changed": False,
    }
    if output_dir is None:
        raise ValueError("--output-dir is required unless --validate-only is set")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "lubbock-cg05-evidence.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "gate": "CG-05",
                "district_keys": live_keys,
                "feature_count": len(features),
                "provenance_hops": len(evidence["provenance_chain"]),
                "stopped_before": "CG-06",
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
