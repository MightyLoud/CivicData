"""Synthetic bounded Texas production-profile controls; no live requests or activation."""
from __future__ import annotations

import base64, copy, hashlib, json, sys, tempfile, unittest, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
for path in (ROOT, TESTS):
    if str(path) not in sys.path: sys.path.insert(0, str(path))

from consumers.empowered_vote import package_catalog, package_source, production_profile, representation_catalog
from test_texas_bounded_contract import bounded_package, receipt
from tools import jurisdiction_package as builder


def resolved_package():
    p = bounded_package()
    for person in p["records"]["people"]:
        for key in ("person_status", "identity_resolution_status", "status", "current_status"):
            person.pop(key, None)
    p["warnings"] = []
    return p


def full_bindings(p):
    jid = p["jurisdiction"]["jurisdiction_id"]
    return [
        {"binding_id":"tx-house","package_jurisdiction_id":jid,"civic_gps_jurisdiction_id":jid,
         "district_adapter_id":"DIST-TX-HOUSE-H2316","district_division_map":{"49":"test-house-49"}},
        {"binding_id":"tx-senate","package_jurisdiction_id":jid,"civic_gps_jurisdiction_id":jid,
         "district_adapter_id":"DIST-TX-SENATE-S2168","district_division_map":{"14":"test-senate-14"}},
    ]


def compact_bindings():
    return [
        {"binding_id":"tx-house","adapter_id":"DIST-TX-HOUSE-H2316","district_division_map":{"49":"test-house-49"}},
        {"binding_id":"tx-senate","adapter_id":"DIST-TX-SENATE-S2168","district_division_map":{"14":"test-senate-14"}},
    ]


def gps(p, senate=True):
    rows = [{"adapter_id":"DIST-TX-HOUSE-H2316","district_key":"49"}]
    if senate: rows.append({"adapter_id":"DIST-TX-SENATE-S2168","district_key":"14"})
    return {"payload":{"jurisdictions":[{"jurisdiction_id":p["jurisdiction"]["jurisdiction_id"]}],"district_assignments":rows}}


def write_package(root, p):
    root.mkdir(parents=True)
    (root/"jurisdiction.json").write_text(builder.canonical_json(p))
    for table in builder.tables_for(p): builder.write_csv(root/(table+".csv"), p["records"].get(table, []))
    (root/"qa_report.json").write_text(builder.canonical_json(p["qa"]))
    files = sorted(x for x in root.iterdir() if x.is_file() and x.name not in {"manifest.json","SHA256SUMS.txt"})
    manifest = {"schema_version":p["schema_version"],"jurisdiction_id":p["jurisdiction"]["jurisdiction_id"],
                "files":[{"path":x.name,"bytes":x.stat().st_size} for x in files]}
    (root/"manifest.json").write_text(builder.canonical_json(manifest))
    files = sorted(x for x in root.iterdir() if x.is_file() and x.name != "SHA256SUMS.txt")
    (root/"SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(x.read_bytes()).hexdigest()}  {x.name}\n" for x in files))


def make_repo(root, p, acceptance):
    src = root/"src"; write_package(src, p)
    archive = root/"artifact.zip"
    with zipfile.ZipFile(archive,"w") as zf:
        for x in sorted(src.iterdir()):
            if x.is_file(): zf.write(x,"Tx_Profile/package/"+x.name)
    raw = archive.read_bytes(); (root/"tx.part01").write_text(base64.b64encode(raw).decode())
    receipt_path = root/"receipt.json"; receipt_path.write_text(builder.canonical_json(acceptance))
    entry = {
        "entry_id":"tx-legislative-two-office-v0.1","profile":"state_legislative_representation",
        "civic_gps_jurisdiction_id":p["jurisdiction"]["jurisdiction_id"],"package_jurisdiction_id":p["jurisdiction"]["jurisdiction_id"],
        "package_schema_version":"0.1","artifact":{"encoding":"base64-parts","parts_glob":"tx.part*",
        "archive_sha256":hashlib.sha256(raw).hexdigest(),"package_subdir":"Tx_Profile/package"},
        "district_bindings":compact_bindings(),"production_profile":{"profile_id":production_profile.PROFILE_ID,
        "acceptance_receipt":{"path":"receipt.json","sha256":hashlib.sha256(receipt_path.read_bytes()).hexdigest()}}}
    catalog = root/"catalog.json"; catalog.write_text(builder.canonical_json({"catalog_version":"0.1","entries":[entry]}))
    return src, catalog


