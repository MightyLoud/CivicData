# Proposed canonical adoption — awaiting merge approval

This draft proposes the official October 16 roster observation as one canonical leadership record, evidence record and normalized assertion. Liz Hensley remains the same Ward 1 councilor, with the same membership and service dates. Exact leadership start/end dates remain null.

The package CSV sidecars, manifest byte counts and record counts, and SHA256SUMS are regenerated. Historical QA and its timestamps remain unchanged: they do not constitute fresh certification of this change. No runtime contract, private-site replay snapshot or activation setting is changed. Production publication and recertification require separate review.

The original candidate remains historical and proposed. baseline-package.json preserves its exact pre-adoption input, pinned by proposal.json. Its validator still rejects baseline tampering and verifies that execution never changes current canonical bytes. check_adoption.py independently checks the proposed canonical package, every checksum, CSV correspondence, manifest counts, preservation of all existing records and the single membership-label delta. The diagnostic export is validated as draft, not published.

Validation: 52 existing exporter/contract/role integration tests; four candidate tests including mutation and optimized-execution controls; read-only adoption acceptance; git diff --check. All passed locally. GitHub CI must be reviewed before merge.

Source: https://www.alamosa.gov/city-council-members ; minimal factual evidence and capture fingerprints are in evidence/roster-facts.json. Full response HTML is excluded.
