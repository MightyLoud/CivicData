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

Each district family currently maps **one resolved district key to one district-specific office**. That assumption is part of v0.1 and must be checked during discovery before packaging.

## Proven counties

- **Collin County** — 4 Commissioner + 4 JP + 4 Constable precincts; first production archetype release.
- **Travis County** — 4 Commissioner + 5 JP + 5 Constable precincts; second production archetype release and clean speed benchmark. Five interiors cover every Commissioner key and every shared JP/Constable key without engine or consumer-schema changes.

## Known unsupported pattern: Hays County

Hays County exposed the first deliberate archetype stop condition. Its JP structure includes multiple JP places sharing a single precinct key. Civic GPS v0.1 currently produces one district assignment and one district-specific office per adapter/district key, so flattening Hays into the existing contract would silently omit representation.

Do **not** work around this by choosing one JP place, duplicating fake geography, or treating place number as if it were a geographic precinct. Supporting Hays requires a future generalized contract that can map one resolved geographic district to multiple applicable offices while preserving deterministic joins and boundary behavior.

## Onboarding gate

Before a new county can be packaged:

1. Confirm official current geography endpoints and stable district fields.
2. Confirm the office structure fits the v0.1 one-office-per-district-family contract.
3. Establish canonical officeholder sources independently from GIS display labels.
4. Prove multiple interior addresses, an outside-county negative, and exact-boundary fail-closed behavior.
5. Keep unmodeled countywide offices and civic-action routing explicit as gaps rather than implying completeness.
6. Package through the normal Civic GPS PR release gate and require a post-merge `main` pass.
