# Texas bounded release readiness v0.1

Status: `CONTRACT_IMPLEMENTED_RELEASE_NOT_AUTHORIZED`

This is a non-mutating gate between post-activation hosted validation and any future release/publication decision. It never creates a GitHub Release, changes Railway, writes canonical civic facts, or authorizes publication by itself.

## Required evidence

`tools/texas_release_readiness.py` requires:

- repository activation receipt `ACTIVATED_BOUNDED`;
- exact default catalog entry hash `1b8fd732e70b90b6ad331f71c7fe0403c061c680ad309135c28b2054a6dfb189`;
- exact default registry group hash `826ba0f04bda435c28cc4025fa253564ace9597402cecf5b2996d717565afa2a`;
- exact successor package hash `a43aa6517ea5a6822319298ee6cbacc83be6f3a8731568863243439a5f802530`;
- explicit authoritative identities for both Persons;
- post-activation hosted evidence schema `texas-post-activation-hosted-evidence/0.1`;
- exact deployed head SHA;
- all ten post-activation hosted checks at `PASS`;
- zero canonical writes;
- release/publication still unauthorized in the hosted evidence.

## Merge-aware states

The same validated runtime evidence is interpreted differently depending on whether the v0.2 runtime code is merged.

### Candidate branch

With `runtime_merged=false`, a successful gate emits:

`READY_FOR_RUNTIME_MERGE`

This means the post-activation runtime is technically validated but **cannot** be treated as release-ready because its code is not yet on `main`.

### Merged runtime

With `runtime_merged=true`, a successful gate emits:

`READY_FOR_RELEASE_AUTHORIZATION`

This is still not release authorization. The receipt continues to carry:

- `release_authorized=false`;
- `publication_workflow_authorized=false`;
- `canonical_writes=0`.

A later explicit user/governance decision must authorize any release/publication workflow.

## Scope preservation

Every readiness state remains bounded to the intersection of House 49 and Senate 14. The receipt explicitly preserves:

- `complete_jurisdiction=false`;
- Full Essentials unsupported;
- elections unsupported;
- both bindings required.

No readiness state implies statewide Texas coverage.

## Verification

Offline contract tests:

```sh
python tests/test_texas_release_readiness.py
```

After a real v0.2 HTTPS deployment, generate evidence and a candidate readiness receipt:

```sh
python tools/texas_post_activation_hosted_validation.py \
  --base-url https://<host> \
  --expected-head-sha <sha> \
  --audit-output artifacts/texas-post-activation/audit.json \
  --release-evidence-output artifacts/texas-post-activation/release-evidence.json

python tools/texas_release_readiness.py \
  --hosted-evidence artifacts/texas-post-activation/release-evidence.json \
  --head-sha <sha> \
  --output artifacts/texas-post-activation/release-readiness.json
```

Only after the runtime is merged should the same gate be rerun with `--runtime-merged`.
