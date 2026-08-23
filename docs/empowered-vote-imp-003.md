# EV-IMP-003 — Live Civic GPS Address Resolution

## Decision

Move Empowered.Vote address resolution from the bounded address-control lookup in Jurisdiction Package v0.2 to the live Civic GPS runtime, while keeping the governed jurisdiction package authoritative for civic facts.

## Authority boundary

Civic GPS may establish only:

- whether the input address activates the Tacoma jurisdiction;
- the live Tacoma council-district assignment;
- other resolved jurisdiction IDs needed for geographic context;
- the matched address returned by the resolver.

The Jurisdiction Package remains authoritative for:

- divisions and jurisdiction identity;
- bodies and offices;
- people and current officeholders;
- currentness and terms;
- elections, contests, and candidacies;
- candidate/person identity and write-in treatment;
- provenance, warnings, and package QA.

Civic GPS `applicable_offices`, `action_links`, or any other civic-fact-bearing output are deliberately ignored by the EV bridge.

## Flow

`address → live Civic GPS → jurisdiction + district only → governed package join → Empowered.Vote Essentials`

`consumers/empowered_vote/live_civic_gps.py` normalizes the live geography response and converts it into an isolated geographic control for the existing read-only package projection. The source package is deep-copied before that temporary control is inserted; canonical package data is never mutated.

## Fail-closed conditions

EV-IMP-003 fails closed when:

- Civic GPS returns an error;
- the response or required geography fields are malformed;
- Tacoma is active but the Tacoma district assignment is missing;
- Civic GPS returns a Tacoma district that does not exist in the governed package;
- the package is not the explicitly supported Tacoma package binding;
- the Civic GPS runtime raises a network/runtime exception.

## Acceptance

- IMP3-01 live Civic GPS replaces package address-test lookup as the geographic authority;
- IMP3-02 Civic GPS civic-fact fields cannot override package facts;
- IMP3-03 747 Market Street resolves Tacoma District 2 and returns exactly 6 package offices, 5 certified contests, and 15 candidate rows;
- IMP3-04 6500 South Sheridan Avenue resolves Tacoma District 5 and returns exactly 6 package offices, 5 contests, and 15 candidate rows;
- IMP3-05 Lakewood resolves outside Tacoma and returns zero Tacoma offices/contests/candidates;
- IMP3-06 missing or unknown Tacoma district assignments fail closed;
- IMP3-07 upstream Civic GPS errors fail closed with no package fallback inference;
- IMP3-08 deterministic projection is stable for the same normalized geography response;
- IMP3-09 canonical writes remain zero;
- IMP3-10 GitHub CI executes both deterministic bridge tests and real-network Civic GPS → package controls.

## Explicit exclusions

No second geocoder, no address inference from mailing addresses, no Civic GPS authority over officeholders/elections/candidates, no canonical writeback, no package mutation, no political scoring, and no publication authorization.
