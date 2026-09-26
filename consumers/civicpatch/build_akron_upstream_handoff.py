#!/usr/bin/env python3
"""Build the deterministic upstream CivicPatch Akron PR handoff package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "acceptance" / "civicpatch" / "akron_upstream_base_69331c2.yml"
CANDIDATE = ROOT / "candidates" / "civicpatch" / "akron_v0.1" / "place_akron.yml"

UPSTREAM_REPOSITORY = "CivicPatch/open-data"
UPSTREAM_COMMIT = "69331c2b0d97e13695dab07ec1d6a969c99a3e4d"
UPSTREAM_BLOB_SHA = "3c335cac8e5d07fb18b67db70aa12c7dc1d7a7d7"
TARGET_PATH = "data/co/local/place_akron.yml"
JURISDICTION_OCDID = "ocd-jurisdiction/country:us/state:co/place:akron/government"
GENERATED_AT = "2026-09-26T15:35:00Z"

PATCH_NAME = "akron_civicpatch_upstream.patch"
PR_BODY_NAME = "UPSTREAM_PR_BODY.md"
CHECKLIST_NAME = "UPSTREAM_REVIEW_CHECKLIST.md"
METADATA_NAME = "handoff.json"


def full_replacement_patch(base: str, candidate: str) -> str:
    old = base.splitlines()
    new = candidate.splitlines()
    lines = [
        f"diff --git a/{TARGET_PATH} b/{TARGET_PATH}",
        f"--- a/{TARGET_PATH}",
        f"+++ b/{TARGET_PATH}",
        f"@@ -1,{len(old)} +1,{len(new)} @@",
    ]
    lines.extend("-" + line for line in old)
    lines.extend("+" + line for line in new)
    return "\n".join(lines) + "\n"


def pr_body() -> str:
    return """## Summary

Refresh the Akron, Colorado elected-official roster from the current official Town sources.

### Current roster represented by this change

- Annette Bowin — Mayor
- Braden Brent — Trustee
- Crystann Benson — Trustee
- Jared Jefferson — Trustee
- Joe Tarnow — Trustee
- Ron Kraich — Trustee
- Terry Alexander — Trustee

### Identity handling

Existing CivicPatch person IDs are retained for:

- Braden Brent — `d31247df-3332-490e-b45d-fa8e7bb55e0b`
- Crystann Benson — `623089fb-bd23-4615-a440-1a61da966c15`
- Jared Jefferson — `dd07c3f5-1432-4c30-9bc9-9f73bb3385c2`

The four newly represented current officials use proposed UUIDs in this PR. Maintainers may remint those IDs if CivicPatch has a preferred identity-creation workflow.

### Jared Jefferson role correction

The current Town roster identifies Jared Jefferson as Trustee / Mayor Pro Tem. Akron Code §1-5-3 provides that the Board selects Mayor Pro Tem from among the trustees, so this file publishes his formal role as `trustee` rather than `mayor-pro-tempore`.

### Tenure handling

The Town publishes term-expiration years, but the source material used here does not establish exact service start/end dates. This change therefore leaves `start_date` and `end_date` null instead of converting an expiration year into an inferred term boundary.

### Rows no longer in the current roster

The replacement file no longer lists:

- Brandon Hill
- Ariella Gonzales-Vondy
- David Kembel
- Jennifer Hansen

This is a current-roster update only; it should not be interpreted as deleting historical Person identities elsewhere in CivicPatch.

## Sources

- Current Town Board roster: https://www.townofakron.com/172/Board-of-Trustees
- Akron Code §1-5-1, Board composition: https://codelibrary.amlegal.com/codes/akron_co/latest/akron_co/0-0-0-127
- Akron Code §1-5-3, Mayor Pro Tem: https://codelibrary.amlegal.com/codes/akron_co/latest/akron_co/0-0-0-134

## Validation

The candidate was generated from a certified CivicData Jurisdiction Factory package and validated against the CivicPatch `shared.schemas.OpenStatesPersonRecord` publish shape pinned to:

