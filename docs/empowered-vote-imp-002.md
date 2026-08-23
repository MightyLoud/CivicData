# EV-IMP-002 — Live Governed Package Integration

## Decision

Use the mainline CivicData Jurisdiction Package as Empowered.Vote's read-only runtime boundary for bounded Essentials, rather than maintaining a second civic backend or relying only on the frozen EV-CDT-001 payload.

## Mainline upstream contract

CivicData `main` now contains the backward-compatible Jurisdiction Package v0.1/v0.2 contract. Version 0.1 remains representation-only. Version 0.2 additionally governs `elections`, `contests`, and `candidacies`, requires named candidates to resolve to canonical Person records, preserves aggregate write-ins as non-person buckets, and requires `election_scope_complete=true` plus `unexplained_loss=0`.

The canonical package authority is `jurisdiction.json`, accompanied by `qa_report.json`, `manifest.json`, deterministic CSV mirrors, and `SHA256SUMS.txt`.

## EV-IMP-002 implementation

`consumers/empowered_vote/package_source.py`:

1. accepts package schema 0.1 and 0.2;
2. verifies required sidecars and SHA-256 checksums;
3. verifies manifest file presence and byte counts;
4. verifies jurisdiction identity and QA/parity/blocking-gap gates;
5. verifies passing governed address controls and provenance presence;
6. exposes deterministic representation data with canonical writes fixed at zero;
7. keeps v0.1 Full Essentials fail-closed;
8. enables v0.2 Full Essentials only when election scope is complete and unexplained loss is zero;
9. preserves named-person candidate identities and non-person write-in buckets;
10. fails closed for addresses that are not present in the governed package controls.

## Mainline Tacoma proof

The repository contains the governed Tacoma v0.2 package at:

`data/packages/wa/tacoma/Tacoma_Jurisdiction_Package_v0.2_2026-08-23.zip`

The package contains 10 offices, 17 people, 2 elections, 9 contests, and 26 candidacies. Its accepted address controls reproduce the bounded EV-CDT-001 result:

- `747 Market Street, Tacoma, WA 98402` → Tacoma District 2; 6 Tacoma offices; 5 certified contests; 15 candidate rows;
- `6500 South Sheridan Avenue, Tacoma, WA 98408` → Tacoma District 5; 6 Tacoma offices;
- `6000 Main St SW, Lakewood, WA 98499` → Tacoma absent; 0 Tacoma offices and 0 Tacoma contests;
- unsupported arbitrary addresses → fail closed.

The accepted stacked proof remains at:

`data/reference/wa/tacoma/EV-IMP-002_Tacoma_Stacked_Proof_2026-08-23.json`

## Acceptance

- IMP2-01 package source is the runtime boundary, not a hand-authored civic backend;
- IMP2-02 checksum tampering fails closed;
- IMP2-03 manifest byte drift fails closed;
- IMP2-04 parity, QA, blocking gaps, election-scope incompleteness, and unexplained loss fail closed;
- IMP2-05 package reads do not mutate source data;
- IMP2-06 canonical jurisdiction, office, person, RoleTerm, contest, and candidacy identities are preserved;
- IMP2-07 provenance and warnings remain visible;
- IMP2-08 output is deterministic;
- IMP2-09 canonical writes remain zero;
- IMP2-10 v0.1 remains representation-only;
- IMP2-11 v0.2 Full Essentials is supported;
- IMP2-12 the checked-in Tacoma v0.2 package is exercised in CI and must reproduce the accepted bounded counts and negative control.

## Explicit exclusions

No CivicData canonical writeback, no package mutation, no inferred civic facts, no recommendation/scoring layer, no accounts or reputation system, and no publication or external distribution authorization.
