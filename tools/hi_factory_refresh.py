#!/usr/bin/env python3
"""Build the bounded 2026-09-19 HI review candidate from governed inputs."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

import jurisdiction_package_strict as jp
import jurisdiction_package as legacy

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidates/hi/hi-refresh-20260919"
SNAPSHOT = CANDIDATE / "source/hi-refresh-20260919.json"
COUNTIES = ("hawaii", "honolulu", "kalawao", "kauai", "maui")
SEATS = dict(zip(COUNTIES, (10, 10, 0, 8, 10)))
BASE_HASHES = {
    "hawaii": "b64510374fe99dcb67e7de3044992ab1b61c9d70c31935c60314a7e6a8f0310c",
    "honolulu": "aefb7b12ae93cc4f0fe84b95711aaced248dc18ad686a2cea52e2986b98bfa1b",
    "kalawao": "946a7ff938e0c2a6b6e7efe0e5ce626ffde017c5ab78053bc3da8516bcadc6db",
    "kauai": "fac5f85e589d237252f7067563f90f73c09f566237967201ef30c994d524081e",
    "maui": "9458ec4ce0498daf88bd6a55f88e48c15c95f48b9c1a97ae07b4ffb52acf2110",
}
TABLES = {
    "divisions": "02_Division", "bodies": "03_Body", "offices": "04_Office",
    "people": "05_Person", "role_terms": "06_RoleTerm",
    "leadership_roles": "07_LeadershipRole", "identifier_crosswalk": "10_IdentifierCrosswalk",
}
DAY = "2026-09-19"


def rows(snapshot, table, jid):
    block = snapshot["tables"][table]
    result = []
    for item in block["rows"]:
        record = item["values"]
        if list(record) != block["columns"]:
            raise ValueError(f"column drift: {table}:{item['source_row']}")
        if record.get("jurisdiction_id") == jid:
            result.append({k: v for k, v in record.items() if v is not None and v != ""})
    return result


def baseline(county):
    stem = county.title() + "_County_Jurisdiction_Package_v0.1_2026-08-23.zip"
    directory = ROOT / "data/packages/hi" / (county + "-county")
    parts = sorted(directory.glob(stem + ".b64.part*"))
    if not parts:
        raise ValueError("missing baseline: " + county)
    data = base64.b64decode(b"".join(b"".join(p.read_bytes().split()) for p in parts), validate=True)
    if hashlib.sha256(data).hexdigest() != BASE_HASHES[county]:
        raise ValueError("baseline hash drift: " + county)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.endswith("/jurisdiction.json")]
        if len(names) != 1:
            raise ValueError("baseline inventory")
        return json.loads(z.read(names[0]))


def package(snapshot, county):
    jid = f"jurisdiction-hi-{county}-county"
    tracker, = rows(snapshot, "00_Batch_Status", jid)
    for field in ("complete_flag", "parity_ok", "release_ready", "freshness_ok"):
        if tracker.get(field) is not True:
            raise ValueError(f"tracker gate {county}:{field}")
    if tracker.get("workflow_status") != "9.00 Complete":
        raise ValueError("workflow status: " + county)
    old = baseline(county)
    jurisdiction, = rows(snapshot, "01_Jurisdiction", jid)
    records = {name: rows(snapshot, tab, jid) for name, tab in TABLES.items()}
    # No jurisdiction, office, division, body, leadership or identifier redesign.
    if jurisdiction != old["jurisdiction"]:
        raise ValueError("jurisdiction drift: " + county)
    for name in TABLES:
        key = jp.PRIMARY_KEYS[name]
        if {r[key] for r in records[name]} != {r[key] for r in old["records"][name]}:
            raise ValueError("identity drift: " + name)
        if name not in ("people", "role_terms") and records[name] != old["records"][name]:
            raise ValueError("structure drift: " + name)
    old_terms = {r["role_term_id"]: r for r in old["records"]["role_terms"]}
    for term in records["role_terms"]:
        previous = old_terms[term["role_term_id"]]
        for field in ("person_id", "office_id", "body_id", "status", "valid_from", "valid_to"):
            if term.get(field) != previous.get(field):
                raise ValueError("holder/interval drift: " + term["role_term_id"])
        expected_selection = "APPOINTED" if term["role_term_id"] == "role-hi-maui-kauanoe-batangan" else previous.get("selection_type")
        if term.get("selection_type") != expected_selection:
            raise ValueError("selection method drift: " + term["role_term_id"])
    capacity = sum(o.get("seats", 0) for o in records["offices"] if o.get("status") == "ACTIVE")
    current = sum(t.get("status") == "CURRENT" for t in records["role_terms"])
    if capacity != SEATS[county] or current != capacity:
        raise ValueError("seat parity: " + county)
    evidence = rows(snapshot, "08_SourceEvidence", jid)
    assertions = rows(snapshot, "09_SourceAssertion", jid)
    checks = rows(snapshot, "13_QA", jid)
    addresses = rows(snapshot, "12_AddressTest", jid)
    warnings = []
    for warning in old["warnings"]:
        warnings.append({**warning, "blocking": False, "jurisdiction_id": jid,
                         "entity_type": "Jurisdiction", "entity_id": jid})
    warnings += [g for g in rows(snapshot, "11_KnownGap", jid) if g.get("status") == "OPEN"]
    counts = {**{n: len(v) for n, v in records.items()}, "source_evidence": len(evidence),
              "source_assertions": len(assertions), "checks": len(checks),
              "address_tests": len(addresses), "warnings": len(warnings)}
    result = {"schema_version": "0.1", "jurisdiction": jurisdiction, "records": records,
              "provenance": {"source_evidence": evidence, "source_assertions": assertions},
              "qa": {"parity_ok": True, "qa_fail_count": sum(q.get("result") is not True for q in checks),
                     "blocking_gap_count": sum(w.get("blocking") is True for w in warnings),
                     "address_tests": addresses, "checks": checks, "source_counts": counts,
                     "tracker_complete": True, "release_ready": True,
                     "roster_verified_on": DAY, "publication_status": "REVIEW_CANDIDATE",
                     "review_scope": "Roster freshness and reference integrity; historical address/geography checks retained with original dates."},
              "warnings": warnings}
    errors = jp.validate(result) + legacy.validate(result)
    if errors:
        raise ValueError(county + ": " + ", ".join(errors))
    return result


def archive_bytes(directory, prefix):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(directory.iterdir()):
            info = zipfile.ZipInfo(prefix + "/package/" + path.name, (2026, 9, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, path.read_bytes())
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    snapshot = json.loads(SNAPSHOT.read_text())
    expected = [f"jurisdiction-hi-{c}-county" for c in COUNTIES]
    if snapshot.get("snapshot_contract") != "civicdata.hi_factory_snapshot.v0.1" or snapshot.get("authorized_jurisdiction_ids") != expected:
        raise ValueError("snapshot scope")
    results = []
    for county in COUNTIES:
        pkg = package(snapshot, county)
        destination = CANDIDATE / "normalized" / pkg["jurisdiction"]["jurisdiction_id"]
        stem = county.title() + "_County_Jurisdiction_Package_v0.1_2026-09-19"
        archive = CANDIDATE / "packages" / (county + "-county") / (stem + ".zip")
        part = archive.with_name(archive.name + ".b64.part01")
        if args.verify:
            errors = jp.verify_package(destination)
            if errors or json.loads((destination / "jurisdiction.json").read_text()) != pkg:
                raise ValueError("package mismatch: " + county + ": " + str(errors))
        else:
            jp.build(pkg, destination)
        data = archive_bytes(destination, stem)
        encoded = base64.b64encode(data).decode("ascii") + "\n"
        if args.verify:
            if archive.read_bytes() != data or part.read_text() != encoded:
                raise ValueError("archive reproducibility: " + county)
        else:
            archive.write_bytes(data)
            part.write_text(encoded)
        results.append({"jurisdiction_id": pkg["jurisdiction"]["jurisdiction_id"],
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                        "package": archive.relative_to(ROOT).as_posix(),
                        "counts": pkg["qa"]["source_counts"], "status": "PASS"})
    report = {"status": "PASS", "batch_id": "HI-REFRESH-002", "publication_status": "REVIEW_CANDIDATE",
              "captured_on": DAY, "baseline_hashes": BASE_HASHES,
              "source_snapshot_sha256": hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(),
              "packages": results}
    target = CANDIDATE / "review/hi-refresh-20260919-validation.json"
    text = jp.canonical_json(report)
    if args.verify:
        if target.read_text() != text:
            raise ValueError("validation report mismatch")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
