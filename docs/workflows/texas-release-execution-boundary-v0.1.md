# Texas bounded publication execution boundary v0.2

Status: `PUBLICATION_EXECUTION_AUTHORIZED__NOT_YET_PUBLISHED`

The bounded Texas release authorization is active on `main` at:

`defefa6d31987187839fa90434b201a287518e34`

The execution receipt now exists at:

`data/packages/tx/legislative/publication-execution-authorization-v0.1.json`

with schema:

`texas-bounded-publication-execution/0.2`

Deterministic SHA-256 under the repository canonical JSON contract:

`4f2b11aa0a51bf3df3eb869b349679906910f0e44440f602fad4eea26a9ce694`

## Non-self-referential target binding

A receipt committed into Git cannot safely contain the SHA of the same commit that contains the receipt, because the commit SHA depends on the receipt bytes. The execution contract therefore separates:

- `authorization_main_sha`: the already-governed `main` revision at which release authorization became active;
- `publication_target_sha`: the immutable commit to which the GitHub Release tag must point;
- `execution_head_sha`: the later `main` commit that carries and executes the receipt, recorded in the generated manifest at runtime.

For this release, both governed target fields are exactly:

`defefa6d31987187839fa90434b201a287518e34`

The later execution commit does not replace or widen that target.

## Authorized execution

The receipt sets:

- `execution_authorized=true`;
- `github_release_creation_authorized=true`;
- tag `tx-legislative-two-office-v0.1`;
- `railway_redeploy_authorized=false`;
- `canonical_writes=0`.

The release remains manifest-only. Raw successor-package bytes are not release assets, and source-package / registry-layer publication eligibility remains false.

## Execution trigger

The publish job runs only on a push to `main` whose commit message contains:

`[execute-tx-publication]`

The job must validate the deterministic execution receipt, build the bounded runtime manifest, target the authorized commit above, fail if the governed release tag already exists, and verify that the resulting GitHub Release contains exactly one asset:

`texas-bounded-runtime-release-manifest-v0.1.json`
