# EV-IMP-004 — Governed Package Catalog

## Decision

Remove Tacoma from the package-selection decision path without weakening the authority split established by EV-IMP-003.

The runtime becomes:

`address → Civic GPS jurisdiction/district resolution → governed package catalog → exactly one Jurisdiction Package → Empowered.Vote Essentials`

## Authority boundaries

Civic GPS remains authoritative only for resolved jurisdiction and district geography. The selected Jurisdiction Package remains authoritative for bodies, offices, people, officeholders, terms/currentness, elections, contests, candidacies, provenance, warnings, and rendered civic facts.

The catalog is routing metadata. It does not create civic facts.

## Catalog v0.1

`consumers/empowered_vote/package_catalog.v0.1.json` declares governed package routes. Each entry binds:

- one Civic GPS jurisdiction ID;
- one canonical package jurisdiction ID;
- one package schema version;
- one deterministic package artifact and SHA-256;
- an optional district adapter and division template;
- one consumer profile.

The first real catalog entry is Tacoma because Tacoma is currently the only governed v0.2 package checked into `data/packages/`.

## Fail-closed selection

The selector fails closed when:

- no governed package matches the resolved jurisdiction set;
- multiple entries match the requested profile;
- catalog identity or schema metadata drifts from the reconstructed package;
- artifact parts are missing, invalid base64, corrupt ZIP, or fail SHA-256;
- a required district assignment is missing;
- a resolved district is absent from the selected package.

No nearest-package, same-state, name-based, or geography inference fallback is allowed.

## Acceptance

- IMP4-01 package selection is catalog-driven, not Tacoma-coded;
- IMP4-02 the real Tacoma package reconstructs and passes through the catalog;
- IMP4-03 Market Street remains 6 offices / 5 contests / 15 candidate rows;
- IMP4-04 unsupported resolved jurisdictions fail closed;
- IMP4-05 ambiguous catalog routes fail closed;
- IMP4-06 a synthetic second jurisdiction proves the selector/binding path is generic without asserting a second real governed package exists;
- IMP4-07 Civic GPS `applicable_offices` and `action_links` remain non-authoritative and ignored;
- IMP4-08 canonical writes remain zero;
- IMP4-09 EV-IMP-003 live geography behavior remains backward compatible.

## Current coverage boundary

Generalized selection does **not** mean national package coverage. At this gate, Tacoma remains the only real governed package in the catalog. New jurisdictions become supported only after a governed package is materialized, validated, checked in, and added to the catalog.

## Explicit exclusions

No publication authorization, no CivicData writeback, no inferred package fallback, no second civic backend, and no claim of jurisdiction coverage beyond catalog entries.
