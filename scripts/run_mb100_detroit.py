from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import yaml

HARNESS_ROOT = Path.cwd().resolve()
sys.path.insert(0, str(HARNESS_ROOT))

from src.init_migration.generate_pipeline import GeneratePipeline  # noqa: E402
from src.init_migration.pipeline_models import GeneratorReq, OCDidIngestResp, Status  # noqa: E402
from src.models.ocdid import OCDIdParsed  # noqa: E402
import src.init_migration.generate_division as division_module  # noqa: E402
import src.init_migration.generate_jurisdiction as jurisdiction_module  # noqa: E402
import src.init_migration.generate_recursive as recursive_module  # noqa: E402

TARGET_ID = "MB100-014"
TARGET_NAME = "Detroit"
TARGET_OCDID = "ocd-division/country:us/state:mi/place:detroit"
EXPECTED_JURISDICTION_OCDID = "ocd-jurisdiction/country:us/state:mi/place:detroit/government"
EXPECTED_CLASSIFICATION = "government"
GENERATOR_COMMIT = "6fbe7d6aed32c3b781490c8e4c5a737bdd6e4705"
FIXED_ASOF = datetime(2026, 8, 6, 14, 27, 0, tzinfo=UTC)
EVIDENCE_ROOT = Path("mb100_evidence")
VALIDATION_PATH = EVIDENCE_ROOT / "detroit_frozen_validation.csv"


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return FIXED_ASOF.replace(tzinfo=None)
        return FIXED_ASOF.astimezone(tz)


def freeze_generator_clock() -> None:
    division_module.datetime = FrozenDateTime
    jurisdiction_module.datetime = FrozenDateTime
    recursive_module.datetime = FrozenDateTime


def write_frozen_validation() -> str:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "GEOID_Census", "GEOIDFQ", "STATEFP", "NAMELSAD", "LSAD",
        "SLDUST_list", "SLDLST_list", "COUNTYFP_list", "COUNTY_NAMES",
        "COUSUBFP", "PLACEFP", "PLACENS",
    ]
    row = {
        "GEOID_Census": "2622000",
        "GEOIDFQ": "1600000US2622000",
        "STATEFP": "26",
        "NAMELSAD": "Detroit city",
        "LSAD": "25",
        "SLDUST_list": "",
        "SLDLST_list": "",
        "COUNTYFP_list": "163",
        "COUNTY_NAMES": "Wayne",
        "COUSUBFP": "",
        "PLACEFP": "22000",
        "PLACENS": "",
    }
    with VALIDATION_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)
    return hashlib.sha256(VALIDATION_PATH.read_bytes()).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"Expected mapping in {path}")
    return data


def tree_evidence(root: Path) -> dict[str, Any]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise AssertionError(f"No generated files under {root}")
    tree_hasher = hashlib.sha256()
    manifest: list[dict[str, Any]] = []
    seen_ocdids: set[str] = set()
    division_count = 0
    jurisdiction_count = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        file_sha = hashlib.sha256(payload).hexdigest()
        tree_hasher.update(relative.encode("utf-8"))
        tree_hasher.update(b"\0")
        tree_hasher.update(payload)
        tree_hasher.update(b"\0")
        entry: dict[str, Any] = {"path": relative, "bytes": len(payload), "sha256": file_sha}
        if path.suffix.lower() in {".yaml", ".yml"}:
            record = load_yaml(path)
            ocdid = record.get("ocdid")
            if not isinstance(ocdid, str) or not ocdid:
                raise AssertionError(f"Generated YAML lacks ocdid: {path}")
            if ocdid in seen_ocdids:
                raise AssertionError(f"Duplicate generated ocdid: {ocdid}")
            seen_ocdids.add(ocdid)
            entry["ocdid"] = ocdid
            if relative.startswith("divisions/"):
                division_count += 1
            elif relative.startswith("jurisdictions/"):
                jurisdiction_count += 1
        manifest.append(entry)
    return {
        "tree_sha256": tree_hasher.hexdigest(),
        "file_count": len(files),
        "division_count": division_count,
        "jurisdiction_count": jurisdiction_count,
        "files": manifest,
    }


