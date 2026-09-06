# Texas Person identity resolution v0.1

Status: `SOURCE_IDENTITY_RESOLVED_NOT_REPACKAGED`

Reviewed and executed: September 6, 2026.

This record resolves the two Person identities used by the bounded Day 12 Texas legislative integration. It does not change the current RoleTerms, create a complete Texas representation package, activate the production catalog or Civic GPS registry, or authorize merge/publication by itself.

## Resolved Persons

| Chamber | District | Person | Canonical Person ID | Current identity status |
| --- | --- | --- | --- | --- |
| House | 49 | Gina Hinojosa | `per-wb020-d061f1971ec9ac58afe308519c117465deb046363ffb026680fa2e483ee840b7` | `AUTHORITATIVE` |
| Senate | 14 | Sarah Eckhardt | `per-wb020-d387c4b877eeedc0a1a6efc49f6e3897209d245e27d8eae3164870552a762dca` | `AUTHORITATIVE` |

The existing canonical Person IDs are preserved. No duplicate Person is created and no name-derived ID is minted.

## Resolution rule

For this bounded D419 scope, `AUTHORITATIVE` requires all of the following:

1. the retained canonical Person is already linked to a current-holder SourceRecord from an official Texas legislative roster;
2. an independently retrieved official chamber member page identifies the same full name and district;
3. an independently retrieved Texas Legislative Reference Library member record identifies the same full name, chamber/district, and current service period;
4. the independent evidence does not conflict on Person identity;
5. the original provisional SourceRecord remains preserved as lineage.

A current RoleTerm by itself is not sufficient. Name equality by itself is not sufficient. Removing `PROVISIONAL` without an explicit authoritative disposition is not sufficient.

## Gina Hinojosa

Canonical Person:
`per-wb020-d061f1971ec9ac58afe308519c117465deb046363ffb026680fa2e483ee840b7`

Preserved provisional SourceRecord lineage:
`sr-wb020-d061f1971ec9ac58afe308519c117465deb046363ffb026680fa2e483ee840b7`

Retained occupancy evidence:
`ev-wb020-15db64fbbf29d7096500c69eda86b9f1ba5cf0f2d6ac135ce6644fc7344ae785`

Independent identity corroboration:

- Texas House member page: `https://house.texas.gov/members/49` — Gina Hinojosa, District 49.
- Texas Legislative Reference Library: `https://lrl.texas.gov/legeleaders/members/memberdisplay.cfm?memberID=5799` — Gina Hinojosa, House District 49, current service beginning January 14, 2025.

Disposition: `AUTHORITATIVE`.

## Sarah Eckhardt

Canonical Person:
`per-wb020-d387c4b877eeedc0a1a6efc49f6e3897209d245e27d8eae3164870552a762dca`

Preserved provisional SourceRecord lineage:
`sr-wb020-d387c4b877eeedc0a1a6efc49f6e3897209d245e27d8eae3164870552a762dca`

Retained occupancy evidence:
`ev-wb020-16a8ece0bdfc2b807913f493153153a564e2ae0dacaf10cabcff71a42c892695`

Independent identity corroboration:

- Texas Senate member page: `https://senate.texas.gov/member.php?d=14` — Sarah Eckhardt, District 14.
- Texas Legislative Reference Library: `https://lrl.texas.gov/legeleaders/members/memberdisplay.cfm?memberID=5858` — Sarah Eckhardt, Senate District 14, current service beginning January 14, 2025.

Disposition: `AUTHORITATIVE`.

## Canonical workbook execution

In `TX_ELECTIONS_Data_C6`:

- `TX_PERSON!I3465` changed from `PROVISIONAL` to `AUTHORITATIVE` for Gina Hinojosa;
- `TX_PERSON!I3580` changed from `PROVISIONAL` to `AUTHORITATIVE` for Sarah Eckhardt;
- each cell retains its existing strict identity-status validation;
- `provisional_source_record_id` remains unchanged for both Persons;
- explanatory cell notes record the independent official evidence and the limited scope of the identity change.

The historical `TX_ROLE_TERM_DATE_AUDIT` text saying the Person remained provisional is preserved as execution history. A superseding cell note now states that the current Person status is `AUTHORITATIVE`.

## Explicit non-changes

The identity-resolution execution did not change:

- either `person_id`;
- either canonical Person name;
- either `role_term_id`;
- either RoleTerm `CURRENT` status;
- the January 14, 2025 current-service start dates;
- the blank actual end dates;
- either Office ID;
- either retained SourceRecord ID;
- source QA blockers;
- `complete_jurisdiction=false` for the bounded slice;
- the default production package catalog;
- the default Civic GPS registry extension;
- repository activation state.

## Successor artifact requirement

The previous bounded package/acceptance artifact contained provisional Person status and is therefore historical. Identity resolution changes package content.

Before production deployment validation or activation, the two-office package must be regenerated from the current governed workbook state and a fresh `texas-bounded-acceptance/0.1` receipt must be issued for the new package hash. The production profile requires both Persons to carry explicit `AUTHORITATIVE` status; missing identity status fails closed.

Until that successor package and receipt exist:

`PERSON_IDENTITY_SOURCE = RESOLVED`

`SUCCESSOR_PACKAGE = REQUIRED`

`PRODUCTION_DEPLOYMENT = NOT_VALIDATED`

`REPOSITORY_ACTIVATION = NOT_ACTIVATED`
