# Jurisdiction Package v0.1

Internal implementation of the D-327 package contract.

## Authority and layout

Canonical authority is `jurisdiction.json`. CSV files are deterministic review mirrors. Every package also contains `qa_report.json`, `manifest.json`, and `SHA256SUMS.txt`.

Repository convention:

- `data/normalized/<state>/<jurisdiction_id>/jurisdiction.json`
- CSV mirrors beside the canonical JSON
- `data/reference/<state>/<jurisdiction_id>/` for package manifest/checksum/QA sidecars when integrated
- schema: `schemas/jurisdiction_package_v0.1.schema.json`
- builder/validator: `tools/jurisdiction_package.py`
- tests: `tests/test_jurisdiction_package.py`

## Fail-closed validation

A package is invalid when schema version is unsupported, parity is not true, QA failures or blocking gaps are nonzero, fewer than two passing address controls exist, provenance is absent, IDs collide, required RoleTerm relationships are absent, counts drift, or checksums fail.

Warnings remain visible. Unsupported facts remain null/blank; the builder must not infer them.

## Integration boundary

This contract does not itself authorize merge to `main`, GitHub Release creation, publication, external distribution, or mutation of source civic facts.
