# Maui held release-execution candidate v0.1

This candidate prepares a guarded, separately authorized release of the existing Maui integration manifest. Preparing or merging this candidate does not publish a release.

## Fixed scope

- Preparation base: `9e3e85a2a16cef0387b9f76cdcd7e01aaca5c419` (PR #66 squash).
- Base tree: `a4079595d7f91a6e3f3631060601a388214aaae3`.
- Certified publication candidate: `33d1e2bd34804dc5e188d4e9b7db8be0002f937e`.
- Integration target remains `2b3e8d5df11ed4f4b19f7579c9bd1663131070bf`.
- Proposed tag: `maui-mayor-council-integration-v0.1`; preparation never reserves it.
- Sole proposed asset: `maui-mayor-council-integration-manifest-v0.1.json`, exactly **5,596 bytes**.
- Asset SHA-256: `eb577b26a899f5e03bb6450225438bcbebd0efb3b53993e14426eddb8506683a`.
- Execution contract SHA-256: `f335177c734bdf07d94df9105677776f87d88ec3161a45a4df82a62126952c5d`.

The diff is exactly eight additions and two modifications. The shared Maui diff guard gains a separate exact-base, exact-tree, ten-path mode. The publication workflow uses that guard while retaining all manifest/schema, production-input, retained-evidence and destination checks. The original manifest builder and original manifest/evidence bytes remain unchanged.

The contract enumerates all ten paths and their required added/modified statuses. A wrong base, dirty tracked checkout, renamed path, additional change, or altered immutable input fails closed. All six production catalog entries, acceptance records, packages, core runtime and deployment configuration remain unchanged.

## Source evidence

`source-recheck.json` records a fresh direct review of **13 official pages and 25 normalized assertions**, completed at `2026-09-13T15:55:35.047235+00:00`: PASS, zero blocking gaps. It binds ten holders, nine residency areas, two leadership roles, countywide voting scope, the appointed Batangan selection, term policy, and Wailuku/Lānaʻi address controls.

Each source records retrieval time, final official URL, HTTP status, complete-response hash and hashed noncontiguous text fragments. Assertion-to-source joins are checked; normalized substantive bindings are pinned independently of observation IDs. Candidate integrity validates the committed review at its recorded time. Future execution requires every source retrieval and completed review to be no more than 24 hours old at the actual execution clock.

The evidence review is an authenticated operator responsibility. The executor validates review structure, hashes, substantive bindings, parity and age; it does not independently scrape or decide whether a new excerpt proves a claim. Refreshing evidence requires a real fresh primary-source review, not changing timestamps on this historical record. Complete source evidence does not grant publication authority.

The accepted production source-review cutoff remains **2026-10-12 UTC, exclusive**. This candidate does not extend acceptance, resolve exact canonical tenure intervals, or certify a hosted endpoint.

## Held preparation and later approval

PR checks and default manual runs use read-only repository access. The execution checkbox defaults to false. The committed approval template has `approved: false` and `publication_authorized: false` and is rejected before even a read request.

Later execution requires separate publication authorization and a bound receipt naming the exact main head, merged candidate PR and its certified head, contract/notes/asset hashes, fresh source-review hash, approval reference, operation ID and a maximum 24-hour approval window. The executor verifies a squash commit with the approved preparation parent and a tree identical to the certified PR head, the exact ten-path diff, and all latest applicable CI runs. Eight named workflows must have succeeded on the certified candidate head.

An authenticated repository operator supplies the separately approved receipt to a manual dispatch on exact main. The dispatch event, repository access and operator review provide authority; user-supplied JSON is not a cryptographic signature. The write job cannot run on a PR, a push, or a non-main manual dispatch. No automatically approved receipt or dispatch is included here.

## Execution and recovery contract

After all approval, evidence, immutable-input, merge/CI, destination and external-boundary checks pass:

1. Create one draft release with `make_latest: "false"`.
2. Upload the exact existing JSON manifest and verify its metadata and downloaded bytes.
3. Create or verify the exact lightweight tag at the original integration target.
4. Recheck approval freshness, evidence, inputs, main/CI, draft asset, tag and external boundaries.
5. Publish with `make_latest: "false"`, then verify the published release, sole asset bytes, tag and preserved boundaries.

No raw package, roster payload, approval document or verification report is a release asset. Manifest preparation-time false authorization flags remain unchanged; the future release body appends separate execution references.

Existing tags/releases fail closed without overwrite, deletion or automatic retry. Ambiguous network failures retain the last phase and known release/asset IDs and require reconciliation; the tool never claims rollback or successful publication without final readback. It never cleans up or retargets an existing tag.

## External boundaries

Texas release `383744766` remains the latest release, targeting `defefa6d31987187839fa90434b201a287518e34`, with asset `547794640` (1,766 bytes; SHA-256 `80bcb6f3d4d668ce62af84450b1db726156c0beaf7bc24b053b8c6291704cffe`).

Kauaʻi release `387664986` remains at `a24dd03a9958ffe7bc7a5ba2d0808ef9d1d81eed`, with asset `559746136` (4,593 bytes; SHA-256 `7a40e104999c2bb891b5ecadb2dfefec511f1fcc783e122f7cd31402987f850f`).

The Railway source ref `agent/day12-tx-post-activation-runtime-v0.2` remains `bf95d7e79c8cfc8be644326d0b0ea2c1065b0a67`. This verifies the Git source pin, not live Railway deployment inventory.

Canonical writes: **0**. Catalog promotion: **false**. Deployment authorization: **false**. Kalawao work: **false**.

## Verification

Offline tests use an in-memory API only. They cover held approvals, altered approval bindings, stale/future/incomplete/tampered sources, normalized record and source-join drift, merge/CI/diff and external-boundary failures, collisions, wrong target/asset/tag, the successful ordered sequence, repeat execution, ambiguous partial failure, failed final readback, unsafe output paths and credential-free asset redirects.

Run:

```sh
python tests/ev_maui_release_execution_test.py
python tests/ev_maui_publication_candidate_test.py
python tests/ev_maui_production_activation_test.py
python tools/ev_maui_release_execution.py --repo-root . \
  --output-dir artifacts/ev-maui-release-execution/local-held
```

CI additionally verifies the exact Git head/base/diff, performs read-only destination checks, retains the held bundle, and runs existing live Maui/Kauaʻi/Civic GPS regression lanes.