async def run_once(run_name: str) -> dict[str, Any]:
    run_root = EVIDENCE_ROOT / run_name
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)
    ingest = OCDidIngestResp(
        uuid=uuid5(NAMESPACE_URL, TARGET_OCDID),
        ocdid=OCDIdParsed.parse_ocdid(TARGET_OCDID),
        raw_record={"id": TARGET_OCDID, "name": TARGET_NAME},
    )
    request = GeneratorReq(
        data=ingest,
        validation_data_filepath=str(VALIDATION_PATH.resolve()),
        asof_datetime=FIXED_ASOF,
    )
    response = await GeneratePipeline(
        request,
        division_output_dir=run_root,
        jurisdiction_output_dir=run_root,
    ).run()
    if response.status.status != Status.SUCCESS:
        raise AssertionError(
            f"{run_name} failed: {response.status.status.value}: {response.status.error or ''}"
        )
    if not response.division_path or not response.jurisdiction_path:
        raise AssertionError(f"{run_name} did not produce both target artifacts")
    division = load_yaml(Path(response.division_path))
    jurisdiction = load_yaml(Path(response.jurisdiction_path))
    assert division["ocdid"] == TARGET_OCDID
    assert division["government_identifiers"]["geoid"] == "2622000"
    assert division["government_identifiers"]["statefp"] == "26"
    assert division["government_identifiers"]["countyfp"] == ["163"]
    assert jurisdiction["ocdid"] == EXPECTED_JURISDICTION_OCDID
    assert jurisdiction["classification"] == EXPECTED_CLASSIFICATION
    assert division["jurisdiction_id"] == jurisdiction["ocdid"]
    evidence = tree_evidence(run_root)
    evidence.update({
        "run_name": run_name,
        "selection_status": "MATCHED",
        "generation_status": "SUCCESS",
        "parity_ok": True,
        "target_division_path": str(Path(response.division_path).relative_to(run_root)),
        "target_jurisdiction_path": str(Path(response.jurisdiction_path).relative_to(run_root)),
    })
    return evidence


async def main() -> None:
    if EVIDENCE_ROOT.exists():
        shutil.rmtree(EVIDENCE_ROOT)
    freeze_generator_clock()
    validation_sha = write_frozen_validation()
    run_1 = await run_once("run_1")
    run_2 = await run_once("run_2")
    checksum_parity = run_1["tree_sha256"] == run_2["tree_sha256"]
    if not checksum_parity:
        raise AssertionError(
            f"Deterministic tree mismatch: {run_1['tree_sha256']} != {run_2['tree_sha256']}"
        )
    summary = {
        "target_id": TARGET_ID,
        "jurisdiction_name": TARGET_NAME,
        "target_key": TARGET_OCDID,
        "expected_classification": EXPECTED_CLASSIFICATION,
        "generator_repository": "openstates/jurisdictions",
        "generator_commit": GENERATOR_COMMIT,
        "fixed_asof_utc": FIXED_ASOF.isoformat().replace("+00:00", "Z"),
        "validation_input_sha256": validation_sha,
        "selection_status": "MATCHED",
        "generation_status": "SUCCESS",
        "parity_ok": True,
        "checksum_run_1": run_1["tree_sha256"],
        "checksum_run_2": run_2["tree_sha256"],
        "checksum_parity_ok": checksum_parity,
        "run_1": run_1,
        "run_2": run_2,
    }
    (EVIDENCE_ROOT / "evidence_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "target_id": TARGET_ID,
        "selection_status": summary["selection_status"],
        "generation_status": summary["generation_status"],
        "parity_ok": summary["parity_ok"],
        "checksum_run_1": summary["checksum_run_1"],
        "checksum_run_2": summary["checksum_run_2"],
        "checksum_parity_ok": summary["checksum_parity_ok"],
        "file_count_per_run": run_1["file_count"],
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
