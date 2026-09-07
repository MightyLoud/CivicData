# Jurisdiction Package v0.1

Internal implementation of the D-327 package contract, with the D-329 Colorado factory exporter and a compatibility boundary between the legacy/public production contract and the strict deterministic export contract.

## Authority and layout

Canonical authority is `jurisdiction.json`. CSV files are deterministic review mirrors. Every strict package also contains `qa_report.json`, `manifest.json`, and `SHA256SUMS.txt`.

Repository convention:

- `data/source/<state>/` for governed, read-only factory snapshots
- `data/normalized/<state>/<jurisdiction_id>/jurisdiction.json`
- normalized-record CSV mirrors beside the canonical JSON
- `source_evidence.csv`, `source_assertions.csv`, `address_tests.csv`, `qa_checks.csv`, and `warnings.csv` beside strict normalized mirrors
- `data/reference/<state>/` for validation reports
- schemas: `schemas/jurisdiction_package_v0.1.schema.json` and `schemas/jurisdiction_package_v0.2.schema.json`
- generic/legacy builder and production-boundary helpers: `tools/jurisdiction_package.py`
- strict deterministic builder/validator: `tools/jurisdiction_package_strict.py`
- Colorado snapshot exporter: `tools/co_factory_export.py`
- generic tests: `tests/test_jurisdiction_package.py` and `tests/test_jurisdiction_package_v0_2.py`
- strict tests: `tests/test_jurisdiction_package_strict.py`, `tests/test_jurisdiction_package_adversarial.py`, `tests/test_co_factory_export.py`, and `tests/test_package_archives.py`

The split is intentional. Existing legacy and Texas production integrations continue to use the generic contract and its explicit identity/partial-scope gates. Governed deterministic factory exports use the strict contract for schema, relationship, inventory, checksum, and output-path enforcement.

## Colorado D-329 export

The governed snapshot is `data/source/co/d329-co-factory-snapshot.json`. It contains exact unformatted values and source row numbers for the five authorized jurisdictions only: Akron, Alamosa, Alma, Arvada, and Aspen. Aguilar, Antonito, and Arriba are explicitly excluded.

Run the deterministic export and strict controls from the repository root:

```bash
python tools/co_factory_export.py \
  data/source/co/d329-co-factory-snapshot.json \
  data/normalized/co
python tests/test_jurisdiction_package_strict.py
python tests/test_co_factory_export.py
python tests/test_jurisdiction_package_adversarial.py
python tests/test_package_archives.py
```

The strict exporter fails closed on snapshot-scope drift, missing or duplicate IDs, broken PK/FK or source/assertion relationships, QA/parity/tracker failures, blocking gaps, failed address controls, count drift, checksum mismatch, unsafe package inventory, path traversal, and symlinked output paths. A second export must be byte-identical.

## Generic production-scope boundary

The generic contract preserves legacy compatibility while enforcing explicit production boundaries. An explicitly partial `complete_jurisdiction` declaration in `jurisdiction` or `qa` is not accepted by the generic production scope gate; when present, that declaration must be boolean `true`. Legacy packages without the field retain their existing requirements.

The separately documented [Texas bounded acceptance contract](texas-bounded-acceptance-v0.1.md) supports an intentionally partial two-office representation release without changing the generic jurisdiction-package contract. Public Person identity disposition is likewise enforced at the production/public boundary rather than by converting internal-review packages into full-jurisdiction packages.

## Integration boundary

This contract and the D-329 artifacts do not themselves authorize merge to `main`, GitHub Release creation, publication, deployment, external distribution, adjacent-jurisdiction expansion, or mutation of source civic facts.
