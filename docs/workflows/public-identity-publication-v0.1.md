# Public identity publication disposition v0.1

Status: `RESOLVED_INTERNAL_ONLY`

This contract governs whether a Person identity that is explicitly marked provisional may cross a public or production consumer boundary. It preserves internal evidence and does not declare the underlying officeholder fact false.

## Decision

`PROVISIONAL` Person identities are **internal-review only** and are **not publication eligible by default**.

A provisional Person record may remain in a staged/internal jurisdiction package with its canonical or provisional ID, observed name, RoleTerm relationship, source lineage, and warnings intact. Internal retention is required for auditability and does not itself authorize publication.

Public or production consumers must fail closed if either condition is present:

1. any Person explicitly carries `PROVISIONAL` in one of the recognized identity-status fields: `person_status`, `identity_resolution_status`, `status`, or `current_status`; or
2. package warnings explicitly retain a provisional-person warning (`status=PROVISIONAL` plus a Person reference or `PROVISIONAL-PERSON:` warning ID).

The public/production error is `PACKAGE_PUBLIC_IDENTITY_UNRESOLVED`.

The existing representation consumer retains its more specific holder-level failure `PERSON_IDENTITY_PROVISIONAL`. The bounded Texas preview is an explicit exception only for `INTERNAL_REVIEW`; it must remain `publication_eligible=false` and preserve visible provisional warnings.

## Compatibility

This policy is intentionally separate from generic package construction and identity-graph validation. Internal packages may still be built and validated while a Person identity is provisional.

Legacy packages that never declared identity status are not reclassified as provisional merely because they lack a newer status field. Absence of a status is not treated as proof of either provisional or resolved identity. Existing production packages therefore remain compatible unless they explicitly carry a provisional Person marker or warning.

## Enforcement points

The shared `validate_public_identity_disposition` contract is defined in `tools/jurisdiction_package.py` but is not called by generic `validate()`.

Empowered.Vote enforces the contract at public/production boundaries in `consumers/empowered_vote/package_source.py`:

- governed package loading;
- direct representation projection;
- Full Essentials eligibility/build entry.

This prevents an in-memory caller or a validly checksummed package from bypassing the public identity rule.

## Resolution requirement

A provisional identity becomes publication-eligible only through a governed upstream identity-resolution change supported by the applicable evidence and QA process. Removing or changing a provisional marker merely to satisfy the consumer gate is not an accepted resolution.

For the bounded Texas House 49 / Senate 14 candidate, the existing staged Person identities may continue to participate in internal acceptance and parity work. They may not be emitted as public officeholders until the identity-resolution process changes their actual governed disposition.

## Scope

`PUBLIC_IDENTITY_PUBLICATION_DISPOSITION = RESOLVED_INTERNAL_ONLY` means the policy question is closed: provisional Persons are internal-only and public consumers fail closed.

It does **not** mean:

- the Texas Person identities have been resolved;
- the bounded Texas package is production-profile compatible;
- the package is complete statewide;
- production deployment has been validated;
- merge, release, publication, or activation is authorized.

Those remain separately governed.
