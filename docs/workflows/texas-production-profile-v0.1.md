# Texas bounded legislative production profile v0.1

Status: `SUPPORTED_AND_ACTIVATED_BOUNDED`

This contract defines the production profile for the exact Texas House District 49 / Senate District 14 representation slice. The profile is now active in the Day 12 branch default package catalog. It does not make the source package a complete Texas package, enable Full Essentials, include elections, merge PR #48, or authorize release.

## Profile

Profile ID: `tx_legislative_two_office_v0.1`

Consumer route: `state_legislative_representation`

Supported scope is exactly:

- Texas House District 49;
- Texas Senate District 14;
- both bindings required atomically;
- representation only;
- omitted data means `NOT_INCLUDED_NOT_ABSENT`;
- `complete_jurisdiction=false`;
- elections unsupported;
- Full Essentials unsupported.

A successful bounded projection may report `publication_eligible=true` for the exact two-office view while the underlying source package remains `complete_jurisdiction=false`.

## Source-package contract remains strict

The ordinary Jurisdiction Package loader is unchanged. A partial package with nonzero blocking gaps or insufficient source address controls still fails the generic full-jurisdiction contract.

The bounded Texas profile uses its dedicated production loader. Source QA is preserved exactly; activation does not clear the five bounded limitations, fabricate source address tests, or rewrite the package.

## Activated catalog envelope

The default catalog now contains exactly one certified Texas entry:

`tx-legislative-two-office-v0.1-hosted-candidate`

Catalog-entry SHA-256:

`1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189`

It declares:

- `profile=state_legislative_representation`;
- `production_profile.profile_id=tx_legislative_two_office_v0.1`;
- exact acceptance-receipt path/hash;
- exactly two explicit bindings;
- House binding `tx-house` / `DIST-TX-HOUSE-H2316` / district 49;
- Senate binding `tx-senate` / `DIST-TX-SENATE-S2168` / district 14;
- explicit canonical district-to-Division maps.

## Identity and atomicity

Every Person must remain explicit `AUTHORITATIVE`. A provisional, missing, merged, blocked, or other non-authoritative identity state fails closed.

Both House and Senate bindings must resolve. A single-chamber result is never returned as a valid bounded representation result.

## Geometry governance

The activated default registry contains the exact `PRODUCTION_BOUNDED` group `GEO-TX-LEGISLATIVE-TWO-DISTRICTS`, bound to geometry policy `texas-legislative-geometry-governance/0.1`.

Legislative-group SHA-256:

`826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a`

Geometry marker drift remains fail-closed before legislative representation is emitted.

## Activation and boundaries

Repository activation moment:

`2d56d3ee1247be470c066df4b4321fd8e4679698`

Activation receipt SHA-256:

`8574a0987e1ebebe4ec3679e9ca936df9aae7453f8ded70642aca54ebf197166`

Current disposition:

`PRODUCTION_PROFILE = ACTIVE_BOUNDED`

`REPOSITORY_ACTIVATION = ACTIVATED_BOUNDED`

`MERGE = NOT_AUTHORIZED`

`RELEASE = NOT_AUTHORIZED`

`PUBLICATION_WORKFLOW = NOT_AUTHORIZED`

`CANONICAL_WRITES = 0`

## Verification

```sh
python tests/test_tx_production_profile.py
python tests/test_texas_activation_execution.py
python tests/test_texas_bounded_contract.py
python tests/test_public_identity_disposition.py
python tests/test_role_term_integration.py
```
