# EV-IMP-009 — Governed Onboarding Proposal Generator

## Decision

Automate the mechanical parts of jurisdiction onboarding from a staged governed Jurisdiction Package while preserving a hard boundary around geography authority.

`tools/ev_onboarding_proposal.py` discovers a staged package by package jurisdiction ID, reconstructs and validates the exact archive, derives the consumer profile, package checksum and path, governed GEOID, acceptance counts, Full Essentials counts when supported, and at least two governed address controls.

## Authority boundary

The generator does **not** invent Civic GPS routing.

If a governed routing record already matches the package GEOID, the generator may reuse it and emit a `READY` production onboarding spec. Supported governed routing records are:

- `CENSUS_GEOID` registry bundles;
- `MUNICIPAL_BOUNDARY_OVERLAY` records.

If no governed routing record exists, the generator emits `REVIEW_REQUIRED` with a bounded routing research candidate. It suggests Census GEOID as the first probe and municipal-boundary overlay as the fallback, but does not create either authority record.

## Derived fields

The following fields are package-derived rather than hand-authored:

- package schema version;
- package artifact path and SHA-256;
- package subdirectory;
- governed GEOID;
- `municipal_representation` vs `municipal_essentials` profile;
- office count;
- current-holder count;
- QA fail count;
- blocking-gap count;
- parity status;
- address-control count and live addresses;
- election, contest, candidacy, named-person, and write-in counts for Full Essentials packages.

Routing-specific authority, parent jurisdiction, service URL, identity field, and polygon query remain governed routing metadata rather than package inference.

## Round-trip gate

`--verify-production` regenerates every current production onboarding spec from its governed package plus already-governed routing metadata. Akron and Fircrest must reproduce their current specs modulo the explicit/default `CENSUS_GEOID` strategy marker.

Any package checksum drift, schema drift, address-control loss, profile change, expected-count change, routing ambiguity, or spec drift fails closed.

## Current proof

- Akron, Colorado regenerates as Package v0.1 `municipal_representation` using the governed `CENSUS_GEOID` route.
- Fircrest, Washington regenerates as Package v0.2 `municipal_essentials` using the governed `MUNICIPAL_BOUNDARY_OVERLAY` route.
- routing authority inferred by the generator: **false**;
- canonical writes: **0**.

EV-IMP-009 does not publish packages, modify canonical civic data, or authorize external distribution or consumer writeback.
