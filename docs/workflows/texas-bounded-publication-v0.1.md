# Texas bounded release authorization and publication v0.1

Status: `RELEASE_AUTHORIZED__PUBLICATION_NOT_EXECUTED`

This phase authorizes the **bounded runtime release workflow** for the Texas House District 49 + Senate District 14 representation profile. It does **not** execute publication, create a GitHub Release, redeploy Railway, widen civic-data scope, or write canonical civic facts.

## Evidence chain

The governed chain is committed under `data/packages/tx/legislative/`:

- post-activation hosted evidence: `ed079fdfade76c06271f4b6be57fc669db7586b2ad66dc56ec13e3694f2abfb6`;
- merged runtime release readiness: `abeacad639da187818748c5af70e9df05fab27bf52101d270b7cd9c133f0c031`;
- release authorization: `7bf9a8ecf9c101e9faee4389f925f469fd1d37934cc1d3dc9bfd6a890989d6de`.

The authorization basis is the v0.2 runtime merge on `main` at:

`2570cba11d218ab32588a30ef6c43a7fce5c2f7c`

The independently validated post-activation hosted runtime remains bound to exact deployment head:

`bf95d7e79c8cfc8be644326d0b0ea2c1065b0a67`

## Authorization boundaries

`release-authorization-v0.1.json` records:

- `release_authorized=true`;
- `publication_workflow_authorized=true`;
- `publication_execution_authorized=false`;
- `github_release_creation_authorized=false`;
- `railway_redeploy_authorized=false`;
- `canonical_writes=0`.

The runtime service contract itself remains non-self-authorizing. Release authority is carried only by the separate governed release receipt.

## Publication surface

The proposed public surface is a **bounded runtime release**, not publication of the raw successor package.

Proposed release identity:

- tag: `tx-legislative-two-office-v0.1`;
- title: `Texas bounded legislative representation v0.1`;
- runtime endpoint: `https://texas-bounded-api-production.up.railway.app`;
- release asset: `texas-bounded-runtime-release-manifest-v0.1.json` only.

The following remain false:

- raw package bytes publishable;
- source-package `publication_eligible`;
- registry-layer `publication_eligible`;
- statewide Texas completeness;
- Full Essentials support;
- election support.

## Workflow execution locks

`.github/workflows/texas-bounded-publication.yml` always runs a read-only authorization gate on relevant pull requests and `main` pushes.

A publication execution can run only through manual `workflow_dispatch` in `publish` mode and requires all of the following:

1. the dispatch ref is exactly `main`;
2. the human confirmation token is exactly `PUBLISH_TX_HOUSE49_SENATE14`;
3. `data/packages/tx/legislative/publication-execution-authorization-v0.1.json` exists;
4. that receipt has schema `texas-bounded-publication-execution/0.1`;
5. it authorizes the exact dispatch `GITHUB_SHA`;
6. it authorizes GitHub Release creation;
7. it keeps Railway redeploy and canonical writes forbidden;
8. the governed release tag does not already exist.

No execution-authorization receipt is created in this phase, so the publish job currently fails closed before any GitHub write.

## Future execution authorization

A separate explicit governance decision is required before publication. That future phase must create an execution receipt bound to the exact publication `main` SHA and then separately authorize dispatching the publication workflow.
