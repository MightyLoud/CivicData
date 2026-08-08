# Civic GPS Texas county precinct archetype

## Purpose

`TX_COUNTY_COMMISSIONER_JP_CONSTABLE_V0.1` is a build-time archetype that emits the existing Civic GPS BASE registry and canonical-release contract. It is not a parallel resolver and does not change the consumer response schema.

## Supported v0.1 contract

A county may use this archetype when its address-specific representation can be expressed as:

- any explicitly bounded set of jurisdiction-wide county offices;
- one Commissioner office for each Commissioner district key;
- one Justice of the Peace office for each JP district key;
- one Constable office for each Constable district key;
- official point-intersection geography with deterministic district keys;
- canonical officeholder identity sourced independently from GIS display labels.

Each district family currently maps **one resolved district key to one district-specific office**. That assumption is part of v0.1 and must be checked before roster/GIS implementation proceeds.

## County Onboarding Pipeline v0.1

A supported county moves through the same gates:

1. `CG-01` scope/intake.
2. `CG-02` authoritative identity/geography source separation.
3. `CG-03` archetype-fit / named STOP classification.
4. `CG-04` deterministic canonical roster and stable office IDs.
5. `CG-05` official GIS + adapter contract proof.
6. `CG-06` multiple real interior address controls.
7. `CG-07` outside-county leakage negative.
8. `CG-08` exact-boundary fail-closed control.
9. `CG-09` deterministic package + full regression.
10. `CG-10` clean protected PR promotion + post-merge `main` proof.

A county is considered a successful pipeline outcome either when it reaches release without new architecture, or when it stops early with a named unsupported pattern before custom engineering begins.

## Automated frozen-spec intake

New counties should begin with `tools/civic_gps_county_onboarding.py` and a frozen `civic-gps-county-onboarding/0.1.0` JSON spec. The tool runs CG-01→CG-03 deterministically before custom engineering, records source-precedence decisions, and emits the existing archetype builder input plus release/bundle previews only for supported counties.

The tool does **not** scrape sources, infer officeholder identity from GIS, or mutate production. Live source discovery and reconciliation must be frozen into the input spec first. See `docs/workflows/civic-gps-county-onboarding.md`.

Acceptance fixtures are permanent:

- Williamson County → `SUPPORTED_V0_1 / NONE` and deterministic release/bundle previews.
- Hays County → `MULTI_OFFICE_PER_DISTRICT` and no build previews.

## Proven counties

- **Collin County** — 4 Commissioner + 4 JP + 4 Constable precincts; first production archetype release.
- **Travis County** — 4 Commissioner + 5 JP + 5 Constable precincts; second production archetype release and first clean speed benchmark.
- **Williamson County** — 4 Commissioner + 4 JP + 4 Constable precincts; third production archetype output and first county completed through CG-01→CG-10. Williamson uses one official shared precinct layer (`PCT_NUMBER` 1–4) for all three district families and was released with no engine or consumer-schema change.
- **Tarrant County** — 4 Commissioner + 8 JP + 8 Constable precincts; fourth production archetype output and second county completed through the automated County Onboarding Pipeline. Tarrant uses separate official Commissioner geometry and shared JP/Constable geometry, preserving independent fail-closed behavior without an engine or consumer-schema change.

Normal interiors in these archetype counties return the explicitly bounded jurisdiction-wide office set plus exactly one office from each resolved district family. Boundary conflicts never tie-break.

## Known unsupported pattern: Hays County

Hays County exposed the first deliberate archetype stop condition. Its JP structure includes multiple JP places sharing a single precinct key. Civic GPS v0.1 currently produces one district assignment and one district-specific office per adapter/district key, so flattening Hays into the existing contract would silently omit representation.

Do **not** work around this by choosing one JP place, duplicating fake geography, or treating place number as if it were a geographic precinct. Supporting Hays requires a future generalized contract that can map one resolved geographic district to multiple applicable offices while preserving deterministic joins and boundary behavior.

Stop class: `MULTI_OFFICE_PER_DISTRICT`.

## Source precedence

GIS is authoritative for geometry only. Officeholder identity must come from current canonical official evidence. If a general directory or GIS display label conflicts with a newer office-specific page or appointment record, preserve the conflict and apply explicit source precedence rather than silently accepting the stale label.

Williamson provides a positive fixture: its general elected-officials directory lagged the July 2026 Tax Assessor-Collector appointment, so the newer official office/appointment evidence controls canonical identity.

## Packaging and promotion

Before promotion:

- prove multiple interiors, an outside negative, and exact-boundary fail-closed behavior;
- keep unmodeled countywide offices and civic-action routing explicit as gaps rather than implying completeness;
- reconstruct and verify the exact packaged runtime SHA;
- pass the full baseline + all previously released county regressions against the candidate package;
- cut a clean production branch from current `main`, excluding discovery/onboarding/packager machinery;
- require a pull request and the `Civic GPS release gate` status;
- require a post-merge `main` pass before calling the county released.

Williamson's v0.1 geography/office package keeps action routing `NOT_YET_RELEASED` and additional countywide offices `BOUNDED_V0_1_SCOPE`.

Tarrant's v0.1 geography/office package contains 26 canonical offices / 26 holders = 6 deliberately bounded countywide + 4 Commissioner + 8 JP + 8 Constable. Action routing remains `NOT_YET_RELEASED`; additional countywide offices remain `BOUNDED_V0_1_SCOPE`.