- `CivicPatch/open-data@69331c2b0d97e13695dab07ec1d6a969c99a3e4d`
- `CivicPatch/civicpatch-tools@072a8baf648542f66557fb30547ee3ba3a11ba6c`

The handoff also verifies a lossless round trip for the canonical representation semantics retained by the CivicPatch candidate + sidecar receipt.
"""


def checklist() -> str:
    return """# Akron upstream review checklist

## Base

- [ ] Confirm `main` is still based on or compatible with `69331c2b0d97e13695dab07ec1d6a969c99a3e4d`.
- [ ] Confirm `data/co/local/place_akron.yml` still has blob SHA `3c335cac8e5d07fb18b67db70aa12c7dc1d7a7d7`, or rebase the candidate first.

## Data review

- [ ] Confirm the current official Town roster lists the seven proposed people.
- [ ] Retain the existing CivicPatch IDs for Braden Brent, Crystann Benson, and Jared Jefferson.
- [ ] Review or remint the four proposed IDs for Annette Bowin, Joe Tarnow, Ron Kraich, and Terry Alexander.
- [ ] Confirm Jared Jefferson is represented formally as Trustee; treat Mayor Pro Tem as internal leadership.
- [ ] Confirm no exact term dates should be inferred from published expiration years.
- [ ] Treat omitted old roster rows as historical/stale-roster removal from this current file, not Person-identity deletion.

## CivicPatch validation

Run from the CivicPatch/open-data checkout:

```bash
uv run python scripts/github_actions/validate_jurisdiction.py \
  "ocd-jurisdiction/country:us/state:co/place:akron/government"
```

- [ ] CivicPatch schema validation passes.
- [ ] Review the full YAML diff.
- [ ] Confirm no unrelated jurisdiction files changed.

## Provenance

- [ ] Board roster source reviewed.
- [ ] Board-composition code source reviewed.
- [ ] Mayor-Pro-Tem code source reviewed.

## Publication

- [ ] Maintainer approves proposed/new person IDs.
- [ ] Maintainer confirms replacement-file workflow is appropriate.
- [ ] Only then merge/publish upstream.
"""


def metadata() -> dict:
    return {
        "handoff_version": "0.1",
        "generated_at": GENERATED_AT,
        "upstream": {
            "repository": UPSTREAM_REPOSITORY,
            "branch": "main",
            "commit": UPSTREAM_COMMIT,
            "target_path": TARGET_PATH,
            "target_blob_sha": UPSTREAM_BLOB_SHA,
            "connected_account_push_permission": False,
        },
        "candidate": {
            "source_path": str(CANDIDATE.relative_to(ROOT)),
            "jurisdiction_ocdid": JURISDICTION_OCDID,
            "upstream_base_blob_sha": UPSTREAM_BLOB_SHA,
            "candidate_blob_sha": "ac9a96cdb8c7052cb6681844cbdafbacdca2ee27",
        },
        "submission": {
            "upstream_write_authorized": False,
            "requires_fork_or_maintainer_branch": True,
            "pr_not_submitted": True,
        },
        "artifacts": {
            "patch": PATCH_NAME,
            "pr_body": PR_BODY_NAME,
            "review_checklist": CHECKLIST_NAME,
        },
    }


def build_handoff(output_dir: Path) -> None:
    base = BASE.read_bytes()
    candidate = CANDIDATE.read_bytes()
    patch = full_replacement_patch(
        base.decode("utf-8"),
        candidate.decode("utf-8"),
    ).encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / PATCH_NAME).write_bytes(patch)
    (output_dir / PR_BODY_NAME).write_text(pr_body(), encoding="utf-8")
    (output_dir / CHECKLIST_NAME).write_text(checklist(), encoding="utf-8")
    (output_dir / METADATA_NAME).write_text(
        json.dumps(metadata(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "candidates" / "civicpatch" / "akron_v0.1" / "upstream_handoff",
    )
    args = parser.parse_args()
    build_handoff(args.output_dir)
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
