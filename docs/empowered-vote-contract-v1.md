# Empowered Vote ↔ Representation Contract v1

Status: **shadow migration; production routing unchanged**

## Bottom line

Empowered Vote can now consume a certified Representation Contract v1 representation graph without reading the legacy `bodies/offices/role_terms` tables directly.

The migration is intentionally parallel:

```text
                         Civic GPS
                            |
                address -> geography only
                            |
             +--------------+--------------+
             |                             |
             v                             v
Jurisdiction Package path        Representation Contract v1
        (existing)                        (shadow)
             |                             |
             v                             v
   voter-facing model            voter-facing model
             |                             |
             +-------------+---------------+
                           |
                      parity check
```

No production selector is switched by this PR.

## Public-authority gate

Empowered Vote accepts Contract v1 for public representation only when:

```text
certification.status == certified
raw_complete          == true
normalized_complete   == true
qa_passed             == true
parity_ok              == true
```

An uncertified CivicPatch or partner snapshot is valid as a reconciliation input but fails closed at the Empowered Vote public boundary.

## Contract model consumed

Empowered Vote reads:

```text
Jurisdiction
   |
Organization
   |
Role -> Post
          |
      Membership <- Person
```

For each applicable post it exposes:

- contract `post_id`;
- legacy `office_id` when the Factory identifier crosswalk is present;
- role/name;
- represented `division_ocdid`;
- seat capacity;
- vacancy count;
- open memberships/current holders;
- membership leadership label;
- source URLs;
- evidence/assertions;
- certification.

## Identity behavior

The consumer does not name-match identities.

Factory Contract projections retain external identifiers such as:

```text
civicdata_factory_office
civicdata_factory_person
civicdata_factory_role_term
```

Those identifiers allow the Contract v1 shadow model to be compared with the current package model without replacing the contract's UUID identities.

Cross-system CivicPatch identity is handled by the reconciliation layer before certification.

## Geography behavior

Civic GPS remains geography-only.

For a citywide jurisdiction such as Akron:

```text
Civic GPS says: address is in jur-us-co-akron
Contract says:  ocd-jurisdiction/.../place:akron/government
Post graph says: these certified posts and holders serve the Akron division
```

For district representation, Contract v1 accepts an explicit Civic GPS adapter → division OCDID binding. When a district post is selected, a certified base-division post is also included when applicable, so citywide offices can coexist with district seats.

No civic facts are imported from Civic GPS.

## Akron shadow proof

The existing package catalog already routes Akron through:

- `civic_gps_jurisdiction_id = jur-us-co-akron`
- governed package `jurisdiction-co-akron`

The Contract v1 shadow path reconstructs that exact package, projects it to the shared contract, and compares the output with the existing Empowered Vote package consumer.

Parity checks cover:

- office identities;
- office names;
- seat capacity;
- current holder names;
- leadership roles;
- current-holder total.

Expected Akron result:

```text
legacy offices:          2
contract offices:        2
legacy current holders:  7
contract current holders:7
office differences:      0
parity_ok:                true
canonical_writes:        0
```

The Contract v1 projection additionally exposes explicit vacancy counts and source-year term-end values recovered by the Factory adapter.

## Tacoma district-bound shadow proof

Tacoma proves that the shared representation spine can combine citywide and district representation without importing civic facts from Civic GPS.

The existing governed catalog entry remains unchanged:

```text
entry:       wa-tacoma-municipal-essentials-v0.2
geography:   jur-us-wa-tacoma
adapter:     DIST-WA-TACOMA-COUNCIL
legacy IDs:  division:us/wa/tacoma/council_district_{district_key}
contract:    ocd-division/.../place:tacoma/council_district:{district_key}
```

The Factory adapter performs a narrow governed legacy-ID crosswalk. It accepts only recognized municipal and district ID shapes that agree with the jurisdiction identity; unknown shapes fail closed. Legacy office `parent_id` is honored as the body relationship.

Two governed controls are parity-tested:

