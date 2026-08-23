# EV-IMP-001 — Empowered.Vote Essentials Consumer MVP

## Decision

Build the first Empowered.Vote implementation as a read-only consumer of the governed `EV-CDT-001-FX01` Tacoma payload.

## User question

> Who governs this address, what recent certified election contests are connected to those offices, and what official evidence supports each answer?

## Bounded fixture

Primary control: `747 Market Street, Tacoma, WA 98402`.

The consumer uses only frozen address controls already proven by Civic GPS. It does not perform free-form geocoding in this gate.

## Contract

The adapter must preserve canonical IDs and provenance, show only applicable Tacoma offices, retain currentness/term values exactly as supplied, expose recent certified contests/candidates, preserve explicit scope limits, make no CivicData.Tech writes, and fail closed for unsupported addresses.

## Acceptance summary

- IMP-01 frozen payload consumed directly;
- IMP-02 canonical IDs preserved in the model;
- IMP-03 frozen address maps to the governed jurisdiction set;
- IMP-04 only the applicable Tacoma district plus citywide offices are displayed;
- IMP-05 current holders are displayed from source fields without derived currentness;
- IMP-06 election → contest → candidacy joins are preserved;
- IMP-07 office/contest provenance is exposed;
- IMP-08 known scope limits are retained;
- IMP-09 no political recommendation/scoring exists;
- IMP-10 canonical writes are always zero;
- IMP-11 repeated input has a stable deterministic model hash;
- IMP-12 a standalone human-readable Tacoma Essentials HTML render is generated for review.

## Explicit exclusions

No accounts, Compass, Read & Rank preference capture, Gems, Badges, reputation, discussion, endorsement, recommendation, candidate scoring, or canonical data writeback.

## Executed full-payload proof

The implementation was executed locally against the complete remediated `EV-CDT-001-FX01` frozen payload rather than a hand-authored projection. For 747 Market Street it produced 6 detailed Tacoma applicable offices, 5 recent certified contests, and 15 candidate rows with zero canonical writes. The exact source and output hashes are frozen in `docs/ev-imp-001-acceptance.json`.
