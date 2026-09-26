## Summary

Refresh the Akron, Colorado elected-official roster from the current official Town sources.

### Current roster represented by this change

- Annette Bowin — Mayor
- Braden Brent — Trustee
- Crystann Benson — Trustee
- Jared Jefferson — Trustee
- Joe Tarnow — Trustee
- Ron Kraich — Trustee
- Terry Alexander — Trustee

### Identity handling

Existing CivicPatch person IDs are retained for:

- Braden Brent — `d31247df-3332-490e-b45d-fa8e7bb55e0b`
- Crystann Benson — `623089fb-bd23-4615-a440-1a61da966c15`
- Jared Jefferson — `dd07c3f5-1432-4c30-9bc9-9f73bb3385c2`

The four newly represented current officials use proposed UUIDs in this PR. Maintainers may remint those IDs if CivicPatch has a preferred identity-creation workflow.

### Jared Jefferson role correction

The current Town roster identifies Jared Jefferson as Trustee / Mayor Pro Tem. Akron Code §1-5-3 provides that the Board selects Mayor Pro Tem from among the trustees, so this file publishes his formal role as `trustee` rather than `mayor-pro-tempore`.

### Tenure handling

The Town publishes term-expiration years, but the source material used here does not establish exact service start/end dates. This change therefore leaves `start_date` and `end_date` null instead of converting an expiration year into an inferred term boundary.

### Rows no longer in the current roster

The replacement file no longer lists:

- Brandon Hill
- Ariella Gonzales-Vondy
- David Kembel
- Jennifer Hansen

This is a current-roster update only; it should not be interpreted as deleting historical Person identities elsewhere in CivicPatch.

## Sources

- Current Town Board roster: https://www.townofakron.com/172/Board-of-Trustees
- Akron Code §1-5-1, Board composition: https://codelibrary.amlegal.com/codes/akron_co/latest/akron_co/0-0-0-127
- Akron Code §1-5-3, Mayor Pro Tem: https://codelibrary.amlegal.com/codes/akron_co/latest/akron_co/0-0-0-134

## Validation

The candidate was generated from a certified CivicData Jurisdiction Factory package and validated against the CivicPatch `shared.schemas.OpenStatesPersonRecord` publish shape pinned to:

- `CivicPatch/open-data@69331c2b0d97e13695dab07ec1d6a969c99a3e4d`
- `CivicPatch/civicpatch-tools@072a8baf648542f66557fb30547ee3ba3a11ba6c`

The handoff also verifies a lossless round trip for the canonical representation semantics retained by the CivicPatch candidate + sidecar receipt.
