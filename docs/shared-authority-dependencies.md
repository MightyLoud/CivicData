# Reviewed shared-authority dependencies

This is a bounded software compatibility path. It supplies no production
authority identity, Division, holder, service area, review approval or release.
No Michigan workbook field or published schema changes. Ordinary same-jurisdiction
packages retain their existing path. Unsupported shared records fail closed.

## Trust boundary

`reviewed_dependencies` is an optional keyword supplied by a trusted caller,
separately from the package, catalog, assertions and resolver output. It is not
loaded from any of those inputs. The default rejects cross-jurisdiction Bodies.
The caller must authenticate and independently approve the policy before using
it; review labels in a JSON file are not authentication or a certificate.
There is intentionally no production policy or CLI auto-discovery mechanism.

The policy contains:

- `review_id`, `reviewed_by`, `reviewed_at`, `package_jurisdiction_id`.
- `jurisdictions`: exact reviewed native institutional Jurisdiction rows,
  including `jurisdiction_id`, `ocd_jurisdiction_id`, and `source_ids`.
- `institutional_divisions`: an explicit native jurisdiction ID → approved
  institutional Division ID mapping. This sidecar association avoids adding a
  native Jurisdiction column. For normalized inputs that already have
  `Jurisdiction.division_id`, that existing field may supply the association;
  if both forms are supplied they must agree.
- `records`: exactly `bodies`, `divisions`, `identifier_crosswalk`; these are
  complete reviewed native rows, not replacement identities. Include both
  institutional and represented Divisions. Their distinct native IDs/OCDIDs are
  preserved; neither constitutes service-area approval.
- `provenance`: exactly `source_evidence` and `source_assertions`; pin all evidence
  used by the reviewed rows, including evidence under the represented jurisdiction.
- `represented_offices`: exact reviewed native Office rows under the package
  jurisdiction, referencing the one canonical Body and an accepted represented
  Division. Every shared Office must be listed, with integer positive `seats`.
- `body_capacities`: whole-body capacities keyed by canonical Body ID. A Post's
  allocation remains separate. Shared allocations in a package may not exceed
  the whole body; leadership creates no seats.

Every institutional jurisdiction needs exactly one included, reviewed crosswalk:
`entity_type=Jurisdiction`, `entity_id=<native institutional ID>`,
`id_type=OCD_JURISDICTION_ID`, `status=VERIFIED`, `external_id=<institutional OCDID>`,
and a resolvable `source_id`. Institutional OCDIDs may not collide with the
package's OCDID or another institutional jurisdiction's OCDID. Reconciliation of
legitimate aliases would require a separate reviewed integration decision.

Rows are compared as complete JSON values with type-sensitive equality. A
changed body, jurisdiction, geography, source or crosswalk requires a new review.
Policy scope, duplicate IDs, Body/Office/RoleTerm links, crosswalk uniqueness,
provenance links, represented geography, and capacities fail closed. A package
cannot widen this allowlist. Sources and assertions remain in package provenance.

## Entry points

The keyword is supported by:

- `tools.co_factory_export.build_package`: adds exact reviewed rows found in the
  native snapshot and reconciles source counts, then runs strict QA. The existing
  CO `export_snapshot` decision/authorized-jurisdiction guard is unchanged. This
  does not activate an uninspected Michigan production exporter.
- `tools.shared_authority_dependencies.include_reviewed_dependencies`: reusable
  source-snapshot closure for another explicitly integrated producer.
- Generic and strict package `validate` / `build`, plus strict `verify_package`.
- `from_jurisdiction_package` and `export_factory_package`.
- Legacy `load_jurisdiction_package`, `reconstruct_package`, and the municipal
  `build_representation_from_live_address` → catalog → direct representation path.

The sidecar is deliberately not serialized into a package as authorization.
Consumers must receive the same separately reviewed policy. Other catalog
profiles are not activated by this change and remain fail closed for shared
records. Contract v1's existing organization ID and institutional jurisdiction
fields are retained; its assertion validator recognizes only jurisdictions
explicitly referenced by the package or an organization.

For reviewed shared Bodies, legacy output now includes Body/organization ID and name, institutional native
jurisdiction/OCDID, represented native jurisdiction, and (for reviewed shared
bodies) whole-body capacity. `seat_capacity` is still the represented Office's
allocation. Address routing still requires the represented jurisdiction and
existing geographic binding. Institutional/service geography never activates an
Office. Dangling declared Body links fail even in direct projections. Legacy standalone
offices without a declared Body retain their prior output, without inferred
organization fields. Organization-dependent Core/Contract exports fail closed
when a scoped Office has no institutional association. The prior unscoped
single-body/exact-ID convention survives only for unscoped legacy rows.

Shared status/date aliases may not conflict. Observation intervals and expected
expiry years are not actual tenure. Only explicit actual date aliases, or
`valid_from` / `valid_to` with `interval_semantics=ACTUAL_TENURE`, become tenure
dates. Unknown membership cannot become a current holder or certified through
export defaults. Contract `opened_at` / `closed_at` retain their existing record
lifecycle semantics, distinct from `start_date` / `end_date` actual tenure.

All prior partial-scope, blocking-gap, provenance, parity, certification and
release requirements remain applicable. Identity review is not completion.

## Tests and limits

Run from the repository root:

```sh
python tests/test_shared_authority_dependencies.py
python tests/test_jurisdiction_package.py
python tests/test_jurisdiction_package_strict.py
python tests/test_co_factory_export.py
python tests/test_canonical_representation_core.py
python tests/test_role_term_integration.py
python tests/test_public_identity_disposition.py
python -m compileall -q tools consumers adapters tests
```

The new suite requires the existing CI `jsonschema` dependency. It covers 6/3 and
11/2 capacities, schema conformance, exact producer closure and count checks,
strict build/verify, both converters, and the actual legacy address function
through a local ZIP/catalog with an injected synthetic resolver. It includes
negative identity, crosswalk, source, geography, scope, certification and temporal
controls. The synthetic fixture is labeled and contains no real authority IDs.

This verifies software plumbing, not a live Eagle address or authority fact.
Eagle's canonical institutions, governed crosswalks, represented Divisions,
current-service and territorial controls still require independent acceptance.
No service-area inference, boundary acceptance, native graph promotion or full
completion certificate is supplied by these tests.
