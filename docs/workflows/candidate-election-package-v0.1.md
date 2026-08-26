# Candidate-Election Package v0.1

`TX-PUB-CONTRACT-001` defines a separate, fail-closed package contract for
municipal candidate-election data. It reuses CivicData stable jurisdiction,
division, office, and person identifiers without forcing candidate facts into
the current-official/role-term model.

This implementation is staged under `TX-PUB-IMPLEMENT-001`. It does not
authorize merge, release, API deployment, public distribution, source-document
redistribution, outreach, or canonical civic-fact changes.

## Repository layout

Contract tooling:

- `schemas/candidate_election_package_v0.1.schema.json`
- `tools/candidate_election_package.py`
- `tests/test_candidate_election_package.py`
- `examples/candidate_election_package_consumer.py`

Jurisdiction packages:

```text
data/normalized/tx/<place_fp>-<slug>/candidate-election/2026/
├── canonical.json
├── candidates.csv
├── contests.csv
├── sources.csv
├── manifest.json
├── qa_report.json
├── SHA256SUMS.txt
└── README.md
```

Aggregate index:

```text
data/normalized/tx/tx-candidate-election-2026-001.manifest.json
```

The JSON file is authoritative. CSV files are deterministic, non-authoritative
review mirrors.

## Canonical boundaries

The package contains:

- Jurisdiction
- Division and JurisdictionDivision
- Election
- Office and OfficeDivision
- Contest
- Person
- Candidacy
- publication-eligible ContactPoint
- ExternalIdentifier
- safe SourceRecordRef
- SourceEvidence and context evidence
- EvidenceLink
- reconciliation, QA, warnings, and release state

Candidate identity is represented by `Person` plus `Candidacy`. A Candidacy
must resolve to one Person, one Contest, and one safe primary SourceRecordRef.
Each Contest must resolve to one Election and one Office.

`EvidenceLink.asserted_value_hash` is required for `FIELD` assertions. WB-020
leaves it blank for `IDENTITY` and `RELATIONSHIP` links because those links bind
the evidence directly to a stable target entity rather than duplicating a field
value. The package preserves that governed distinction and does not synthesize
missing assertion hashes.

## Public-field policy

Publish only normalized, source-supported facts. A ContactPoint is allowed only
when all of the following are true:

- `sensitivity = PUBLIC`
- `publication_ok = TRUE`
- `contact_status = ACTIVE`
- `source_evidence_id` resolves inside the package

The package excludes:

- Candidate_RAW and complete normalized workbook rows
- `raw_payload_json`
- raw notes and source notes
- outreach, recipient, response, and workflow metadata
- operator and migration fields
- unsupported inferred facts
- source-document bytes
- Gap and Retired audit rows

Gap and Retired rows remain count-accounted in
`reconciliation.excluded_source_records`; they are not candidate records and
are not copied into the public provenance payload.

## Texas release reconciliation

The staged release contains exactly ten municipal packages:

| Place FP | Jurisdiction | Governed rows | Candidacies |
|---|---|---:|---:|
| 07552 | Benbrook | 3 | 3 |
| 08128 | Bevil Oaks | 6 | 6 |
| 17917 | Cross Timber | 1 | 1 |
| 26808 | Fort Stockton | 3 | 3 |
| 33794 | Highland Haven | 3 | 3 |
| 35228 | Hudson | 5 | 5 |
| 38548 | Keene | 8 | 8 |
| 39952 | Kyle | 16 | 8 |
| 46824 | Mart | 9 | 9 |
| 47316 | Meadow | 4 | 4 |

Aggregate reconciliation:

- 58 RAW
- 58 normalized
- 58 QA-ready
- 50 Candidate records
- 3 Structure records
- 1 Gap record
- 4 Retired records
- 50 Person records
- 50 Candidacy records
- 25 Contest records
- 10 Election records
- 25 Office records
- 53 scoped safe SourceRecordRef rows
- 55 scoped ACTIVE / OFFICIAL_PRIMARY SourceEvidence rows
- 0 ContactPoint records

Context source/evidence rows provide the closed provenance needed by division
and office-division relationships. They are counted separately from the 53/55
candidate-election source scope.

## Validation

Validate one canonical package:

```bash
python tools/candidate_election_package.py validate \
  data/normalized/tx/07552-benbrook/candidate-election/2026/canonical.json
```

Verify one built directory:

```bash
python tools/candidate_election_package.py verify \
  data/normalized/tx/07552-benbrook/candidate-election/2026
```

Verify the complete staged release:

```bash
python tools/candidate_election_package.py verify-release .
python tests/test_candidate_election_package.py
```

The validator fails closed on schema/version drift, duplicate IDs, unresolved
foreign keys, missing provenance, count mismatches, QA/parity/tracker failures,
restricted-field leakage, non-public contact data, altered publication state,
checksum errors, and non-deterministic output. Evidence assertion kinds are
limited to `FIELD`, `IDENTITY`, and `RELATIONSHIP`, and each target ID must match
the declared target-entity type. `ExternalIdentifier` is reserved in v0.1, so
its record collection must remain empty. Dates and timestamps use canonical
`YYYY-MM-DD` and RFC 3339 forms rather than permissive ISO 8601 alternatives.

Schema validation applies every JSON Schema keyword used by the v0.1 Draft
2020-12 contract. Package verification requires the exact flat output set,
rejects symlinks and unexpected nested entries, and treats duplicate or unsafe
checksum paths as errors. Release validation recursively inventories the staged
tree, rebuilds the complete output in a temporary directory, and requires exact
byte equality, so omissions, additions, aggregate-count drift, false QA state,
and a package set other than the fixed ten-place release fail closed.

Pull requests that touch this contract run
`.github/workflows/candidate-election-package.yml`, which compiles the builder,
tests, and consumer example; executes positive and negative contract controls;
and verifies the complete staged release.

## Publication boundary

Every package and the aggregate manifest must remain
`STAGED_NOT_PUBLISHED`. A merge, release, API deployment, or public
distribution requires a separate exact authorization gate.
