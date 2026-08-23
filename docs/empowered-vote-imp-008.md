# EV-IMP-008 — Catalog-Wide Jurisdiction Onboarding Gate

## Decision

Promote the EV-IMP-006 single-jurisdiction onboarding contract into a catalog-wide production gate. Every production spec under `onboarding/ev/*.v0.1.json` (excluding the template) is discovered automatically and must pass the same deterministic and live controls.

## Why

Akron and Fircrest proved two real onboarding patterns:

- `CENSUS_GEOID` for a municipality directly returned by the Civic GPS geography stack.
- `MUNICIPAL_BOUNDARY_OVERLAY` when the core Census address response omits a municipality and an authoritative polygon service must confirm the city boundary.

The next jurisdiction should not require another hand-written CI workflow or another jurisdiction-specific consumer path.

## Deterministic batch gate

`tools/ev_onboarding_batch.py` discovers every production onboarding spec and fails closed on:

- duplicate catalog entry IDs;
- duplicate Civic GPS jurisdiction IDs;
- duplicate package jurisdiction IDs;
- duplicate governed GEOIDs;
- duplicate routing identities;
- duplicate package artifact routes;
- unsupported routing strategies;
- fewer than two live address controls;
- package/checksum/schema/GEOID drift;
- profile capability overclaim;
- mismatch against current governed catalog/routing metadata.

It replays each spec through `ev_jurisdiction_onboarding.py` and emits one deterministic `acceptance-matrix.json`.

## Live batch gate

`tools/ev_live_onboarding_batch.py` loads the exact Civic GPS runtime once, resolves every configured live address, selects the governed package through the catalog, chooses the consumer from the declarative profile, and verifies the configured acceptance counts.

The runner contains no Akron or Fircrest condition. Adding a future supported jurisdiction requires governed package data plus a production onboarding spec; the batch gate discovers it automatically.

## Current production matrix

- Akron, Colorado — `municipal_representation` — Package v0.1 — `CENSUS_GEOID` — 2 live controls.
- Fircrest, Washington — `municipal_essentials` — Package v0.2 — `MUNICIPAL_BOUNDARY_OVERLAY` — 2 live controls.

Both remain package-authoritative. Civic GPS contributes geography; canonical writes remain zero.

## CI

`.github/workflows/ev-onboarding-live-batch.yml` runs the deterministic matrix and all production live address controls in one generic gate. Existing jurisdiction-specific workflows are retained during this gate as regression controls; EV-IMP-008 does not remove them.

Publication, external distribution, and consumer writeback are not authorized by EV-IMP-008.
