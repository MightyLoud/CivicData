# Texas bounded legislative production profile v0.1

Status: `SUPPORTED_NOT_ACTIVATED`

This contract adds production-profile support for the already accepted bounded Texas legislative representation slice. It does **not** make the source package a complete Texas package, add a Texas entry to the production catalog, deploy a hosted service, merge the draft PR, or activate public routing.

## Profile

Profile ID: `tx_legislative_two_office_v0.1`

Consumer route: `state_legislative_representation`

Supported scope is exactly:

- Texas House District 49;
- Texas Senate District 14;
- both bindings required for a successful projection;
- representation only;
- omitted data means `NOT_INCLUDED_NOT_ABSENT`;
- elections and Full Essentials are not included.

A successful profile projection may report `publication_eligible=true` for this bounded view while it must continue to report `complete_jurisdiction=false`. It does not convert the underlying source package into a complete-jurisdiction package.

## Default package contract remains strict

The ordinary Jurisdiction Package production loader is unchanged. A package with `complete_jurisdiction=false`, nonzero blocking gaps, or insufficient source-package address controls is still rejected by the ordinary loader.

The bounded Texas profile uses a separate profile loader. That loader is available only when all profile controls below pass. Source QA is preserved exactly; the profile must not clear blockers, fabricate address controls, or rewrite the package merely to satisfy the generic full-jurisdiction gate.

## Required envelope

A catalog entry using this profile must declare:

- `profile=state_legislative_representation`;
- `production_profile.profile_id=tx_legislative_two_office_v0.1`;
- a repository-relative acceptance-receipt path and exact SHA-256;
- exactly two explicit district bindings;
- House binding `tx-house` using adapter `DIST-TX-HOUSE-H2316` and key `49`;
- Senate binding `tx-senate` using adapter `DIST-TX-SENATE-S2168` and key `14`;
- explicit district-to-canonical-division maps. Labels or templates do not mint IDs for this profile.

The hash-bound receipt must be a deterministic `texas-bounded-acceptance/0.1` receipt for the exact package bytes. Its declared office, Person, RoleTerm, binding, source-QA, identity-status, and package-hash scope must agree with the package and catalog entry.

The receipt's historical gate-disposition fields do not overwrite later governance. They establish the accepted bounded evidence base. Current publication identity and runtime geometry governance are enforced independently by current code.

## Identity rule

The profile loader applies the public-identity publication contract **and** requires an explicit `AUTHORITATIVE` identity status for every Person in this bounded profile.

- `PROVISIONAL` fails closed under the general publication policy.
- A missing identity status also fails closed as `PRODUCTION_PROFILE_AUTHORITATIVE_IDENTITY_REQUIRED`.
- `MERGED`, `BLOCKED`, or any other non-`AUTHORITATIVE` value does not satisfy the production profile.
- The acceptance receipt's `person_identity_status` must exactly match the current package.

For the current Day 12 source state, Gina Hinojosa and Sarah Eckhardt were resolved to `AUTHORITATIVE` in the governed Texas workbook on September 6, 2026 after independent official member-page and Texas Legislative Reference Library corroboration. Their original `provisional_source_record_id` lineage remains preserved. See `texas-person-identity-resolution-v0.1.md`.

Resolving identity changes the package content and therefore requires a newly built package and newly hash-bound bounded acceptance receipt. Removing a provisional marker or warning without an explicit authoritative disposition is not a valid release procedure.

## Atomic public projection

The production-profile representation consumer queries both governed bindings against the supplied Civic GPS result. Either both resolve and project or the entire bounded view fails closed. A successful House result is never returned by itself when the Senate binding fails, and vice versa.

The bounded profile is representation-only. Attempts to route it through Full Essentials fail closed.

## Geometry governance

Geometry-version governance remains enforced by the Texas legislative runtime contract. The profile does not weaken or replace the live preflight. When the Texas runtime is activated, service-marker drift must still produce `GEOMETRY_VERSION_DRIFT` before a legislative representation claim is returned.

## Activation boundary

This change intentionally adds **no** `state_legislative_representation` entry to `package_catalog.v0.1.json`. Production support and production activation are separate decisions.

Activation requires a later governed change containing, at minimum:

1. the exact successor production package artifact reflecting the authoritative Person statuses;
2. a current bounded acceptance receipt bound to that exact package;
3. explicit `AUTHORITATIVE` identity status for both Persons;
4. exact House and Senate catalog bindings;
5. production deployment validation against the hosted/runtime path;
6. explicit catalog/registry activation approval.

Until then, `REPOSITORY_ACTIVATION = NOT_ACTIVATED`.

## Verification

```sh
python tests/test_tx_production_profile.py
python tests/test_texas_bounded_contract.py
python tests/test_public_identity_disposition.py
python tests/test_role_term_integration.py
python tests/empowered_vote_package_catalog_test.py
```

The profile suite proves that the ordinary package loader remains strict, the alternate loader preserves source blockers and source address-control state, provisional identities remain blocking, missing identity status cannot masquerade as resolution, explicit authoritative identity is required, acceptance-receipt drift fails closed, both legislative bindings are atomic, Full Essentials cannot use the profile, and the default catalog remains unactivated.
