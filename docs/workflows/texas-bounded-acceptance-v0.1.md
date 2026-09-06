# Texas bounded acceptance contract v0.1

**Disposition: the two-office slice can receive internal acceptance. It cannot
be released through the existing production jurisdiction-package profile.**

The contract preserves the staged source package and records acceptance in a
separate `texas-bounded-acceptance/0.1` receipt. The receipt resolves the bounded
coverage decision without changing source QA, clearing public-identity gaps,
creating a production catalog entry, or asserting complete Texas coverage.

## Scope and authority

| Dimension | Contract |
| --- | --- |
| Included records | Exactly two existing Divisions, Offices, Persons, and CURRENT RoleTerms: House 49 and Senate 14 |
| Address domain | Intersection of the two configured districts; both bindings must resolve |
| Consumption | Explicit internal representation preview; both projections or no partial officials |
| Civic facts | Exact hash-pinned staged package; canonical IDs pass through |
| Geography | Exact hash-pinned live evidence and its tested candidate commit |
| Omitted records | Not included; never interpreted as absent, vacant, or complete statewide |
| Unknown dates | Remain unknown; no scheduled end dates are inferred |
| Elections | Outside this profile |
| Person identity | Preserve each source status; provisional identity is not upgraded by CURRENT service |
| Publication / complete jurisdiction | Always false in this receipt |
| Production release eligibility | Always false in this receipt |

This is a narrow Texas two-office profile. Other slices require their own
coverage contract. Acceptance of the captured run does not grant acceptance to
changed sources, expanded records, a different runtime, or arbitrary new inputs.

## Machine-verifiable receipt

`tools/texas_bounded_contract.py::build_contract` consumes source-package bytes,
live-evidence ZIP bytes, both **previously reviewed** SHA-256 pins, the exact
live-tested commit, and the two explicit canonical division IDs. It performs no
network calls and returns a deterministic metadata object.

The verifier checks input hashes, evidence-to-package and evidence-to-commit
bindings, exact record scope, source identity/provenance, declared partial scope,
source parity/QA, the captured positive/negative pair, and six coordinate-level
boundary outcomes. It replays both recorded geography results through the
existing two-binding representation consumer and requires exact equality with
the saved projections. The positive output must contain both exact source
RoleTerms, Persons, Offices, and represented Divisions.

```python
from tools.texas_bounded_contract import build_contract

receipt = build_contract(
    package_bytes,
    live_evidence_zip_bytes,
    expected_package_sha256=reviewed_package_sha256,
    expected_evidence_sha256=reviewed_live_archive_sha256,
    expected_tested_commit=reviewed_live_commit,
    house_division_id=canonical_house_division_id,
    senate_division_id=canonical_senate_division_id,
)
```

Supplying the expected pins is an authority boundary: deriving new expected
values solely to make unreviewed inputs pass does not establish reviewed
evidence. A hash proves identity/integrity; the captured source records and live
controls establish the underlying claims. The tool checks and replays reviewed
evidence; it does not perform fresh source verification.

The returned receipt includes exact source hashes, bindings, entity IDs, Person
statuses, acceptance scope, source-QA digest/counts, and remaining gates. Its own
`deterministic_sha256` hashes canonical JSON before that field is appended.
No receipt is written into `jurisdiction.json` or used as its QA sidecar.

## Production boundary

Both jurisdiction-package schemas now constrain an optional
`complete_jurisdiction` declaration in `jurisdiction` or `qa` to boolean `true`
for production-profile validation. The builder and production package loader
enforce the same restriction. An explicit `false` or malformed declaration is
rejected even if every QA counter is zero and every address-test result is true.

Existing packages that omit the field retain their existing contract and are
not reclassified by this change. The omission is not new evidence of statewide
completeness. This patch preserves the original v0.1/v0.2 gates and adds a guard
against silently accepting an explicitly partial package through those profiles.

Direct internal representation preview remains available. The default
representation consumer continues to reject provisional Persons. The bounded
receipt has a distinct schema version and is rejected if supplied to the
production package builder/loader as a jurisdiction package.

## Gate disposition

| Gate | Internal receipt disposition | Production consequence |
| --- | --- | --- |
| BOUNDED_COVERAGE_CONTRACT | RESOLVED_INTERNAL_ONLY | No partial production profile is introduced |
| GPS_BINDINGS | VERIFIED_CAPTURED_CANDIDATE | No runtime/catalog activation |
| LIVE_ADDRESS_CONTROLS | VERIFIED_CAPTURED_CANDIDATE | Captured evidence is not inserted into source QA |
| GEOMETRY_VERSION_GOVERNANCE | OPEN | Version/change handling remains required |
| PUBLIC_PERSON_IDENTITY | BLOCKED_PROVISIONAL for this source snapshot | Publication remains blocked |
| REPOSITORY_ACTIVATION | NOT_ACTIVATED | Review/merge/activation remain separate |

The source stage's five historical blocking gaps and zero production address
controls remain byte-unchanged. The receipt records newer gate dispositions
separately; it does not rewrite the historical stage or claim five current,
unresolved internal defects. Day 12 production closeout remains BLOCKED.

## Verification

Run `python tests/test_texas_bounded_contract.py`. Fixtures are synthetic and
cover pin mismatch, source/evidence drift, failed or incomplete controls, preview
scope drift, source immutability, deterministic receipts, unsupported record
scope, and rejection of partial production packages even after checksums are
regenerated. Legacy package and consumer regressions remain required. The
package and consumer CI workflows run these controls.
