# Colorado D-328 package targets

Authorized package targets: Akron, Alamosa, Alma, Arvada, Aspen.

Source of truth remains the governed `CO Jurisdiction Factory v0.1` workbook. Package generation must copy the complete jurisdiction-scoped rows from Jurisdiction, Division, Body, Office, Person, RoleTerm, LeadershipRole, IdentifierCrosswalk, SourceEvidence, SourceAssertion, AddressTest, QA, and nonblocking KnownGap surfaces. It must not reconstruct or infer facts from summaries.

The three blocked jurisdictions Aguilar, Antonito, and Arriba are excluded.

No package in this directory is publishable until the generated snapshot passes the generic validator, checksum verification, deterministic rerun comparison, and a separate merge/release gate.
