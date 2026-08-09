# Civic GPS County Onboarding Pipeline v0.1

## Purpose

`tools/civic_gps_county_onboarding.py` converts a **frozen county onboarding spec** into a deterministic GO/STOP decision and the existing Civic GPS build/proof plan.

It is deliberately **not** a source scraper, live GIS crawler, or parallel resolver. Research and source reconciliation happen before the spec is frozen. The automation then answers a narrower question: can this evidence be represented safely by `TX_COUNTY_COMMISSIONER_JP_CONSTABLE_V0.1` without custom resolver logic or silent data loss?

## One-command intake

```bash
python tools/civic_gps_county_onboarding.py \
  tests/fixtures/civic_gps_county_onboarding/williamson_supported_v0.1.json \
  --output-dir artifacts/civic-gps-county-onboarding/williamson \
  --expect SUPPORTED_V0_1
```

A named STOP is also a successful deterministic classification:

```bash
python tools/civic_gps_county_onboarding.py \
  tests/fixtures/civic_gps_county_onboarding/hays_multi_office_stop_v0.1.json \
  --output-dir artifacts/civic-gps-county-onboarding/hays \
  --expect MULTI_OFFICE_PER_DISTRICT
```

## Frozen input contract

Schema: `schemas/civic_gps_county_onboarding_v0.1.schema.json`

A frozen spec carries:

- county name, Texas GEOID, stable Civic GPS IDs, and observation date;
- an explicit bounded countywide office scope;
- official identity and GIS source references;
- any source-precedence conflicts and whether they are resolved;
- district families, deterministic keys, office↔district cardinality, canonical holders, and GIS fields;
- candidate interior addresses, an outside-county negative, and the exact-boundary policy;
- explicit architecture flags and known gaps.

The tool does not infer missing evidence from GIS labels. Current officeholder identity remains `CANONICAL_RELEASE_ONLY`.

## Outputs

Every valid spec emits:

- `fit-report.json` — GO/STOP decision, named STOP class, reasons, and frozen-spec SHA-256;
- `source-precedence.json` — resolved/unresolved identity-conflict record;
- `proof-plan.json` — CG-01→CG-10 gate state, interior/negative/boundary matrix, package plan, and protected-promotion plan;
- `manifest.json` — deterministic SHA-256 hashes for all emitted JSON files.

A `SUPPORTED_V0_1` spec also emits:

- `builder-spec.json` — input for the existing `civic_gps_tx_county_archetype` helper;
- `canonical-release-preview.json` — deterministic canonical release preview;
- `base-bundle-plan.json` — deterministic BASE registry-bundle preview.

The tool refuses to emit those build previews after a STOP decision.

## Named STOP classes

Primary STOP priority follows the operational registry:

1. `MULTI_OFFICE_PER_DISTRICT`
2. `MISSING_OFFICIAL_GIS`
3. `NON_NUMERIC_DISTRICT_KEY`
4. `SOURCE_IDENTITY_CONFLICT`
5. `COUNTYWIDE_SCOPE_UNBOUNDED`
6. `TRANSIENT_UPSTREAM_FAILURE`
7. `ARCHITECTURE_CHANGE_REQUIRED`

The fit report retains all detected STOP classes and reasons while exposing one deterministic primary class.

## Non-negotiable invariants

A supported county must preserve:

- no county-specific resolver logic;
- no consumer-schema change;
- one applicable district-specific office per resolved key/family under v0.1;
- numeric district keys;
- official GIS geometry;
- `failure_scope = ADAPTER` for district adapters;
- `officeholder_identity_source = CANONICAL_RELEASE_ONLY`;
- `MULTIPLE_INTERSECTIONS => CONFLICT; NEVER TIE_BREAK`;
- a bounded one-meter topology probe on generated district adapters so source services that report a single owner at an exact shared edge still fail closed;
- explicit `BOUNDED_V0_1_SCOPE` rather than implied completeness;
- explicit `NOT_YET_RELEASED` for civic-action routing when actions have not been built.

## Acceptance fixtures

### Williamson County — supported

The Williamson fixture reproduces the first full County Onboarding Pipeline release:

- 18 modeled offices / 18 current holders;
- 4 Commissioner + 4 JP + 4 Constable district offices;
- four P1–P4 interior controls;
- Austin cross-county negative;
- shared P1/P4 exact-boundary fail-closed behavior;
- resolved Tax Assessor-Collector source precedence;
- no engine or consumer-schema change.

Expected classification: `SUPPORTED_V0_1 / NONE`.

### Hays County — stop

Hays is the negative fixture because JP precincts 1 and 2 each have multiple JP places sharing one geographic precinct key. The current v0.1 builder maps one resolved key to one district-specific office, so flattening Hays would silently omit representation.

Expected classification: `MULTI_OFFICE_PER_DISTRICT`.

No builder spec, release preview, or bundle preview may be emitted for this fixture.

## Release integration

The required `Civic GPS release gate` runs the deterministic Williamson/Hays fixtures and `tests/civic_gps_county_onboarding_test.py` before the existing networked release matrix.

Changing the onboarding tool, schema, fixtures, tests, or this documentation therefore triggers the same protected gate used for Civic GPS runtime promotion. A green onboarding test cannot hide a Denton, Collin, Travis, Williamson, or baseline regression.

## Human-minute metrics

This repo tool does not invent or backfill human time. Manual minutes remain recorded in the Program Command Center. The automation only produces machine evidence and deterministic plans.
