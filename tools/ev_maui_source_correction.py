#!/usr/bin/env python3
"""Reproduce a held Maui correction without replacing the governed package."""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consumers.empowered_vote import package_catalog, package_source
from tools import jurisdiction_package

GATE = "EV-MAUI-SOURCE-CORRECTION-001"
CORRECTION = Path("previews/ev/maui_source_correction.v0.1.json")
CONFIG = Path("previews/ev/maui_countywide.v0.1.json")
PACKAGE_ID = "jurisdiction-hi-maui-county"
ROLE_ID = "role-hi-maui-kauanoe-batangan"
PERSON_ID = "person-hi-maui-kauanoe-batangan"
OFFICE_ID = "office-hi-maui-council-kahului"
BASE_ARTIFACT = {
    "encoding": "base64-parts",
    "parts_glob": "data/packages/hi/maui-county/Maui_County_Jurisdiction_Package_v0.1_2026-08-23.zip.b64.part*",
    "archive_sha256": "9458ec4ce0498daf88bd6a55f88e48c15c95f48b9c1a97ae07b4ffb52acf2110",
    "package_subdir": "Maui_County_Jurisdiction_Package_v0.1_2026-08-23/package",
}
CANDIDATE_SUBDIR = "Maui_County_Preview_Package_v0.1_2026-09-12/package"
CANDIDATE_PART = Path("previews/ev/maui/Maui_County_Preview_Package_v0.1_2026-09-12.zip.b64.part01")
SOURCE_URLS = {
    "mayor-appointment": "https://www.mauicounty.gov/m/newsflash/home/detail/18065",
    "council-seating": "https://mauicounty.us/press-release/batangan-seated-as-councilmember-changes-to-committees-adopted/",
    "state-elections": "https://elections.hawaii.gov/resources/elected-officials/",
}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def entry(artifact):
    return {"entry_id": "held-maui-correction", "artifact": artifact,
            "package_jurisdiction_id": PACKAGE_ID, "package_schema_version": "0.1"}


def read_archive(root, artifact):
    parts = sorted(root.glob(artifact["parts_glob"]))
    require(bool(parts), "MAUI_ARCHIVE_PARTS_MISSING")
    raw = base64.b64decode("".join(p.read_text().strip() for p in parts), validate=True)
    require(sha(raw) == artifact["archive_sha256"], "MAUI_ARCHIVE_HASH_MISMATCH")
    return raw


def corrected_package(base, correction):
    """The delta is fixed; the receipt cannot introduce arbitrary field edits."""
    require(correction.get("gate") == GATE
            and correction.get("mode") == "HELD_PREVIEW_ONLY"
            and correction.get("publication_eligible") is False
            and correction.get("canonical_writes") == 0
            and correction.get("source_artifact") == BASE_ARTIFACT,
            "MAUI_CORRECTION_CONTRACT_INVALID")
    require(correction.get("target") == {
        "role_term_id": ROLE_ID, "person_id": PERSON_ID, "office_id": OFFICE_ID,
        "field": "selection_type", "before": "ELECTED", "after": "APPOINTED"},
        "MAUI_CORRECTION_TARGET_INVALID")
    require(base["jurisdiction"]["jurisdiction_id"] == PACKAGE_ID,
            "MAUI_CORRECTION_PACKAGE_MISMATCH")
    observations = correction.get("raw_observations")
    require(isinstance(observations, list) and len(observations) == 3
            and {r.get("key") for r in observations} == set(SOURCE_URLS),
            "MAUI_CORRECTION_RAW_SET_INVALID")
    package = copy.deepcopy(base)
    targets = [r for r in package["records"]["role_terms"] if r["role_term_id"] == ROLE_ID]
    require(len(targets) == 1, "MAUI_CORRECTION_ROLE_MISSING")
    role = targets[0]
    require(role["person_id"] == PERSON_ID and role["office_id"] == OFFICE_ID
            and role["selection_type"] == "ELECTED", "MAUI_CORRECTION_PRECONDITION_FAILED")
    require(not any(k in role for k in ("start_date", "end_date", "term_start", "term_end",
                                       "term_start_date", "term_end_date", "selection_date")),
            "MAUI_CORRECTION_INTERVAL_DRIFT")
    sources, assertions = [], []
    for observation in observations:
        key = observation["key"]
        require(observation.get("url") == SOURCE_URLS[key]
                and observation.get("accessed_at") == "2026-09-12"
                and observation.get("authority_level") == "PRIMARY_OFFICIAL"
                and observation.get("normalized_selection_type") == "APPOINTED"
                and isinstance(observation.get("observed_text"), str)
                and "appoint" in observation["observed_text"].lower(),
                "MAUI_CORRECTION_RAW_INVALID")
        source_id = f"src-hi-maui-batangan-{key}-20260912"
        assertion_id = f"asrt-hi-maui-batangan-{key}-20260912"
        sources.append(source_id)
        assertions.append(assertion_id)
        package["provenance"]["source_evidence"].append({
            "source_id": source_id, "jurisdiction_id": PACKAGE_ID,
            "batch_id": GATE, "url": observation["url"],
            "title": observation["title"], "publisher": observation["publisher"],
            "source_type": observation["source_type"], "authority_level": "PRIMARY_OFFICIAL",
            "accessed_at": observation["accessed_at"], "locator": observation["locator"],
            "supports_entity_type": "RoleTerm", "supports_entity_id": ROLE_ID,
            "notes": "Held preview correction of appointment method; exact tenure dates remain unasserted.",
        })
        package["provenance"]["source_assertions"].append({
            "assertion_id": assertion_id, "jurisdiction_id": PACKAGE_ID,
            "batch_id": GATE, "source_id": source_id, "source_locator": observation["locator"],
            "subject_type": "RoleTerm", "subject_id": ROLE_ID,
            "predicate": "selection_type", "object_type": "ENUM", "object_value": "APPOINTED",
            "observed_text": observation["observed_text"], "confidence": "HIGH",
            "normalized_status": "NORMALIZED",
            "notes": "The elected office's normal selection method is distinct from this holder's appointment.",
        })
    role["selection_type"] = "APPOINTED"
    role["source_ids"] += ";" + ";".join(sources)
    role["assertion_ids"] += ";" + ";".join(assertions)
    role["notes"] += " Appointment selection corrected under " + GATE + "; no exact interval asserted."
    # Original row timestamps and historical QA are retained, not relabeled as a fresh full recheck.
    package_source._validate_package_shape(package)
    return package


