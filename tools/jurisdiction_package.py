#!/usr/bin/env python3
"""Build and validate deterministic CivicData jurisdiction packages."""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

TABLES = ("divisions","bodies","offices","people","role_terms","leadership_roles","identifier_crosswalk")


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def validate(pkg):
    errors=[]
    if pkg.get("schema_version") != "0.1": errors.append("schema_version")
    qa=pkg.get("qa",{})
    if qa.get("parity_ok") is not True: errors.append("parity_ok")
    if qa.get("qa_fail_count") != 0: errors.append("qa_fail_count")
    if qa.get("blocking_gap_count") != 0: errors.append("blocking_gap_count")
    if len(qa.get("address_tests",[])) < 2 or any(x.get("result") is not True for x in qa.get("address_tests",[])): errors.append("address_tests")
    sources={x.get("source_id") for x in pkg.get("provenance",{}).get("source_evidence",[])}
    if None in sources: errors.append("source_id")
    ids=set()
    for table in TABLES:
        for row in pkg.get("records",{}).get(table,[]):
            key=next((k for k in row if k.endswith("_id") and k not in {"jurisdiction_id","body_id","person_id","office_id","represented_division_id"}),None)
            if key and row[key] in ids: errors.append("duplicate_id:"+str(row[key]))
            if key: ids.add(row[key])
    for rt in pkg.get("records",{}).get("role_terms",[]):
        if not rt.get("person_id") or not rt.get("office_id"): errors.append("role_term_fk")
    if not pkg.get("provenance",{}).get("source_evidence"): errors.append("provenance")
    return sorted(set(errors))


def write_csv(path, rows):
    keys=sorted({k for r in rows for k in r})
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(rows)


def build(pkg, out):
    errs=validate(pkg)
    if errs: raise SystemExit("validation failed: "+", ".join(errs))
    out.mkdir(parents=True,exist_ok=True)
    (out/"jurisdiction.json").write_text(canonical_json(pkg),encoding="utf-8")
    for table in TABLES: write_csv(out/(table+".csv"),pkg["records"].get(table,[]))
    (out/"qa_report.json").write_text(canonical_json(pkg["qa"]),encoding="utf-8")
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name not in {"manifest.json","SHA256SUMS.txt"})
    manifest={"schema_version":"0.1","jurisdiction_id":pkg["jurisdiction"]["jurisdiction_id"],"files":[{"path":p.name,"bytes":p.stat().st_size} for p in files]}
    (out/"manifest.json").write_text(canonical_json(manifest),encoding="utf-8")
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name!="SHA256SUMS.txt")
    sums="".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files)
    (out/"SHA256SUMS.txt").write_text(sums,encoding="utf-8")


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("input",type=Path); ap.add_argument("output",type=Path); ap.add_argument("--validate-only",action="store_true"); a=ap.parse_args()
    pkg=json.loads(a.input.read_text(encoding="utf-8")); errs=validate(pkg)
    if errs: raise SystemExit("validation failed: "+", ".join(errs))
    if not a.validate_only: build(pkg,a.output)
    print("PASS")
if __name__=="__main__": main()
