#!/usr/bin/env python3
"""Read a staged candidate-election package without mutating it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_candidates(package_dir: Path) -> list[dict[str, str]]:
    package = json.loads(
        (package_dir / "canonical.json").read_text(encoding="utf-8")
    )
    if package.get("publication_status") != "STAGED_NOT_PUBLISHED":
        raise ValueError("unexpected publication status")

    people = {
        row["person_id"]: row for row in package["records"]["people"]
    }
    contests = {
        row["contest_id"]: row for row in package["records"]["contests"]
    }
    offices = {
        row["office_id"]: row for row in package["records"]["offices"]
    }
    elections = {
        row["election_id"]: row for row in package["records"]["elections"]
    }

    rows = []
    for candidacy in package["records"]["candidacies"]:
        person = people[candidacy["person_id"]]
        contest = contests[candidacy["contest_id"]]
        office = offices[contest["office_id"]]
        election = elections[contest["election_id"]]
        rows.append(
            {
                "candidate": person["person_full_name"],
                "office": office["office_name"],
                "contest": contest["contest_label"],
                "election_date": election["election_date"],
                "status": candidacy["candidacy_status"],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["election_date"],
            row["office"],
            row["candidate"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(load_candidates(args.package_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
