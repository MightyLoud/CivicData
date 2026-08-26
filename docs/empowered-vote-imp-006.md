# EV-IMP-006 — Repeatable Jurisdiction Onboarding

## Purpose

Turn the Akron second-jurisdiction proof into a declarative, repeatable consumer-onboarding pipeline.

The pipeline starts from an already governed CivicData Jurisdiction Package. It does **not** research, infer, normalize, or create civic facts. It produces only the metadata needed for Empowered.Vote to route a Civic GPS result to that package.

## Authority boundary

- Civic GPS owns address → geography resolution.
- The Jurisdiction Package owns offices, people, terms, leadership, elections/candidates when supported, provenance, warnings, and QA.
- The onboarding spec owns only routing/configuration metadata.
- `applicable_office_rules` and `action_registry_files` are always emitted empty by the onboarding pipeline.
- Canonical civic-data writes are always zero.

## Inputs

One JSON spec under `onboarding/ev/` declares:

- package artifact location and SHA-256;
- package jurisdiction ID and schema version;
- consumer profile (`municipal_representation` or `municipal_essentials`);
- Civic GPS jurisdiction ID;
- Census routing GEOID and routing-only adapter metadata;
- expected package counts/gates.

`onboarding/ev/TEMPLATE.v0.1.json` is the starting template.

## Gates

The tool `tools/ev_jurisdiction_onboarding.py` reconstructs the governed package and fails closed when:

1. package bytes/checksums fail the existing package boundary;
2. package jurisdiction ID or schema differs from the spec;
3. routing GEOID differs from the governed package GEOID;
4. the requested profile exceeds package capability (for example v0.1 → Full Essentials);
5. expected office/current-holder/address-control/QA counts drift;
6. routing metadata tries to acquire office/action authority;
7. `--verify-current` output differs from the already governed catalog or Civic GPS routing bundle.

Successful output consists of exactly three generated artifacts:

- `package_catalog_entry.json`
- `civic_gps_routing_bundle.json`
- `acceptance.json`

These outputs are review/staging artifacts. The tool does not directly alter canonical civic data or silently register a jurisdiction.

## Akron regression proof

`onboarding/ev/akron.v0.1.json` replays the already merged Akron implementation. A successful replay must reproduce the exact governed package-catalog entry and exact routing-only Civic GPS bundle while observing:

- package v0.1;
- 2 office rows representing 7 elected seats;
- 7 current holders;
- 2 passing address controls;
- parity TRUE;
- 0 QA failures;
- 0 blocking gaps;
- 0 Civic GPS civic-fact rows;
- 0 canonical writes.

Akron remains `municipal_representation`. The pipeline must reject any attempt to label the same v0.1 package as `municipal_essentials` because Election/Contest/Candidacy capability is not governed in that package.

## Production sequence for the next jurisdiction

1. Complete the jurisdiction factory through governed package eligibility.
2. Build and validate its deterministic Jurisdiction Package with `tools/jurisdiction_package.py`.
3. Store the immutable package artifact and checksum.
4. Copy `onboarding/ev/TEMPLATE.v0.1.json` and fill only evidence-backed IDs, GEOID, artifact metadata, profile, and expected counts.
5. Run `tools/ev_jurisdiction_onboarding.py ...` to generate routing/catalog artifacts.
6. Review the diff, register the generated metadata, and run EV/Civic GPS CI.
7. Add live address controls only when the exact Civic GPS engine can resolve the jurisdiction.
8. Keep Full Essentials fail-closed unless the governed package actually has v0.2 election capability.

Publication, external promotion, and consumer writeback remain separate gates.
