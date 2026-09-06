# Texas bounded release authorization and publication v0.2

Status: `PUBLICATION_EXECUTION_AUTHORIZED__PENDING_MAIN_EXECUTION_MERGE`

This phase executes the previously authorized **bounded runtime release** for Texas House District 49 + Senate District 14. It does not publish raw successor-package bytes, redeploy Railway, widen civic-data scope, or write canonical civic facts.

## Evidence chain

Governed inputs under `data/packages/tx/legislative/` remain:

- post-activation hosted evidence: `ed079fdfade76c06271f4b6be57fc669db7586b2ad66dc56ec13e3694f2abfb6`;
- merged runtime release readiness: `abeacad639da187818748c5af70e9df05fab27bf52101d270b7cd9c133f0c031`;
- release authorization: `7bf9a8ecf9c101e9faee4389f925f469fd1d37934cc1d3dc9bfd6a890989d6de`;
- publication execution authorization: `4f2b11aa0a51bf3df3eb869b349679906910f0e44440f602fad4eea26a9ce694` under the repository canonical JSON contract.

Release authorization became active on `main` at:

`defefa6d31987187839fa90434b201a287518e34`

The execution receipt binds the GitHub Release target to that exact commit.

## Publication surface

The public surface is a **manifest-only bounded runtime release**:

- tag: `tx-legislative-two-office-v0.1`;
- title: `Texas bounded legislative representation v0.1`;
- target commit: `defefa6d31987187839fa90434b201a287518e34`;
- runtime endpoint: `https://texas-bounded-api-production.up.railway.app`;
- release asset: `texas-bounded-runtime-release-manifest-v0.1.json` only.

The following remain false:

- raw package bytes published;
- source-package `publication_eligible`;
- registry-layer `publication_eligible`;
- statewide Texas completeness;
- Full Essentials support;
- election support;
- Railway redeploy;
- canonical writes.

## Execution receipt

`publication-execution-authorization-v0.1.json` uses schema `texas-bounded-publication-execution/0.2` and records:

- `execution_authorized=true`;
- `github_release_creation_authorized=true`;
- `authorization_main_sha=defefa6d31987187839fa90434b201a287518e34`;
- `publication_target_sha=defefa6d31987187839fa90434b201a287518e34`;
- `railway_redeploy_authorized=false`;
- `canonical_writes=0`.

The later merge SHA that carries this receipt is intentionally **not** self-referenced in the receipt. It is recorded as `execution_head_sha` inside the generated release manifest.

## Execution trigger

`.github/workflows/texas-bounded-publication.yml` runs read-only validation on pull requests. The actual publish job can run only on a push to `main` whose commit message contains:

`[execute-tx-publication]`

The publish job validates the deterministic execution receipt, builds the governed manifest, refuses to overwrite an existing tag, creates the manifest-only GitHub Release against the authorized target commit, and verifies the exact single-asset result.
