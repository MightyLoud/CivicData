# Akron representation pilot — Factory ↔ CivicPatch

Status: **migration/reconciliation proof; no write-back**

## Inputs

### Factory

- `data/normalized/co/jurisdiction-co-akron/jurisdiction.json`
- Factory snapshot date: 2026-08-19
- Jurisdiction OCDID: `ocd-jurisdiction/country:us/state:co/place:akron/government`
- Certified projection: 1 body, 2 aggregate posts, 7 people, 7 current memberships
- Trustee post headcount: 6
- Mayor Pro Tem is modeled as leadership on Jared Jefferson's Trustee membership.

### CivicPatch public rendered snapshot

- Source: `CivicPatch/open-data:data/co/local/place_akron.yml`
- Captured blob: `3c335cac8e5d07fb18b67db70aa12c7dc1d7a7d7`
- Record timestamps: 2025-07-09
- Same jurisdiction OCDID
- Historical rendered shape: Mayor (1), Trustee (5), Mayor Pro Tempore (1)
- This rendered artifact is used only to test migration/reconciliation. The production adapter targets CivicPatch's current Postgres organization/post/membership graph.

## Current-source check

Checked 2026-09-25 against the Town of Akron Board of Trustees page:

https://www.townofakron.com/172/Board-of-Trustees

The current official roster published there matches the seven-person Factory snapshot:

- Annette Bowin — Mayor
- Jared Jefferson — Trustee or Mayor Pro Tem
- Crystann Benson — Trustee
- Braden Brent — Trustee
- Terry Alexander — Trustee
- Joe Tarnow — Trustee
- Ron Kraich — Trustee

This establishes that the older CivicPatch rendered file should be treated as a historical/stale current-roster snapshot, not as evidence that the Factory should be overwritten.

## Reconciliation behavior

The pilot deliberately does not auto-link or overwrite.

Expected/verified classes include:

| Finding | Outcome |
|---|---|
| Same jurisdiction OCDID | `SAME` |
| Braden Brent name overlap | `IDENTITY_CONFLICT` + proposed person crosswalk |
| Crystann Benson name overlap | `IDENTITY_CONFLICT` + proposed person crosswalk |
| Jared Jefferson name overlap | `IDENTITY_CONFLICT` + proposed person crosswalk |
| Factory Trustee headcount 6 vs rendered CivicPatch Trustee headcount 5 | `FIELD_CONFLICT` |
| Rendered `mayor-pro-tempore` post vs Factory Trustee membership leadership title | `FIELD_CONFLICT: LEADERSHIP_TITLE_AS_POST` |
| Names only in the newer Factory snapshot | `FACTORY_ONLY` |
| Names only in the older rendered CivicPatch snapshot | `CIVICPATCH_ONLY` |
| Duplicate/ambiguous semantic keys | `BLOCKED` |

The three name matches remain proposed crosswalks. Exact-name agreement alone does not create canonical identity.

## Why the leadership conflict matters

A rotating or internally selected title can describe the holder of another seat rather than define a distinct seat. The current CivicPatch schema has evolved in this direction: post identity is based on organization + role + division, while holder-specific label material is kept on membership derivation rather than blindly minting a new post.

The contract therefore keeps:

```text
Trustee post
   ↓
Jared Jefferson membership
   └── label: Mayor Pro Tem
```

instead of assuming:

```text
Trustee post
Mayor Pro Tempore post
```

unless authoritative evidence establishes two distinct seats.

## Production path

```text
CivicPatch Postgres
   ↓ read-only repeatable-read snapshot
adapters/civicpatch/extract_snapshot.sql
   ↓
adapters/civicpatch/export_representation.py
   ↓
Representation Contract v1

Factory jurisdiction package
   ↓
adapters/factory/export_representation.py
   ↓
Representation Contract v1

both contracts
   ↓
tools/reconcile_representation.py
   ↓
SAME / ONLY / FIELD_CONFLICT / IDENTITY_CONFLICT / BLOCKED
   ↓
reviewed crosswalk/promotion decision
```

## Write boundary

`canonical_writes = 0`

No Factory, CivicPatch, OpenStates, Empowered Vote, SeeGov, or Civic Mirror record is modified by this pilot.
