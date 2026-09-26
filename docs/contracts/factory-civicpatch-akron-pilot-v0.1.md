# Factory → Canonical Core → CivicPatch Akron Pilot v0.1

Status: candidate interoperability proof for issue #82.

## Source

The pilot uses the committed certified Akron Jurisdiction Package:

```text
data/normalized/co/jurisdiction-co-akron/jurisdiction.json
```

No civic facts in the candidate are hand-authored substitutes.

## Target contract

Pinned partner contract:

- `CivicPatch/open-data@69331c2b0d97e13695dab07ec1d6a969c99a3e4d`
- `CivicPatch/civicpatch-tools@072a8baf648542f66557fb30547ee3ba3a11ba6c`
- publish shape: `shared.schemas.OpenStatesPersonRecord`

## Pipeline

```text
Akron Jurisdiction Package
        ↓
Canonical Representation Core v0.1
        ↓
CivicPatch adapter v0.1
        ├── CivicPatch-compatible YAML candidate
        ├── hashed candidate bundle + sidecar receipt
        └── drift report vs pinned CivicPatch Akron
        ↓
round-trip semantic projection
        ↓
compare with source Canonical Core
```

## Candidate identity rule

The Factory currently does not carry accepted CivicPatch IDs for Akron's current
people.

The candidate therefore uses deterministic preview-only UUIDv5 IDs derived from
the canonical Person ID under an adapter namespace.

These IDs:

- are stable for repeated previews;
- are not name-derived;
- are not shared canonical Person IDs;
- are **not accepted CivicPatch identities**;
- must not be promoted upstream until CivicPatch identity review establishes the
  actual product crosswalk.

## Leadership rule

Akron's Factory package identifies Jared Jefferson as a Trustee and separately
as Mayor Pro Tem.

The CivicPatch published-file model has no membership-level internal leadership
field.

Therefore the candidate YAML exports:

```text
formal role: Trustee
```

and the sidecar receipt preserves:

```text
internal_label: Mayor Pro Tem
```

It deliberately does **not** publish `Mayor Pro Tem` as a formal CivicPatch
role. This is the #72 contract in motion.

## Tenure rule

The Factory knows term-expiration years for several Akron officials but does not
have authoritative exact term-end dates.

The canonical memberships therefore keep the dates unknown and the CivicPatch
candidate emits:

```text
start_date: null
end_date: null
```

The adapter never converts an expiration-year assertion into a fabricated
service-end date.

## Sidecar receipt

CivicPatch's published person file cannot carry all canonical information.

The bundle receipt preserves the fields that would otherwise be lost:

- core Person ID;
- Membership ID;
- Post ID;
- Organization ID;
- internal leadership label;
- source certification;
- candidate-ID status.

The bundle—not the YAML alone—is the round-trip unit.

## Drift diagnostic

The pinned CivicPatch Akron file is older than the certified Factory snapshot.

The drift report compares exact display names only. It explicitly does **not**
perform identity resolution or authorize deletes/additions.

Any exact-name overlap is marked as a potential identity match requiring review.

## Outputs

The pinned partner comparison input is committed at:

```text
acceptance/civicpatch/akron_current_pinned_69331c2.json
```

The deterministic builder produces these acceptance artifacts into the requested
output directory:

```text
akron_factory_candidate_bundle_v0.1.json
akron_factory_candidate_bundle_v0.1.manifest.json
akron_factory_candidate_v0.1.yml
akron_factory_candidate_drift_v0.1.json
```

CI builds those files twice and requires byte-for-byte equality, then validates
the bundle, manifest, drift contract, YAML publish shape, and semantic round trip.

Generator:

```text
consumers/civicpatch/build_akron_pilot.py
```

Adapter:

```text
consumers/civicpatch/adapter.py
```

Regression tests:

```text
tests/test_civicpatch_akron_integration.py
```

## Boundary

This pilot does not modify `CivicPatch/open-data`, mint accepted CivicPatch
identity crosswalks, or authorize an upstream merge.
