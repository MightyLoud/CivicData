#!/usr/bin/env python3
from __future__ import annotations

import base64, hashlib, importlib.util, json, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"consumers"/"empowered_vote"/"package_source.py"
PARTS=ROOT/"data"/"packages"/"wa"/"tacoma"
PROOF=ROOT/"data"/"reference"/"wa"/"tacoma"/"EV-IMP-002_Tacoma_Stacked_Proof_2026-08-23.json"
ZIP_SHA="2c6219303eff3f49b4202f72048910ba970cd65353032b6bfda2975791701d53"
spec=importlib.util.spec_from_file_location("ev_package_source",SRC); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def package_bytes():
    files=sorted(PARTS.glob("Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip.b64.part*"))
    assert files
    raw=base64.b64decode("".join(p.read_text().strip() for p in files),validate=True)
    assert hashlib.sha256(raw).hexdigest()==ZIP_SHA
    return raw

def run():
    proof=json.loads(PROOF.read_text()); assert proof["status"]=="PASS" and proof["package_schema_version"]=="0.2"
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); archive=root/"tacoma.zip"; archive.write_bytes(package_bytes()); assert zipfile.is_zipfile(archive)
        with zipfile.ZipFile(archive) as z: z.extractall(root)
        p=root/"Tacoma_Jurisdiction_Package_v0.2_2026-08-23"/"package"
        before=mod.directory_digest(p); pkg=mod.load_jurisdiction_package(p); assert before==mod.directory_digest(p)
        assert mod.package_capabilities(pkg)=={"representation":True,"elections":True,"full_essentials":True,"read_only":True}
        assert (len(pkg["records"]["offices"]),len(pkg["records"]["people"]),len(pkg["records"]["elections"]),len(pkg["records"]["contests"]),len(pkg["records"]["candidacies"]))==(10,17,2,9,26)
        market=mod.build_essentials_from_package(pkg,"747 Market Street, Tacoma, WA 98402")
        assert market["status"]=="PASS" and market["canonical_writes"]==0
        assert market["district_assignments"]["DIST-WA-TACOMA-COUNCIL"]=="2"
        assert (len(market["applicable_offices"]),len(market["recent_certified_contests"]),sum(len(c["candidates"]) for c in market["recent_certified_contests"]))==(6,5,15)
        assert market["deterministic_sha256"]==mod.build_essentials_from_package(pkg,"747 Market Street, Tacoma, WA 98402")["deterministic_sha256"]
        wapato=mod.build_essentials_from_package(pkg,"6500 South Sheridan Avenue, Tacoma, WA 98408"); assert len(wapato["applicable_offices"])==6 and wapato["district_assignments"]["DIST-WA-TACOMA-COUNCIL"]=="5"
        lakewood=mod.build_essentials_from_package(pkg,"6000 Main St SW, Lakewood, WA 98499"); assert lakewood["applicable_offices"]==[] and lakewood["recent_certified_contests"]==[]
        unsupported=mod.build_essentials_from_package(pkg,"1 Made Up Road, Tacoma, WA"); assert unsupported["status"]=="FAIL-CLOSED" and unsupported["error"]=="ADDRESS_NOT_IN_GOVERNED_PACKAGE" and unsupported["canonical_writes"]==0
        named=[c for c in pkg["records"]["candidacies"] if c["candidate_kind"]=="PERSON"]; writeins=[c for c in pkg["records"]["candidacies"] if c["candidate_kind"]=="WRITE_IN_BUCKET"]
        assert len(named)==17 and len(writeins)==9 and all(c.get("person_id") for c in named) and all(c.get("person_id") is None for c in writeins)
    print(json.dumps({"status":"PASS","real_tacoma_package":"PASS","full_essentials":"PASS","address_controls":"3/3","determinism":"PASS","named_candidates":17,"write_in_buckets":9,"canonical_writes":0},sort_keys=True))

if __name__=="__main__": run()
