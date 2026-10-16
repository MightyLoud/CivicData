# Alamosa leadership correction candidate

The official City Council Members page retrieved October 16, 2026 lists Liz Hensley as Mayor Pro Tem and Ward 1 Councilor. The canonical package has no leadership records, so its exported membership omits Mayor Pro Tem.

This proposal appends one leadership record, one official source-evidence record and one **proposed** assertion. It preserves existing identifiers, people, offices, memberships and service dates. Exact leadership dates remain unknown. The evidence entry records the URL, retrieval time and SHA-256 of the original HTML response; it does not imply continuous verification. A minimal factual extract is retained under evidence/roster-facts.json with its own SHA-256. The original response fingerprint is recorded separately; the validator checks extract integrity and observation links, not the absent original response bytes. Full HTML is excluded because it contains unrelated session/security material.

Source: https://www.alamosa.gov/city-council-members

## Validation

From repository root:

```sh
python3 candidates/co/alamosa-leadership-20261016/validate.py
```

The read-only validator checks the exact archived baseline hash in baseline-package.json, identity and evidence joins, exporter output, the one membership-label difference, identifier/date preservation and draft contract structure. It also verifies that the production consumer rejects the draft as uncertified. It creates no canonical files or exported runtime artifacts.

The targeted Alamosa leadership candidate workflow runs this validator and four tests covering a valid read-only execution, eleven proposal/evidence mutations and rejection of optimized Python execution. The workflow has read-only repository permissions.

## Review and adoption boundary

This directory is a candidate, not an adopted correction. Its assertion remains proposed. The validated export is explicitly draft; inherited historical QA/certification fields do not recertify this change. Before adoption, review the source evidence, regenerate package sidecars/checksums and run the governed source acceptance process. Do not simply copy this candidate into the canonical package or change contract certification to bypass review. The private review site's historical replay contracts remain separate and unchanged.

The archived baseline preserves the original candidate replay after canonical changes. The validator separately checks that it never mutates the current canonical file. It does not assert that the current canonical file still matches the historical baseline.
