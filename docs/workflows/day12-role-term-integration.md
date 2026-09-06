# Day 12 RoleTerm integration patch

This patch supplies a representation bridge and validation controls for the
two-chain Texas integration. It does not register a Texas package, change any
canonical civic records, or release an address-to-official service.

## Projection contract

`consumers/empowered_vote/representation.py::project_role_term` copies a record
and accepts the existing consumer names plus the explicit Texas field names:

| Source field | Consumer field | Behavior |
| --- | --- | --- |
| `role_term_status` | `status` | Currentness belongs to the RoleTerm. |
| `term_start_date` | `start_date` | Exact ISO date; blank becomes null. |
| `term_end_date` | `end_date` | Blank remains unknown; no scheduled end is inferred. |
| `role_term_id`, `person_id`, `office_id` | Same IDs | Pass through; never re-key from labels. |
| `source_record_id`, `observed_at` | Same fields on holder output | Preserve lineage and observation time. |
| `source_id`, `source_ids` | Same evidence relationships | Declared references must resolve to package evidence. |

`status/currentness_status`, `term_start/start_date`, and `term_end/end_date`
remain supported. When two aliases are present they must agree. An explicitly
blank source field cannot be filled silently by a conflicting nonblank alias.
Texas date fields reject partial dates, spreadsheet serials, and impossible
dates. The consumer continues to expose dates as `term_start` and `term_end`.

The builder and package loader share explicit per-table primary keys and require
each RoleTerm's Person and Office to exist. Source IDs cannot masquerade as
primary IDs. Existing `id` aliases and the existing leadership/crosswalk key
spellings remain supported. Reused evidence references do not imply duplicate
entity IDs. Declared RoleTerm evidence references are checked on build, load,
and direct representation calls. Existing semicolon-separated factory evidence
IDs are interpreted for validation while their original representation is retained.

## Provisional identity

The default representation function returns `PERSON_IDENTITY_PROVISIONAL` when
an applicable current holder has a provisional Person. It does not upgrade the
identity because the RoleTerm is current.

The explicit `identity_policy="INTERNAL_REVIEW"` option permits previewing that
same holder with `person_status=PROVISIONAL`, a visible per-Person warning, and
`publication_eligible=false`. The source records and existing warnings are
preserved. This is an implementation disposition for internal review, not a
decision granting public eligibility to provisional identities.

## Separate district bindings

`preview_representation_for_bindings(package, address, civic_gps_result,
bindings=...)` composes separately supplied district bindings. Each binding
requires a unique `binding_id`, the package/GPS jurisdiction IDs, a district
adapter ID, and either a `district_division_map` or an existing
`division_template`. An explicit map is preferred for opaque canonical IDs:

```python
# Synthetic example only; these are not production IDs or GIS configuration.
bindings = [{
    "binding_id": "house",
    "package_jurisdiction_id": "test-jurisdiction",
    "civic_gps_jurisdiction_id": "test-gps-jurisdiction",
    "district_adapter_id": "test-adapter-house",
    "district_division_map": {"49": "opaque-canonical-division-0"},
}, {
    "binding_id": "senate",
    "package_jurisdiction_id": "test-jurisdiction",
    "civic_gps_jurisdiction_id": "test-gps-jurisdiction",
    "district_adapter_id": "test-adapter-senate",
    "district_division_map": {"14": "opaque-canonical-division-1"},
}]
```

Every selected division must exist in the package. Missing, outside-scope,
ambiguous, overlapping, or invalid bindings fail the whole preview without
returning a partial set of officials. Caller-supplied GPS officeholders/actions
are ignored. The result is deterministic, has `scope=BOUND_BINDINGS_ONLY`,
`complete_jurisdiction=false`, `publication_eligible=false`, and zero canonical
writes. No Texas binding or package is added to the production catalog.

## Verification and remaining work

Run `python tests/test_role_term_integration.py`. Its fixtures are synthetic;
district keys 49/14 exercise separate chambers without asserting real geography
or identities. The controls cover aliases, exact dates, unknowns, orphan links,
duplicate keys, evidence links, provisional identity, source immutability,
separate district bindings, negative/ambiguous cases, and deterministic output.
Existing v0.1/v0.2, Tacoma, Akron, Fircrest, and consumer/onboarding regressions
remain relevant. Both affected CI workflows invoke the new controls. The
package workflow also triggers on package/data changes; it still does not
automatically certify every new artifact found under those paths.

Day 12 requires additional evidence before closeout:

1. Materialize the exact two promoted chains with their existing canonical
   divisions/offices and claim-level occupancy **and** start-date provenance.
   Preserve the historical frozen proof package and its original hash.
2. Ground actual House/Senate adapter IDs and canonical division crosswalks;
   decide how a partial two-office slice satisfies the package coverage contract
   without asserting complete Texas coverage or inventing QA/parity flags.
3. Execute official live address, outside-district, and boundary controls using
   the intended runtime. Synthetic geography tests are not live proof.
4. Verify deterministic package hashes, target parity, the intended CI steps on
   the candidate commit, and the release/consumer identity disposition.
5. Synchronize the tracker only to the integration state actually achieved.

The protected main branch continues to require its existing PR and Civic GPS
release gate. A GPS gate that takes its unrelated-change success path does not
constitute Texas integration proof. Merge, publication, and production activation
are separate from this patch.
