# CivicData

A civic-data production system for collecting, normalizing, validating, and publishing reliable information about elected officials, candidates, districts, and geographic relationships.

## Core objective

Build a nationwide dataset that can support questions such as:

- Who represents a given address?
- Which municipality, county, state-legislative districts, and congressional district contain a location?
- Who currently holds each federal, state, county, and municipal office?
- What source supports each published record?

## Definition of done

A record is complete only when:

1. Source data exists in `data/raw/`.
2. A normalized record exists in `data/normalized/`.
3. Required QA checks pass.
4. `Parity_OK` is `TRUE`.
5. Source, confidence, and review metadata are populated.
6. The project tracker reflects completion.

## Initial pipeline

```text
Source research
    ↓
Raw capture
    ↓
Normalization
    ↓
Validation and QA
    ↓
Parity checks
    ↓
Publishable output
```

## Planned repository structure

```text
CivicData/
├── data/
│   ├── raw/
│   ├── normalized/
│   └── reference/
├── docs/
│   ├── schemas/
│   └── workflows/
├── scripts/
│   ├── ingest/
│   ├── normalize/
│   └── qa/
├── tests/
└── README.md
```

## Initial development priorities

1. Define the canonical jurisdiction and office schemas.
2. Establish raw-to-normalized field mappings.
3. Create repeatable QA and parity checks.
4. Build one end-to-end pilot jurisdiction.
5. Convert the pilot into a reusable state-production workflow.

## Working principles

- Preserve raw source data.
- Separate facts from interpretations.
- Store provenance at the record level.
- Prefer repeatable batch workflows over manual edits.
- Never mark work complete before QA and parity validation.
- Improve the existing system before redesigning it.

## Status

Repository initialized. Schemas and the first pilot pipeline are the next build targets.
