# EV-KAUAI-RELEASE-EXECUTION-CANDIDATE-001

This candidate prepares a guarded, metadata-only GitHub release executor. Its default
operation builds one held manifest asset and performs no remote writes. Preparing or
merging this code does not authorize a tag, draft release, upload, publication, or deployment.

## Exact preparation and release boundaries

| Item | Exact value |
| --- | --- |
| Preparation base | `028c7c2241a9302c8b481c4ceeab2a73319c4aba` (PR #61 squash) |
| Preparation base tree | `e0db7d510d8d3855b9eeaddee8d4fc4311197e0a` |
| Certified manifest head | `352fceebc010426195e481eb02aca6ea870e94de` |
| Future release target | `a24dd03a9958ffe7bc7a5ba2d0808ef9d1d81eed` (PR #60 integration) |
| Future target tree | `71c9f04666fff5789d2d52f41a4284b9570a29bb` |
| Proposed tag | `kauai-mayor-council-integration-v0.1` |
| Sole uploaded asset | `kauai-mayor-council-integration-manifest-v0.1.json` |
| Asset bytes / SHA-256 | 4,593 / `7a40e104999c2bb891b5ecadb2dfefec511f1fcc783e122f7cd31402987f850f` |
| Contract SHA-256 | `c7f7b2d91766d40fff8965130d708fef26d623198cb8bf64f7bc59c921b4fb15` |
| Source review expiry | December 1, 2026 UTC; unchanged |

Exactly eight paths are added: the executor, its tests and workflow, contract, unapproved
approval template, partial source recheck, release notes, and this document. Existing
files are preserved. The executor checks the original package, acceptance receipt,
production spec, catalog, routing, core runtime, retained live evidence, manifest, and
schema against their existing contracts and hashes. No production flag is flipped.

The manifest is immutable preparation metadata. Its original held status and false
authorization flags remain in the asset bytes. A later, separately authorized metadata
distribution records its authority in the execution receipt and release body; it does
not promote package eligibility or certify a hosted Kauaʻi API. The only represented
scope remains Mayor plus the unnumbered seven-seat countywide Council. Prosecuting
Attorney, Full Essentials, election results, and complete-jurisdiction coverage are excluded.

## Source recheck and publication hold

The September 10 state election directories directly corroborated the packaged Mayor
and seven Council incumbents. The state proclamation corroborated seven at-large seats
and the December 1 local-noon transition; the earlier UTC expiry remains conservative.
The State procurement directory corroborated Council Chair Mel Rapozo.

Direct retrieval of both Kauaʻi Council pages returned HTTP 403. Indexed official
excerpts corroborated the retained Chair and Vice Chair but do not establish a fresh
direct leadership review. The committed recheck is therefore `PARTIAL`, with blocker
`LIVE_COUNCIL_LEADERSHIP_RECHECK_REQUIRED`. It cannot authorize execution.

A later complete recheck must directly support Mayor and Council roster, Chair and
Vice Chair, countywide scope, and term transition from primary sources. It must match
the existing package hashes, be at most 24 hours old, precede the unchanged expiry,
and preserve the production receipt. The approval binds the exact recheck bytes.
The executor validates a review receipt; it does not scrape websites or independently
establish the truth of a reviewer's assertions. A reviewer must retain the actual
primary-source evidence for that later decision. An indexed excerpt is insufficient.

## Separate authorization required for future execution

The committed approval template has `approved=false` and `publication_authorized=false`.
It is not an execution credential. The live executor rejects it before even an API read.
A later receipt must bind repository, tag, original release target, manifest and notes
hashes, contract hash, complete source-recheck hash, merged execution head, certified
candidate head, PR number, operation ID, and explicit approval reference. Approval
lasts at most 24 hours. Deployment, catalog promotion, Kalawao work and canonical
writes remain prohibited even in a publication approval.

JSON cannot authenticate a person's approval. The trust boundary is the repository's
authenticated operator performing a manual dispatch after obtaining that separate
approval. Never fill or dispatch the template merely because this candidate passed CI.
The workflow has no push-triggered execution and defaults `execute` to false. Its write
job requires manual dispatch on `main`, the exact dispatched SHA, and validated external
approval and recheck inputs. The normal PR job has only contents-read permission.

Before writes, the executor independently verifies the approved PR is merged to the
exact current `main`, its base is this preparation base, its eight changes are additions,
and the squash tree matches the certified candidate tree. All applicable exact-head PR
workflows must be successful, including this lane, production activation, adapter, and
Civic GPS smoke. Civic GPS may correctly gate off route probes when these eight paths
do not affect routing. Workflow success alone does not claim those probes executed.

Run the held offline preparation with:

```sh
python tests/ev_kauai_publication_candidate_test.py
python tests/ev_kauai_release_execution_test.py
python tools/ev_kauai_release_execution.py --repo-root . \
  --output-dir artifacts/ev-kauai-release-execution/local-candidate
```

CI adds exact-head/base verification and read-only destination checks. Those reads see
only releases visible to the token. Actual execution repeats preflight with its write
credential; no preview asserts privileged visibility of all drafts.

## Release sequence and recovery

1. Validate separate approval, fresh source review, immutable inputs, merged candidate,
   successful CI, original target tree, absence of the exact proposed tag/release,
   Texas release fingerprint, and Railway source pin.
2. Create a **draft** release targeting the original integration SHA, with the fixed
   release notes and execution references; set `make_latest` to `false`.
3. Upload exactly one JSON manifest. Fetch the draft and all its assets; verify the
   asset name, content type, state, length, server digest, and downloaded bytes.
4. Create the lightweight tag atomically if the draft API has not created it, then
   verify that it points directly to the original integration commit. Never retarget.
5. Recheck authority, source freshness, local inputs, current main/CI, external
   boundaries, draft metadata, single asset and bytes, and exact tag.
6. Publish the verified draft with `make_latest=false`. Read the published release,
   tag and bytes again, verify external boundaries, and retain the execution receipt.

GitHub's release API ignores `target_commitish` if a tag already exists; this is why
preflight refuses an existing exact tag and later verifies the Git ref itself. No
existing release or asset is overwritten. No delete API is implemented. Partial
failures retain the last phase and any known release/asset IDs, mark publication
completion unknown, and require explicit reconciliation. Network timeouts may follow
a successful remote write. Never retry, delete, retarget, or claim rollback automatically.
Even a final readback failure after publication remains a failed verification.

The executor uses fixed GitHub repository/hosts, finite pagination, no automatic retries,
and no authenticated redirects. An asset-storage redirect is followed only to HTTPS
GitHubusercontent storage with a fresh unauthenticated request. HTTP 403 and other
errors are never interpreted as an absent destination.

GitHub may require a separately provisioned token with Workflows-write permission to
create a tag/release at this older commit because its workflows differ from the default
branch. The future manual job can use `KAUAI_RELEASE_TOKEN` when explicitly configured;
otherwise it uses the job token. No credential is created or permission increased here.
A permission error must stop execution; never change the release target to avoid it.
See GitHub's [release API](https://docs.github.com/en/rest/releases/releases),
[asset API](https://docs.github.com/en/rest/releases/assets), and
[Git refs API](https://docs.github.com/en/rest/git/refs).

## External boundaries and validation limits

Texas release `383744766` remains targeted to
`defefa6d31987187839fa90434b201a287518e34`, with its single 1,766-byte asset
`547794640`, SHA-256
`80bcb6f3d4d668ce62af84450b1db726156c0beaf7bc24b053b8c6291704cffe`.
Railway's source ref remains `agent/day12-tx-post-activation-runtime-v0.2` at
`bf95d7e79c8cfc8be644326d0b0ea2c1065b0a67`. A source-ref check is not a live
Railway deployment inspection. This executor has no deployment API.

The original activation evidence remains a retained live run with two Līhuʻe positives
and one Hilo rejection. Raw negative geography was not present in that original
artifact; its certified runner assertion remains the evidence basis. Retention does
not refresh that evidence or extend source review. Existing tenure and unnumbered
Council warnings remain.

Tests exercise actual immutable inputs, all approval bindings, stale and incomplete
source review, primary/direct leadership requirements, exact merged context, collision
rejections, tampered assets and targets, successful request order, partial failures,
repeat execution, final readback failures, output path guards and redirect handling.
Every test publication request uses an in-memory fake API. These tests do not certify
live GitHub publication permissions or perform a release, tag, upload, or deployment.