| Address | Tacoma district | Applicable offices | Result |
|---|---:|---:|---|
| 747 Market Street | 2 | 6 | parity TRUE |
| 6500 South Sheridan Avenue | 5 | 6 | parity TRUE |

For each address, the Contract v1 shadow matches the existing Full Essentials representation portion on:

- office identity;
- display label;
- holder identity/name;
- leadership title;
- applicable office set.

Five citywide office IDs remain stable while the one district-scoped council office changes with the Civic GPS district assignment.

The test also verifies that missing or unknown Tacoma council districts fail closed.

Election, contest, and candidacy objects are **not** routed through Contract v1 yet. Tacoma's existing Full Essentials path remains authoritative for those objects.

## Post identity versus display label

A post's normalized identity remains:

```text
(organization_id, role_id, division_ocdid)
```

The optional `post.label` is display metadata, not identity. This preserves labels such as `Councilmember — Position 2` and `Position 8` without turning wording into a new role or a new identity rule.

## Files

```text
consumers/empowered_vote/
  contract_v1.py
  contract_v1_catalog.py

tests/
  test_empowered_vote_contract_v1.py
  test_empowered_vote_contract_v1_tacoma.py
```

## Fail-closed controls

The Contract consumer rejects:

- unsupported contract versions;
- missing/duplicate identity keys;
- broken organization/post/person membership foreign keys;
- memberships without source URLs;
- one person simultaneously holding multiple open posts in one body;
- posts over headcount;
- broken assertion → evidence links;
- jurisdiction binding mismatch;
- unresolved Civic GPS jurisdiction;
- district bindings without an OCD division;
- uncertified contracts;
- incomplete certification gates.

## Preserved legacy paths

This migration does not modify:

- `representation.py`;
- `representation_catalog.py`;
- `package_source.py`;
- `package_catalog.v0.1.json`;
- existing countywide Maui/Kauaʻi routes;
- Texas multi-binding production profile;
- Full Essentials election/contest/candidacy paths.

Those move only after separate Contract v1 schemas and parity gates exist for their additional domain objects.

## Next migration sequence

1. Keep Contract v1 shadowing Akron and Tacoma.
2. Add a current CivicPatch Postgres snapshot and reconcile/promote its crosswalks.
3. Add the election/contest/candidacy contract extension.
4. Migrate countywide special cases.
5. Migrate multi-binding state-legislative representation.
6. Switch production routing only after sustained parity.


## Full Essentials election shadow

The Contract v1 migration now includes an optional, separately certified
Election → Contest → Candidacy extension.

The existing Empowered Vote Full Essentials consumer remains the production
path. The new shadow path is:

```text
governed v0.2 package
        |
Factory → Contract v1
        |
        +-- representation certification
        |
        +-- election certification
                 |
Civic GPS geography + applicable Posts
                 |
       applicable Contests
                 |
          Candidacies
```

Files:

```text
consumers/empowered_vote/
  contract_v1_full_essentials.py
  contract_v1_full_essentials_catalog.py

tests/
  test_election_contract_v1.py
```

### Public gate

The Full Essentials shadow refuses to run unless both representation and
election certification pass. An Akron representation-only Contract remains
valid for representative lookup and correctly fails closed for Full Essentials.

### Identity rules

- Contest links to canonical `post_id`, not an office-name string.
- Named candidates link to canonical `person_id`.
- Aggregate write-in buckets never link to Person.
- Factory election, contest, and candidacy IDs are preserved as explicit
  external identifiers while Contract entities use deterministic UUIDs.
- Civic GPS supplies only the address-derived jurisdiction/district selection.

### Tacoma parity gate

For 747 Market Street, the Contract Full Essentials shadow must match the
existing governed path on:

- six applicable Tacoma offices;
- five applicable contests;
- fifteen candidate rows;
- contest → election and contest → office identity;
- candidacy source ID, Person identity, names, outcome, votes, vote share, and
  write-in semantics.

No production route is switched by this work and canonical writes remain zero.
