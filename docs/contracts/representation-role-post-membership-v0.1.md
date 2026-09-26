# Representation Role / Post / Membership Semantics v0.1

Status: **Draft contract implementation for issue #72**

This document freezes the minimum semantics needed for CivicData, CivicPatch, Civic Mirror, SeeGov, Empowered Vote, and other consumers to exchange representation records without confusing a formal office with an internally selected leadership title.

## Canonical chain

```text
Organization
    |
    v
Role
    |
    v
Post ----> Division
    |
    v
Membership <---- Person
```

### Role

A **Role** is the normalized formal elected or appointed function, such as:

- `mayor`
- `council-member`
- `select-board-member`
- `trustee`

Role IDs are stable slugs. Labels may be corrected without re-keying the role when the underlying function is unchanged.

### Post

A **Post** is a Role in an Organization for a representation Division.

The shared v0.1 identity tuple is:

```text
(organization_id, role_id, division_ocdid)
```

A multi-member at-large body may use one aggregate Post with `seats > 1` when authoritative sources do not establish persistent independently keyed seats.

A label such as `Seat 2`, `Place 8`, or `Position A` is **not geography by itself**. It MUST NOT mint a `division_ocdid` unless authoritative evidence establishes an actual representation division.

### Membership

A **Membership** is a Person holding a Post during an observed or source-stated service period.

Membership is where person-specific service facts belong, including:

- source-stated term dates;
- observation timestamps;
- non-geographic seat/designation text;
- internal leadership titles when the person remains in the same formal Post.

### Internal leadership title

A title such as `Chair`, `Vice Chair`, `Clerk`, `Secretary`, or `Mayor Pro Tem` selected from among existing members is an **internal leadership title**, not a new Post, unless authoritative law establishes it as a distinct office.

Current CivicData packages already demonstrate this separation: Akron keeps `Trustee` as the Office while `Mayor Pro Tem` is stored separately in `leadership_roles.csv`.

For cross-system adapters, existing `leadership_roles` records conceptually attach to Membership. This issue does not require a destructive migration of existing packages.

## Title observation rule

Every source title observation is handled as exactly one of:

| Classification | Meaning | Canonical effect |
|---|---|---|
| `FORMAL_ROLE` | Evidence supports the formal office label | May confirm the current Role label; a conflicting label requires reviewed override evidence |
| `INTERNAL_TITLE` | Leadership/function selected from among members | Preserve formal Role/Post; attach title to Membership |
| `RAW_ONLY` | Source wording is ambiguous, wrong, or not trusted for normalization | Preserve as evidence/provenance only; never overwrite canonical Role/Post |

A scraper string MUST NOT become a new canonical office merely because it appears in a municipal roster.

## Role taxonomy governance and alias policy

1. `role_id` is the durable semantic key.
2. Display-label corrections do not change `role_id` when the formal function is continuous.
3. Alternate source spellings are aliases, not new Role IDs.
4. Alias additions require reviewed evidence or an approved normalization rule.
5. A change that materially changes the legal/formal function requires a new Role ID rather than silent semantic reuse.
6. Canonical role or alias changes are governed by reviewed changes in the shared CivicData contract repository until a different registry owner is formally adopted.
7. Consumers MUST join on canonical IDs/crosswalks, never raw display titles.

## Geographic and non-geographic seats

### Geographic seat

Example: `Council Member — District 1`.

- Role: `council-member`
- Post division: the authoritative District 1 `division_ocdid`
- Membership designation: optional display metadata only

### Non-geographic designation

Example: `Council Member — Seat 2` where Seat 2 is only a ballot/position label.

- Role: `council-member`
- Post division: the base jurisdiction division
- Membership designation: `Seat 2`
- No new geographic division is minted

If authoritative evidence later proves the designation represents geography, the record is reviewed and promoted through the normal evidence/assertion process.

## Multi-seat and vacancy rule

Vacancy is a state of Post capacity, not a Person.

```text
vacancy_count = seats - active_memberships
```

Rules:

- `seats` MUST be a non-negative integer.
- `active_memberships` MUST be between zero and `seats`.
- Never create a Person named `Vacant`, `Vacancy`, or equivalent solely to fill an empty seat.
- An aggregate five-seat Select Board with four active Memberships has one vacancy.

## Millbury interoperability fixture

The live CivicMirror/CivicPatch discussion in CivicMirror issue #80 is the reference case.

For a five-seat Select Board:

| Source wording | Formal Post | Membership title | Canonical disposition |
|---|---|---|---|
| Chair | Select Board Member | Chair | internal title |
| Vice Chair | Select Board Member | Vice Chair | internal title |
| Clerk | Select Board Member | Clerk | internal title |
| Council Member | Select Board Member | none | raw/source wording only unless reviewed evidence proves a formal-office change |

The formal ballot/legal office remains the joinable office.

## Fail-closed behavior

Adapters MUST fail closed when:

- a source title is presented as a conflicting `FORMAL_ROLE` without reviewed override evidence;
- a geographic seat is asserted without an authoritative division identifier;
- active Membership count exceeds Post capacity;
- a non-geographic designation is used to mint geography;
- raw source wording is used as a join key.

## Acceptance fixtures

Machine-checkable examples live in:

```text
acceptance/representation/office_semantics_v0.1.json
```

The reference implementation is:

```text
tools/representation_semantics.py
```

Regression controls are:

```text
tests/test_representation_semantics.py
```

## Evidence / compatibility notes

- CivicMirror issue #80: https://github.com/CivicMirror/Civic-Data/issues/80
- CivicPatch maintainer response in that issue maps the formal office to Post/Role semantics and leftover internal title text to Membership-level labeling.
- Existing CivicData Akron package preserves `Trustee` separately from `Mayor Pro Tem` in `leadership_roles.csv`.

This contract freezes interoperability semantics only. It does not authorize writeback to CivicPatch, Civic Mirror, OpenStates, SeeGov, or Empowered Vote.
