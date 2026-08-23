# Jurisdiction Package v0.2 — Election Extension

`CDT-PKG-002` extends the existing Jurisdiction Package v0.1 contract without changing v0.1 semantics.

## Purpose

Jurisdiction Package v0.2 adds the minimum governed election layer required by downstream consumers such as Empowered.Vote while keeping CivicData.Tech authoritative for civic identity, provenance, QA, parity, and unknowns.

The package remains read-only from a consumer's perspective. This contract does not authorize publication, consumer writeback, inferred identities, or creation of civic facts that are absent from source evidence.

## Added record collections

Version 0.2 requires three additional canonical collections under `records`:

- `elections`
- `contests`
- `candidacies`

### Election

Minimum governed fields:

- `election_id`
- `election_date`
- `source_ids[]`

Every referenced source must exist in `provenance.source_evidence`.

### Contest

Minimum governed fields:

- `contest_id`
- `election_id`
- `office_id`
- `contest_name`
- `source_ids[]`

The election and office foreign keys must resolve inside the same package.

### Candidacy

Minimum governed fields:

- `candidacy_id`
- `contest_id`
- `candidate_kind`
- `source_candidate_id`
- `candidate_name`
- `source_id`
- `outcome`

`candidate_kind` is either `PERSON` or `WRITE_IN_BUCKET`.

For `PERSON`, `person_id` is mandatory and must resolve to `records.people`. A named candidate must not be silently converted into an unlinked candidate identity.

For `WRITE_IN_BUCKET`, `person_id` must be null. Aggregate write-in ballot rows are not promoted to people.

## Added QA gates

Version 0.2 requires:

- `election_scope_complete = true`
- `unexplained_loss = 0`

These are in addition to the v0.1 requirements:

- `parity_ok = true`
- `qa_fail_count = 0`
- `blocking_gap_count = 0`
- at least two passing address controls
- provenance present
- deterministic manifest/checksum output

## Backward compatibility

The builder/validator continues to accept v0.1 packages unchanged. Version 0.1 packages do not gain implied election completeness and must not be treated as Full Essentials packages by downstream consumers.

Version 0.2 is an explicit opt-in contract: the package must actually contain the three election collections and satisfy the added identity, provenance, foreign-key, parity, and zero-loss rules.

## Fail-closed rules

A v0.2 package fails validation when any of the following occurs:

- duplicate Election, Contest, or Candidacy IDs;
- Contest references a missing Election or Office;
- Candidacy references a missing Contest;
- a named `PERSON` candidacy lacks a canonical Person relationship;
- a `WRITE_IN_BUCKET` is assigned a Person identity;
- election/contest/candidacy provenance references an unknown source;
- election scope is not explicitly complete;
- unexplained loss is nonzero;
- any inherited v0.1 package gate fails.

## Output

The deterministic builder adds review mirrors:

- `elections.csv`
- `contests.csv`
- `candidacies.csv`

The canonical authority remains `jurisdiction.json`. The manifest and `SHA256SUMS.txt` cover the added files in exactly the same way as the existing package files.

## Tacoma status

This contract extension does not itself assert that a Tacoma v0.2 package exists. Tacoma package materialization is a separate execution step and must use the governed Tacoma source/election data rather than a hand-authored substitute.
