# HI roster refresh — review candidate

All five existing county/county-equivalent jurisdictions are internally complete after the September 19, 2026 roster refresh. This candidate has not been merged, released, deployed or selected by a consumer catalog.

## Changes

- Direct official pages confirm all 38 existing holders. The Hawaiʻi mayor and three Kauaʻi council pages were verified in a browser after search retrieval returned 403. Four earlier indexed-only observations remain in history as CAPTURED/MEDIUM; four new direct observations are NORMALIZED/HIGH.
- Kauanoe Batangan's role selection method changes from ELECTED to APPOINTED, supported by the county's December 16, 2025 announcement. No exact actual service interval is inferred.
- Sixteen old normalized assertions now point to the existing durable offices: seven Kauaʻi council assertions and nine Maui council assertions. Prior subject IDs remain in the assertion notes; names and observed source text are preserved.
- Ten maintenance QA rows now contain a single valid primary source_id. Supporting source IDs remain in notes.
- Legacy warning messages are preserved and given explicit nonblocking jurisdiction/entity fields for the strict validator.

## Verified controls

| Control | Result |
| --- | --- |
| Existing jurisdictions | 5 |
| Directly verified current holders | 38 / 38 |
| Seat capacity / current RoleTerms | 38 / 38 |
| Recorded QA checks passing | 83 / 83 |
| Source evidence records | 43 |
| Source assertions | 82 |
| Current complete / parity flags | 5 / 5 each |
| Open source-access gaps | 0 |
| Open publication gap | 1, nonblocking |

The 83 QA rows consist of 70 historical checks and 13 maintenance checks. Historical address, geography and other checks retain their original dates; they were not freshly re-executed as part of this roster review. The current evidence confirms the modeled holders, not every possible elective or appointed office beyond the established v0.1 scope.

## Source and package boundaries

The source snapshot is `candidates/hi/hi-refresh-20260919/source/hi-refresh-20260919.json`, from the existing HI factory. It preserves native values, headers and source row numbers. Canonical candidate JSON and deterministic CSV mirrors are under `candidates/hi/hi-refresh-20260919/normalized/`. Each dated ZIP has matching base64 parts under `candidates/hi/hi-refresh-20260919/packages/`.

The five August 23 packages and their published hashes are unchanged. Schema version remains 0.1; the September 19 date identifies the successor artifact revision. Government identity, geography, offices, divisions, leadership records and identifier records match the old packages. Honolulu remains consolidated, Kauaʻi retains its seven-seat unnumbered council office, Maui retains countywide election with residency-qualified seats, and Kalawao retains zero autonomous elected county offices.

These files contain governed facts, paraphrased observations and citation metadata. Source documents and copied page bodies are not redistributed. The existing Maui consumer-release work and consumer catalogs are unchanged. Candidates live outside the automatically discovered `data/packages/` directory; a regression test confirms all five consumer discoveries still select the original published hashes. The initial PR placement caused ambiguous package discovery and was corrected before review. Existing activation guards are unchanged.

## Reproduce and verify

From the repository root, with Python 3:

```bash
python tools/hi_factory_refresh.py
python tests/test_hi_factory_refresh.py
python tools/hi_factory_refresh.py --verify
python tests/test_package_archives.py
python tests/ev_kauai_countywide_preview_test.py
python tests/ev_maui_countywide_preview_test.py
```

`--verify` checks the strict and legacy contracts, source/assertion joins, unchanged identities and structure, tracker gates, file inventories, checksums, and byte-identical ZIP/base64 reconstruction. Exact successor and baseline hashes are in `hi-refresh-20260919-validation.json`.

Approval can authorize merging this isolated review bundle. Promotion into governed data/package paths requires a separate publication change with explicit version selection and existing activation checks. After publication, reconcile the live tracker with the actual merge/release and close the publication gap; do not treat this review candidate as already published.