class TxProductionProfileTests(unittest.TestCase):
    def test_default_catalog_not_activated(self):
        rows = package_catalog.load_catalog()["entries"]
        self.assertFalse(any(r.get("production_profile") or r.get("profile")=="state_legislative_representation" for r in rows))

    def test_profile_loader_preserves_strict_default_contract(self):
        p = resolved_package(); acceptance = receipt(package=p)
        with tempfile.TemporaryDirectory() as tmp:
            src, _ = make_repo(Path(tmp), p, acceptance)
            with self.assertRaises(package_source.PackageContractError) as err: package_source.load_jurisdiction_package(src)
            self.assertEqual(err.exception.code,"PACKAGE_BLOCKING_GAPS_PRESENT")
            loaded = production_profile.load_profile_package(src,profile_id=production_profile.PROFILE_ID,
                        acceptance_receipt=acceptance,bindings=full_bindings(p))
            self.assertEqual(loaded["qa"]["blocking_gap_count"],5); self.assertEqual(loaded["qa"]["address_tests"],[])

    def test_provisional_identity_stays_blocking(self):
        p = bounded_package(); acceptance = receipt(package=p)
        with tempfile.TemporaryDirectory() as tmp:
            src, _ = make_repo(Path(tmp), p, acceptance)
            with self.assertRaises(production_profile.ProductionProfileError) as err:
                production_profile.load_profile_package(src,profile_id=production_profile.PROFILE_ID,
                    acceptance_receipt=acceptance,bindings=full_bindings(p))
            self.assertEqual(err.exception.code,"PRODUCTION_PROFILE_PUBLIC_IDENTITY_UNRESOLVED")

    def test_receipt_chain_drift_rejected(self):
        p = resolved_package(); acceptance = receipt(package=p); acceptance["scope"]["office_ids"][0] = "wrong"
        acceptance.pop("deterministic_sha256",None); acceptance["deterministic_sha256"] = hashlib.sha256(builder.canonical_json(acceptance).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            src, _ = make_repo(Path(tmp), p, acceptance)
            with self.assertRaises(production_profile.ProductionProfileError) as err:
                production_profile.load_profile_package(src,profile_id=production_profile.PROFILE_ID,
                    acceptance_receipt=acceptance,bindings=full_bindings(p))
            self.assertEqual(err.exception.code,"PRODUCTION_PROFILE_RECEIPT_CHAIN_DRIFT")

    def test_public_route_requires_both_bindings_atomically(self):
        p = resolved_package(); acceptance = receipt(package=p)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, catalog = make_repo(root,p,acceptance)
            ok = representation_catalog.build_representation_from_catalog("TX",gps(p),repo_root=root,catalog_path=catalog,
                    profile="state_legislative_representation")
            self.assertEqual(ok["status"],"PASS"); self.assertTrue(ok["publication_eligible"]); self.assertFalse(ok["complete_jurisdiction"])
            self.assertEqual(len(ok["projections"]),2); self.assertEqual(ok["production_profile_id"],production_profile.PROFILE_ID)
            bad = representation_catalog.build_representation_from_catalog("TX",gps(p,False),repo_root=root,catalog_path=catalog,
                    profile="state_legislative_representation")
            self.assertEqual(bad["status"],"FAIL-CLOSED"); self.assertEqual(bad["error"],"CIVIC_GPS_REQUIRED_DISTRICT_MISSING"); self.assertNotIn("projections",bad)

    def test_profile_cannot_drive_full_essentials(self):
        p = resolved_package(); acceptance = receipt(package=p)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, catalog = make_repo(root,p,acceptance)
            result = package_catalog.build_essentials_from_catalog("TX",gps(p),repo_root=root,catalog_path=catalog,
                        profile="state_legislative_representation")
            self.assertEqual(result["error"],"PACKAGE_PRODUCTION_PROFILE_NOT_FULL_ESSENTIALS")


if __name__ == "__main__": unittest.main(verbosity=2)
