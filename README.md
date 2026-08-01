# CivicData

A versioned civic-data production system for collecting, normalizing, validating, publishing, and maintaining reliable information about governments, offices, officeholders, elections, identifiers, and geographic relationships.

## Current proof

Two municipal jurisdictions now pass the same release and consumer system:

| Jurisdiction | Modeled offices | Public-elected offices | Current RoleTerms | Consumer test |
|---|---:|---:|---:|---|
| Seattle, Washington | 18 | 18 | 18 | PASS |
| Tacoma, Washington | 16 | 15 | 16 | PASS |

Tacoma adds a Council–Manager government, an appointed City Manager, voter-elected Civil Service Board seats, and a judicial retirement → vacancy → appointment → successor-election transition without changing the package schema or release logic.

## Repository contract

```text
source assertions
    ↓
canonical entities and temporal relationships
    ↓
jurisdiction-neutral validation
    ↓
canonical JSON + CSV mirrors + manifest + QA
    ↓
independent consumer acceptance
```

A jurisdiction is not complete because rows were collected. It is complete when:

1. durable entities have stable canonical IDs;
2. every factual record has registered evidence;
3. unknowns, conflicts, and deferrals remain explicit;
4. relationship and temporal checks pass;
5. JSON and CSV outputs agree;
6. checksums match;
7. a consumer can use the release without opening the working spreadsheet.

## Repository layout

```text
.github/workflows/         Continuous validation
docs/contracts/            Field and publication contracts
docs/workflows/            Production and maintenance procedures
partner-acceptance/        Bounded external acceptance protocol
registry/                  Jurisdiction and release registry
releases/<place>/<version> Canonical JSON, manifest, QA, checksum
schema/                    Versioned package schema
scripts/                   Generic release and consumer validators
tests/                     Cross-jurisdiction regression tests
```

## Run validation

```bash
python scripts/validate_release.py releases/seattle/0.1/canonical.json
python scripts/validate_release.py releases/tacoma/0.1/canonical.json
python scripts/run_consumer_test.py releases/seattle/0.1/canonical.json
python scripts/run_consumer_test.py releases/tacoma/0.1/canonical.json
python -m unittest discover -s tests -v
```

## Rights and licensing

Record-level source attribution is part of every release. A package-level open license has **not yet been adopted**. See `docs/RIGHTS_AND_LICENSING.md`.
