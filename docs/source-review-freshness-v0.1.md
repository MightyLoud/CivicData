# Bound source-review freshness v0.1

The report exposes upcoming expiry before a source-review gate blocks unrelated
work. It discovers countywide profiles in the default Empowered Vote catalog,
verifies each acceptance receipt's exact byte hash, and verifies separately bound
source-review hashes where present. Embedded reviews remain bound by the
acceptance hash.

The existing countywide runtime validators enforce the receipt and source
contracts. The reporter calls them at the bound review's start date to distinguish
expired valid evidence from invalid evidence, then classifies freshness against
the report's current UTC date. That validation date never makes an expired or
future review current. Runtime code and its expiry rules are unchanged.

| Status | Condition after contract verification | CLI result |
|---|---|---|
| CURRENT | More than 14 days remain | 0 |
| EXPIRING_14_DAYS | 8 through 14 days remain | 0, warning |
| EXPIRING_7_DAYS | 1 through 7 days remain | 0, warning |
| EXPIRED | Expiry date reached or passed | 1, error |
| NOT_YET_VALID | Review start is in the future | 1, error |
| INVALID | Hash, contract, policy, path or input is invalid | 1, error |

Expiry is exclusive at 00:00 UTC. The JSON report and GitHub step summary show
reviewed dates, expiry dates, days remaining, verified references and errors.
Warnings are visible on every run in the threshold range. Missing or invalid
catalogs and empty review inventories fail, rather than producing an empty pass.
One invalid receipt does not prevent the other receipt from being checked.

```
python tools/source_review_freshness.py --repo-root .
python tools/source_review_freshness.py --format markdown
python tools/source_review_freshness.py --as-of 2026-10-28 --format markdown
```

`--as-of` is an explicit simulation using a canonical UTC date. CI never supplies
it. `--github-actions` appends the Markdown summary to `GITHUB_STEP_SUMMARY` and
emits escaped warning/error annotations on stderr, leaving JSON stdout parseable.

The dedicated workflow runs daily at 15:17 UTC, on relevant PRs and pushes to
main, and manually. It uses read-only repository permissions, no network probes
or external credentials, and retains the JSON report for 30 days. GitHub's
scheduled execution may be delayed; the next run recomputes the current state.

Scope is catalog-bound countywide reviews, currently Maui and Kauaʻi. Other
catalog entries are explicitly listed as not covered. PASS certifies review
bindings and freshness within that scope; it does not certify complete source
coverage, civic facts, package reconstruction, geocoding, release or deployment.
The report does not renew evidence, edit receipts or grant publication authority.
