# Colorado D-329 deterministic packages

Generated package targets: Akron, Alamosa, Alma, Arvada, and Aspen.

The source of truth remains the governed `CO Jurisdiction Factory v0.1` workbook. D-329 copied the complete jurisdiction-scoped source rows into a governed snapshot and generated the five packages mechanically. Open nonblocking KnownGap rows are preserved in each package's `warnings`; unsupported values remain null/blank.

The three blocked jurisdictions Aguilar, Antonito, and Arriba are excluded.

Each package passes the generic validator, exact count reconciliation, PK/FK and source/assertion integrity checks, QA/parity/tracker checks, address controls, manifest byte checks, SHA-256 verification, and a byte-identical deterministic rerun. The packages remain branch-only and are not published or merged without a separate gate.