def package_bytes(package):
    """Use the existing package builder, with a portable deterministic ZIP envelope."""
    with tempfile.TemporaryDirectory(prefix="maui-held-build-") as tmp:
        directory = Path(tmp) / "package"
        jurisdiction_package.build(package, directory)
        loaded = package_source.load_jurisdiction_package(directory)
        require(loaded == package, "MAUI_CORRECTION_ROUNDTRIP_DRIFT")
        # Check all CSV rows against their JSON values, not just file lengths.
        for table in jurisdiction_package.BASE_TABLES:
            with (directory / (table + ".csv")).open(newline="") as stream:
                reader = csv.DictReader(stream)
                actual, fields = list(reader), reader.fieldnames or []
            expected = [{k: "" if row.get(k) is None else str(row[k]) for k in fields}
                        for row in package["records"][table]]
            require(actual == expected, "MAUI_CORRECTION_CSV_PARITY_FAILED:" + table)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in sorted(directory.iterdir()):
                info = zipfile.ZipInfo(CANDIDATE_SUBDIR + "/" + path.name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        return stream.getvalue()


def rebuild(root):
    raw = (root / CORRECTION).read_bytes()
    correction = json.loads(raw)
    base = package_catalog.reconstruct_package(entry(BASE_ARTIFACT), root)
    candidate = corrected_package(base, correction)
    return candidate, package_bytes(candidate), sha(raw)


def verify_candidate(root, binding):
    candidate, rebuilt, correction_sha = rebuild(root)
    require(binding.get("source_correction") == {"path": CORRECTION.as_posix(), "sha256": correction_sha},
            "MAUI_CORRECTION_RECEIPT_HASH_MISMATCH")
    artifact = binding.get("artifact") or {}
    require(artifact == {"encoding": "base64-parts", "parts_glob": CANDIDATE_PART.as_posix(),
                         "archive_sha256": sha(rebuilt), "package_subdir": CANDIDATE_SUBDIR},
            "MAUI_CANDIDATE_ARTIFACT_CONTRACT_DRIFT")
    require(read_archive(root, artifact) == rebuilt, "MAUI_CANDIDATE_REPLAY_MISMATCH")
    require(package_catalog.reconstruct_package(binding, root) == candidate,
            "MAUI_CANDIDATE_PACKAGE_DRIFT")
    # Unchanged members remain byte-for-byte equal in the two archives.
    with zipfile.ZipFile(io.BytesIO(read_archive(root, BASE_ARTIFACT))) as old_zip, \
         zipfile.ZipFile(io.BytesIO(rebuilt)) as new_zip:
        old = {Path(n).name: old_zip.read(n) for n in old_zip.namelist()}
        new = {Path(n).name: new_zip.read(n) for n in new_zip.namelist()}
    changed = sorted(k for k in old if old[k] != new[k])
    require(set(old) == set(new) and changed == ["SHA256SUMS.txt", "jurisdiction.json", "manifest.json", "role_terms.csv"],
            "MAUI_CANDIDATE_MEMBER_SCOPE_DRIFT")
    return candidate, {"gate": GATE, "status": "PASS", "mode": "HELD_PREVIEW_ONLY",
        "source_archive_sha256": BASE_ARTIFACT["archive_sha256"],
        "candidate_archive_sha256": sha(rebuilt), "source_correction_sha256": correction_sha,
        "raw_observations": 3, "new_source_evidence": 3, "new_normalized_assertions": 3,
        "corrected_role_terms": 1, "csv_tables_checked": 7, "parity_ok": True,
        "changed_archive_members": changed, "exact_intervals_added": 0,
        "canonical_writes": 0, "publication_eligible": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    binding = json.loads((root / CONFIG).read_text())
    _, report = verify_candidate(root, binding)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
