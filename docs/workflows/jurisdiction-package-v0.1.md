# Jurisdiction Package v0.1

Internal implementation of the D-327 package contract, with the D-329 Colorado factory exporter.

## Authority and layout

Canonical authority is `jurisdiction.json`. CSV files are deterministic review mirrors. Every package also contains `qa_report.json`, `manifest.json`, and `SHA256SUMS.txt`.

Repository convention:

- `data/source/<state>/` for governed, read-only factory snapshots
- `data/normalized/<state>/<jurisdiction_id>/jurisdiction.json`
- normalized-record CSV mirrors beside the canonical JSON
- `source_evidence.csv`, `source_assertions.csv`, `address_tests.csv`, `qa_checks.csv`, and `warnings.csv` beside the normalized mirrors
- `data/reference/<state>/` for validation reports
- schema: `schemas/jurisdiction_package_v0.1.schema.json`
- builder/validator: `tools/jurisdiction_package.py`
- Colorado snapshot exporter: `tools/co_factory_export.py`
- tests: `tests/test_jurisdiction_package.py` and `tests/test_co_factory_export.py`

## Colorado D-329 export

The governed snapshot is `data/source/co/d329-co-factory-snapshot.json`. It contains exact unformatted values and source row numbers for the five authorized jurisdictions only: Akron, Alamosa, Alma, Arvada, and Aspen. Aguilar, Antonito, and Arriba are explicitly excluded.

Run the deterministic export and tests from the repository root:

```bash
python tools/co_factory_export.py \
  data/source/co/d329-co-factory-snapshot.json \
  data/normalized/co
python tests/test_jurisdiction_package.py
python tests/test_co_factory_export.py
```

The exporter fails closed on snapshot-scope drift, missing or duplicate IDs, broken PK/FK or source/assertion relationships, QA/parity/tracker failures, blocking gaps, failed address controls, count drift, or checksum mismatch. A second export must be byte-identical.

## Fail-closed validation

A package is invalid when schema version is unsupported, parity is not true, QA failures or blocking gaps are nonzero, fewer than two passing address controls exist, provenance is absent, IDs collide, required relationships are missing, source/assertion references break, counts drift, or checksums fail.

Open nonblocking KnownGap rows remain visible in `warnings`. Unsupported facts remain null/blank; the exporter does not infer them.

## Integration boundary

This contract does not itself authorize merge to `main`, pull-request creation, GitHub Release creation, publication, external distribution, or mutation of source civic facts.
