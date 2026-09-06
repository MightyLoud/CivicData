# Texas bounded legislative successor package v0.1

Status: `SUCCESSOR_PACKAGE_AND_RECEIPT_ISSUED_NOT_ACTIVATED`

Issued: September 6, 2026.

This artifact supersedes the **package bytes** of the earlier provisional-identity Texas House 49 / Senate 14 candidate. It does not rewrite or invalidate the historical evidence archive, historical package hashes, or earlier acceptance records. The old artifacts remain historical evidence of the state that was actually tested at that time.

## Current bounded package

Profile: `tx_legislative_two_office_v0.1`

Coverage:

- Texas House District 49;
- Texas Senate District 14;
- both bindings required atomically;
- representation only;
- omitted data means `NOT_INCLUDED_NOT_ABSENT`;
- `complete_jurisdiction=false`;
- Full Essentials and election scope unsupported.

The package contains exactly:

- 2 canonical Divisions;
- 2 canonical Offices;
- 2 canonical Persons;
- 2 canonical CURRENT RoleTerms;
- 10 package provenance evidence records;
- 8 claim assertions;
- 5 explicit bounded-scope limitations;
- 0 source-package address tests.

The canonical jurisdiction, Division, Office, Person, RoleTerm, and SourceRecord IDs are passed through from the governed Texas workbook. No labels mint IDs.

## Identity and temporal state

Both Persons are explicit `AUTHORITATIVE`:

- Gina Hinojosa — House District 49;
- Sarah Eckhardt — Senate District 14.

Both RoleTerms remain `CURRENT` with current-service start `2025-01-14`. Actual end dates remain blank. Published future term endpoints in LRL are retained only in evidence summaries and are not written as actual ends.

The original `provisional_source_record_id` remains on both Persons as lineage. Identity resolution does not erase the earlier source observation.

## Bounded source QA

`parity_ok=true` and `qa_fail_count=0` apply to the exact exported two-chain graph. Five limitations remain intentionally visible:

1. `BOUNDED_TWO_OFFICE_SCOPE`;
2. `SOURCE_PACKAGE_ADDRESS_CONTROLS_EXTERNAL`;
3. `FULL_TEXAS_ROSTER_NOT_INCLUDED`;
4. `FULL_ESSENTIALS_UNSUPPORTED`;
5. `ELECTION_SCOPE_UNSUPPORTED`.

These are current bounded-package limitations. They are not relabeled historical source defects and they are not cleared to force the generic full-jurisdiction loader to pass.

## Hashes

- `jurisdiction.json`: `a43aa6517ea5a6822319298ee6cbacc83be6f3a8731568863243439a5f802530`
- deterministic package ZIP: `7b6abf28e0535041797b180488cb98ebf223b844b3081e7386ccbd63c85762b1`
- fresh acceptance receipt file: `3b204dc1d7c4c9442bf61fe422f3de907dfed0bd567ae15ffa6e853ab5399f96`
- fresh receipt deterministic digest: `f58251a3a127841ec1773a342336d01145aca47d61957ea4bfd1e81121266483`

The source workbook snapshot is `TX_ELECTIONS_Data_C6`, file ID `1xG1J2fliSTOHoohhDGbsCM4OYUJq0ArEFFLlNYWA6D8`, observed at Drive modification time `2026-09-06T19:34:37.871Z` after the identity-resolution writes.

## Fresh receipt semantics

The receipt remains schema `texas-bounded-acceptance/0.1`, but it is a **fresh successor receipt** bound to the new `jurisdiction.json` hash.

Historical live evidence is carried forward only for what it still proves without changing civic facts:

- live House/Senate geography routing;
- positive/outside-slice address behavior;
- boundary fail-closed behavior;
- accepted geometry comparisons and runtime pins.

The historical live evidence archive is pinned as:

`f8f7d11bccd35d23496cbb3cb0f4dd82f2604bf5b3ac3d3cc7799e4eccb21a39`

with tested commit:

`a9994e75d9aac62ae1ae494b8984199e7477bd6a`

The successor receipt explicitly declares:

`geometry_evidence_reuse_scope = GEOGRAPHY_ONLY__NO_OLD_REPRESENTATION_REPLAY`

The old captured representation output contained provisional Person state. It is **not** asserted equal to the successor authoritative package and is not silently rewritten.

Current representation/identity is instead revalidated deterministically from the successor package and current production-profile policy.

## Reproducibility

`tools/texas_successor_contract.py` rebuilds the receipt deterministically from:

- exact successor `jurisdiction.json` bytes;
- historical geography-evidence SHA;
- historical tested commit;
- pinned runtime SHA;
- identity-resolution head;
- governed source workbook ID and modification time;
- exact canonical House and Senate Division IDs.

`tests/test_tx_successor_package.py` reconstructs the committed base64 package archive, verifies all hashes, rebuilds the receipt, loads the package through the bounded production profile, replays the two canonical representation chains against synthetic exact district assignments, and confirms the default catalog remains unactivated.

## Activation boundary

This issuance does **not** add a Texas catalog entry or Civic GPS registry overlay. It does not perform hosted production deployment validation, merge PR #48, publish a route, or authorize release.

Current next gate:

`EXACT_HEAD_PRODUCTION_DEPLOYMENT_VALIDATION = REQUIRED`

`REPOSITORY_ACTIVATION = NOT_ACTIVATED`
