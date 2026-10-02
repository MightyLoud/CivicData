# Generic Representation Export + Conformance Engine v0.1

This tool turns governed Jurisdiction Packages into a repeatable multi-consumer
conformance run.

## Commands

One package:

```bash
python tools/export_representation.py \
  --package data/normalized/co/jurisdiction-co-akron/jurisdiction.json \
  --consumer all
```

All shared-certified normalized packages:

```bash
python tools/export_representation.py \
  --all-certified \
  --consumer all \
  --output out/conformance.json \
  --markdown out/conformance.md \
  --artifact-dir out/artifacts
```

## Pipeline

```text
Jurisdiction Package
      ↓
package validation
      ↓
Canonical Representation Core
      ↓
Core validation / shared certification
      ↓
Representation Contract v1
      ↓
Contract semantic validation + Core parity
      ↓
consumer conformance
```

The engine orchestrates existing adapters. It does not define another canonical
schema.

## Statuses

- `PASS` — the tested direction is implemented and preserves the governed
  representation semantics checked by this harness.
- `LOSSY` — the adapter runs, but governed semantics are lost.
- `BLOCKED` — the adapter cannot safely run.
- `NOT_TESTED` — that direction/capability is not implemented in the harness.

## Current consumer coverage

### CivicPatch

Mode: `FORWARD_EXPORT_ROUND_TRIP`.

The engine:

1. exports Canonical Core to the CivicPatch-compatible candidate bundle;
2. validates the published Official shape;
3. round-trips the bundle + sidecar receipt;
4. compares the result with the Canonical Core semantic projection.

Preview person IDs are reported as identity gaps. They do not cause semantic
loss because they remain explicit partner-review work rather than guessed
identity.

### Empowered Vote

Mode: `GOVERNED_GEOGRAPHY_RUNTIME`.

The engine consumes every passing governed Factory `qa.address_tests` control.

For district controls with committed coordinates, runtime geography is derived
from the governed Polygon/MultiPolygon snapshot:

```text
coordinate
  → governed geometry registry
  → point-in-polygon
  → canonical OCD division
```

The Factory `expected_division_id` is then checked as an assertion against the
runtime result; it is not used as the district-routing input.

Citywide controls without coordinate-backed local geometry continue through the
reviewed fixture boundary. The report exposes `controls_pip` and
`controls_fixture` separately.

PASS requires:

- resolved OCD division matches the Factory control;
- applicable office IDs exactly match the Factory control;
- current-holder counts reconcile;
- no canonical writes occur.

This is deterministic runtime conformance, **not a live network geocode**.
Live address geocoding remains explicitly separate as
`live_address_geocoding_network`; coordinate → district resolution is now
exercised through governed PIP.

When a jurisdiction contains ward/district divisions but no governed address
control resolves those districts, the report records
`NO_GOVERNED_ADDRESS_CONTROL` geography gaps rather than inferring coverage.
Full Essentials elections also remain separately scoped when no certified
election extension is present.

### Civic Mirror

Current direction in the repository is a partner-inbound adapter that proposes
reviewable assertions. Factory → Civic Mirror forward export is therefore
reported `NOT_TESTED`, not implied.

### SeeGov

Current direction in the repository is a partner-inbound meeting/speaker adapter.
Factory → SeeGov forward export is therefore reported `NOT_TESTED`.

## Core ↔ Contract semantic parity

The engine compares stable representation fields across Canonical Core and
Representation Contract v1 using the Factory native identifiers carried in the
Contract:

- Person
- Membership
- Post
- Organization
- formal Role
- jurisdiction
- representation Division
- internal membership label

Dates already represented canonically must match.

When Contract v1 carries a partial date (for example a source-stated expiration
year) while Canonical Core retains that precision in assertions rather than
`membership.end_date`, the engine records a
`CONTRACT_PARTIAL_DATE_ENRICHMENT` note. It is visible and auditable rather
than silently claimed as exact Core parity.

## Discovery

Repository discovery is intentionally simple and deterministic:

```text
data/normalized/**/jurisdiction.json
```

`--all-certified` evaluates discovered packages and selects only those whose
Canonical Core shared certification is `certified`.

## Artifact output

With `--artifact-dir`, each selected jurisdiction gets:

```text
<jurisdiction_id>/
  canonical_core.json
  representation_contract_v1.json
  civicpatch_bundle.json
  empowered_vote_runtime.json
  conformance.json
```

Consumer artifacts are written only when that payload was actually generated.

## No external writes

The engine is read-only with respect to partner systems. It does not submit
CivicPatch patches, mutate Empowered Vote, or write to SeeGov/Civic Mirror.
