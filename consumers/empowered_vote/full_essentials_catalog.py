#!/usr/bin/env python3
"""Jurisdiction-agnostic governed Full Essentials consumer."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from consumers.empowered_vote import live_civic_gps, package_catalog, package_source


def _fail(address: str, code: str, detail: str | None = None) -> dict[str, Any]:
    out={"status":"FAIL-CLOSED","consumer_gate":"EV-IMP-007","input_address":address,"error":code,"canonical_writes":0}
    if detail: out["detail"]=detail
    return out


def _id(row: dict[str, Any], *keys: str) -> str | None:
    return next((str(row[k]) for k in keys if row.get(k) not in (None,"")), None)


def _name(row: dict[str, Any], *keys: str) -> str | None:
    return next((str(row[k]) for k in keys if row.get(k) not in (None,"")), None)


def _first_source(row: dict[str, Any]) -> str | None:
    if row.get("source_id"): return str(row["source_id"])
    value=row.get("source_ids")
    if isinstance(value,list): return str(value[0]) if value else None
    if isinstance(value,str) and value.strip(): return value.split(";",1)[0].strip()
    return None


def _source(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row: return None
    return {"source_id":row.get("source_id") or row.get("Source_ID"),"title":row.get("title") or row.get("Title"),"publisher":row.get("publisher") or row.get("Publisher"),"url":row.get("url") or row.get("Source_URL_or_File"),"authority_level":row.get("authority_level") or row.get("Authority_Level"),"verification_status":row.get("verification_status") or row.get("Verification_Status"),"verified_as_of":row.get("verified_as_of") or row.get("Verified_As_Of_ISO")}


def _is_current(row: dict[str, Any]) -> bool:
    return str(row.get("status") or row.get("currentness_status") or "").upper() in {"CURRENT","CURRENT_VERIFIED"}


def build_full_essentials_from_civic_gps_result(package: dict[str, Any], address: str, civic_gps_result: Any, *, binding: dict[str, Any]) -> dict[str, Any]:
    try: package_source.require_full_essentials(package)
    except package_source.PackageContractError as exc: return _fail(address,exc.code,exc.detail)
    if package.get("jurisdiction",{}).get("jurisdiction_id") != binding.get("package_jurisdiction_id"):
        return _fail(address,"CIVIC_GPS_PACKAGE_BINDING_UNSUPPORTED")
    geo=live_civic_gps.normalize_civic_gps_result(address,civic_gps_result)
    if geo.get("status")!="PASS": return _fail(address,str(geo.get("error") or "CIVIC_GPS_GEOGRAPHY_INVALID"),geo.get("detail"))
    civic_id=str(binding.get("civic_gps_jurisdiction_id") or "")
    if not civic_id or civic_id not in geo["jurisdiction_ids"]: return _fail(address,"CIVIC_GPS_JURISDICTION_NOT_ACTIVE",civic_id or None)

    records=package["records"]
    divisions=[r for r in records.get("divisions",[]) if isinstance(r,dict)]
    base=package.get("jurisdiction",{}).get("division_id")
    if not base and len(divisions)==1: base=_id(divisions[0],"division_id","id")
    known={_id(r,"division_id","id") for r in divisions}
    if not base or str(base) not in known: return _fail(address,"PACKAGE_JURISDICTION_DIVISION_MISSING")
    applicable={str(base)}
    if binding.get("district_adapter_id"):
        adapter=str(binding["district_adapter_id"]); key=geo["district_assignments"].get(adapter)
        if key is None: return _fail(address,"CIVIC_GPS_REQUIRED_DISTRICT_MISSING",adapter)
        template=binding.get("division_template")
        if not template: return _fail(address,"CIVIC_GPS_DIVISION_TEMPLATE_MISSING",adapter)
        district=str(template).format(district_key=key)
        if district not in known: return _fail(address,"CIVIC_GPS_DISTRICT_NOT_IN_PACKAGE",district)
        applicable.add(district)

    sources={str(r.get("source_id") or r.get("Source_ID")):r for r in package.get("provenance",{}).get("source_evidence",[]) if isinstance(r,dict) and (r.get("source_id") or r.get("Source_ID"))}
    people={_id(r,"person_id","id"):r for r in records.get("people",[]) if isinstance(r,dict) and _id(r,"person_id","id")}
    terms=[r for r in records.get("role_terms",[]) if isinstance(r,dict) and _is_current(r)]
    leadership=[r for r in records.get("leadership_roles",[]) if isinstance(r,dict) and str(r.get("status") or r.get("currentness_status") or "CURRENT").upper() in {"CURRENT","CURRENT_VERIFIED"}]
    offices=[]; office_ids=set()
    for office in records.get("offices",[]):
        if not isinstance(office,dict): continue
        div=_id(office,"represented_division_id","geography_id","division_id")
        if div not in applicable: continue
        oid=_id(office,"office_id","id")
        if not oid: return _fail(address,"PACKAGE_OFFICE_ID_MISSING")
        office_ids.add(oid); ots=[t for t in terms if _id(t,"office_id")==oid]; holders=[]
        for term in ots:
            pid=_id(term,"person_id"); person=people.get(pid,{}) if pid else {}; roles=[]
            for lead in leadership:
                if pid and _id(lead,"person_id")!=pid: continue
                lo=_id(lead,"office_id")
                if lo and lo!=oid: continue
                role=_name(lead,"role","role_title")
                if role: roles.append(role)
            holders.append({"person_id":pid,"name":_name(person,"name","canonical_name","Canonical_Name") if person else None,"currentness_status":term.get("currentness_status") or term.get("status"),"leadership_roles":sorted(set(roles)),"selection_method":term.get("selection_method") or term.get("selection_type"),"term_start":term.get("term_start") or term.get("valid_from") or term.get("start_date"),"term_end":term.get("term_end") or term.get("valid_to") or term.get("end_date"),"term_end_basis":term.get("term_end_basis") or term.get("interval_semantics")})
        holders.sort(key=lambda r:(str(r.get("name") or ""),str(r.get("person_id") or "")))
        sid=_first_source(ots[0]) if ots else _first_source(office)
        model={"office_id":oid,"office_name":_name(office,"name","office_name","Canonical_Name"),"seat_type":_name(office,"classification_or_role","office_type","role"),"division_id":div,"current_status":office.get("current_status") or office.get("status"),"provenance":_source(sources.get(str(sid))) if sid else None}
        if len(holders)==1:
            holder=dict(holders[0]); holder["leadership_role"]=holder["leadership_roles"][0] if holder["leadership_roles"] else None; model["holder"]=holder
        else: model["holder"]=None; model["holders"]=holders
        offices.append(model)
    if not offices: return _fail(address,"PACKAGE_APPLICABLE_OFFICES_EMPTY")

    contests=[]; contest_ids=set()
    for contest in records.get("contests",[]):
        if contest.get("office_id") not in office_ids: continue
        cid=str(contest["contest_id"]); contest_ids.add(cid); srcs=contest.get("source_ids") or []; sid=srcs[0] if isinstance(srcs,list) and srcs else None
        contests.append({"contest_id":cid,"contest_name":contest.get("contest_name"),"election_id":contest.get("election_id"),"office_id":contest.get("office_id"),"provenance":_source(sources.get(str(sid))) if sid else None,"candidates":[]})
    index={r["contest_id"]:r for r in contests}
    for cand in records.get("candidacies",[]):
        cid=str(cand.get("contest_id"))
        if cid not in contest_ids: continue
        index[cid]["candidates"].append({"candidacy_id":cand.get("candidacy_id"),"candidate_source_id":cand.get("source_candidate_id"),"person_id":cand.get("person_id"),"candidate_name":cand.get("candidate_name"),"ballot_name":cand.get("ballot_name"),"outcome":cand.get("outcome"),"votes":cand.get("votes"),"vote_share":cand.get("vote_share"),"is_write_in_bucket":cand.get("candidate_kind")=="WRITE_IN_BUCKET","provenance":_source(sources.get(str(cand.get("source_id"))))})
    for contest in contests: contest["candidates"].sort(key=lambda r:(0 if r.get("outcome")=="WINNER" else 1,str(r.get("candidate_name") or ""),str(r.get("candidate_source_id") or "")))
    offices.sort(key=lambda r:(str(r.get("seat_type") or ""),str(r.get("office_name") or ""))); contests.sort(key=lambda r:(str(r.get("election_id") or ""),str(r.get("contest_name") or "")))
    out={"status":"PASS","consumer_gate":"EV-IMP-007","package_schema_version":package.get("schema_version"),"input_address":address,"matched_address":geo.get("matched_address"),"address_resolution_source":"CIVIC_GPS_LIVE","resolved_jurisdictions":geo["jurisdiction_ids"],"district_assignments":geo["district_assignments"],"jurisdiction":package.get("jurisdiction"),"applicable_offices":offices,"recent_certified_contests":contests,"warnings":package.get("warnings",[]),"canonical_writes":0}
    out["deterministic_sha256"]=package_source.sha256_bytes(package_source.canonical_json_bytes(out)); return out


def build_full_essentials_from_catalog(address: str, civic_gps_result: dict[str, Any], *, repo_root: str | Path, catalog_path: str | Path = package_catalog.DEFAULT_CATALOG, profile: str = "municipal_essentials") -> dict[str, Any]:
    try:
        catalog=package_catalog.load_catalog(catalog_path); entry=package_catalog.select_entry(catalog,civic_gps_result,profile=profile); package=package_catalog.reconstruct_package(entry,repo_root)
    except package_catalog.PackageCatalogError as exc: return _fail(address,exc.code,exc.detail)
    out=build_full_essentials_from_civic_gps_result(package,address,civic_gps_result,binding=package_catalog.binding_from_entry(entry))
    if out.get("status")=="PASS":
        out["package_catalog_entry_id"]=entry["entry_id"]; out.pop("deterministic_sha256",None); out["deterministic_sha256"]=package_source.sha256_bytes(package_source.canonical_json_bytes(out))
    return out
