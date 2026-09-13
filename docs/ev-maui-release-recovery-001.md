# Maui existing-draft recovery

## Incident and observed state

Manual run `34776975180`, job `103776766384`, executed the authorized workflow on main `6260d0c6da3971f2e13309e3746c51cc02044543`. Approval and fresh-source validation passed. The workflow created draft release `388004869`, uploaded asset `561768290`, and verified its downloaded bytes. It then failed with `EXACT_LIGHTWEIGHT_TAG_REQUIRED` during `CREATE_OR_VERIFY_EXACT_TAG`.

The retained receipt has completed phases `PREFLIGHT`, `CREATE_DRAFT`, `UPLOAD_ONE_MANIFEST`, and `VERIFY_DRAFT_ASSET`. No publication mutation was attempted. The draft, asset and lightweight tag exist; current exact-ref and matching-ref reads both show the approved target. Reconciliation also confirmed the existing body, asset ID/size/digest, original eight CI results, approval freshness and preserved external boundaries. A delayed or stale tag response is a plausible explanation, not established by the retained failure logs.

Do not rerun the original create workflow or publish through an unverified alternate path. Existing objects are reconciled by this separate guarded recovery. The original executor and its workflow remain unchanged.

## Fixed recovery scope

- Base: `6260d0c6da3971f2e13309e3746c51cc02044543`.
- Base tree: `78975d979409484ee4f6318d17a6c6e0436154f6`.
- Exactly seven added paths, listed in the contract; all existing repository files preserved.
- Existing release: `388004869`; existing asset: `561768290`.
- Tag: `maui-mayor-council-integration-v0.1`.
- Original integration target: `2b3e8d5df11ed4f4b19f7579c9bd1663131070bf`.
- Sole asset: `maui-mayor-council-integration-manifest-v0.1.json`, 5,596 bytes, SHA-256 `eb577b26a899f5e03bb6450225438bcbebd0efb3b53993e14426eddb8506683a`.
- Recovery contract SHA-256: `f0eefc2f93de9d95477796603bdb3b7297cd71d4b1830eace271015f36276a2c`.

The original failure receipt is retained byte-for-byte and pinned by SHA-256 `c997dd25cb7d5348f4ffe480590181b1016c46173fae34d34743765782204601`. It came from artifact `10323877402`, archive SHA-256 `f84a9546af7ee67a7671e78b671ddf9800471a6fb83ac1c7cf96e907d797bb71`. The original executor and workflow hashes are pinned too.

## Approval, evidence and execution

The committed recovery template is unapproved. A new recovery receipt must bind the approved recovery main head, its certified PR head, contract, existing release/asset IDs, retained failure receipt, immutable asset, and current source review. The previously granted publication authorization remains in the historical failure receipt; it is not treated as an unrestricted or perpetually fresh execution credential.

Execution requires manual dispatch on exact main with `execute: true`, fresh approval and fresh primary-source evidence no more than 24 hours old, and the unchanged October 12, 2026 UTC exclusive acceptance cutoff. The authenticated operator establishes the meaning and authority of the evidence and approval. The code verifies bindings, integrity and age; it does not create approval from an unapproved template or change observation timestamps.

Before writing, the runner checks:

1. All immutable local inputs and the pinned failed-execution receipt.
2. The original failed manual run identity, head, workflow, conclusion and attempt.
3. Original PR #67 and the recovery PR: exact scope, squash parent, certified tree and all latest applicable CI results. The original eight and recovery seven named workflows are required.
4. Current main, the exact existing tag, unique matching release, original unchanged release body, sole asset identity and freshly downloaded asset bytes.
5. Texas/Kauaʻi releases and the Railway Git source pin, compared with the original preflight boundary record.

Immediately before publication it repeats approval/source freshness, immutable-input, context, draft/tag, fresh asset download and external-boundary checks. Only then can the API client issue `PATCH releases/388004869` with exactly `{"draft": false, "make_latest": "false"}`. All other writes, including POST and DELETE, are rejected by the client even when its write switch is enabled.

After that one request, it verifies the published release and downloads the sole asset again. Published readback may repeat at most three times, waiting one second between reads. Only reads repeat; no write is automatically retried. This tolerates a transient readback delay while preserving the fail-closed final result. Ambiguous publication or failed final verification retains the known IDs and an unknown completion result for reconciliation. No rollback or cleanup is claimed.

## Preserved boundaries and current hold

Creating or merging this recovery candidate does not publish anything. PR/default manual candidate jobs have read-only permissions and make no release mutations. The write job is restricted to explicit manual main dispatch with current bound approval. Its concurrency group matches the original release workflow.

The recovery never creates a release, uploads an asset, creates or retargets a tag, deletes an object, promotes a catalog entry, changes canonical data, deploys, or performs Kalawao work. Texas remains latest. Existing Texas and Kauaʻi releases and their assets remain pinned. The Railway source check does not certify live deployment inventory. Exact tenure intervals, full Essentials, complete jurisdiction coverage and a hosted Maui endpoint remain outside this release's certified scope.

## Verification

```sh
python tests/ev_maui_release_recovery_test.py
python tests/ev_maui_release_execution_test.py
python tests/ev_maui_publication_candidate_test.py
python tools/ev_maui_release_recovery.py --repo-root . \
  --output-dir artifacts/ev-maui-release-recovery/local-held
```

Recovery tests use an in-memory API. They cover approval/source tampering and expiry; original/recovery CI, scope, failed-run provenance and external drift; altered draft/body/tag/asset bytes or IDs; already-published state; exactly one permitted PATCH; a transient stale read; an ambiguous write; final-read failure; output safety; and seven-addition scope. Live regressions remain in the existing Maui/Kauaʻi lanes. Civic GPS may satisfy its unrelated-path gate without rerunning broad smoke steps.
