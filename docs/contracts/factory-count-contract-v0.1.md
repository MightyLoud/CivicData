# Factory count contract v0.1

The factory representation adapter validates an explicit count sidecar before
exporting the profiled Bowie and Victory scopes. Existing unprofiled packages
without this sidecar retain their current payloads and certification behavior.
No count basis is inferred from state, name or a numerical match.

The reviewed profiles in `adapters/factory/Civic_Tracker_Count_Profiles.json`
preserve the October 13 count interpretation: `jurisdiction-tx-09640` counts
Office containers, while `jurisdiction-vt-cousub-5000975175` counts seat capacity.
The registry is the same declaration retained in the verified RC1 replay package.
Missing or malformed registry configuration stops export.

`qa.factory_count_contract` must contain these fields:

| Field | Meaning |
| --- | --- |
| `schema` | `CIVIC_FACTORY_COUNT_CONTRACT_v0.1` |
| `jurisdiction_id` | Exact input package jurisdiction ID |
| `scope` | `ACTIVE_OFFICES_CURRENT_ROLE_TERMS` |
| `tracker_count_basis` | `OFFICE_CONTAINERS` or `SEAT_CAPACITY`, matching the reviewed profile when present |
| `active_offices` | Captured tracker count in its declared unit |
| `current_role_terms` | Captured tracker current-role count |
| `vacant_offices` | Captured tracker explicit vacant-seat count |
| `source_workbook_sha256` | Lowercase 64-character hash of the captured source workbook |

The scoped records must contain exact-jurisdiction ACTIVE Offices and CURRENT
RoleTerms. Office seats are positive integers, never a fallback from a tracker.
Tracker counts are nonnegative integers. Boolean, missing, fractional, negative
and nonfinite values are rejected. Office and RoleTerm IDs must be unique.
Current roles must point to selected Offices, and a person cannot occupy the same
Office twice in this current scope. FILLED Offices require exactly their declared
occupancy; VACANT Offices require zero occupants. Unknown or inconsistent
occupancy, conflicting seat fields, lost records and counter drift stop export.
Historical records remain preserved upstream and are outside this active/current
sidecar contract. Partially vacant multi-seat containers need a later explicit
contract revision; the adapter does not guess their state.

`assess_factory_counts` returns a count diagnostic for preflight inspection.
The adapter does not add fields to Representation Contract v1, invent an OCD
crosswalk, supply missing service dates, alter approval, or certify count evidence
as a geography replay. The sidecar records a declared source hash; the upstream
capture/replay must verify those bytes and their lineage separately.

The earlier recovered pilot captures had blank jurisdiction OCD crosswalks;
their count preflight passed while representation export was held at the
governed-crosswalk requirement. On October 14, 2026, explicit jurisdiction and
Division crosswalks were applied and verified for Bowie and Victory, and fresh
scoped representation candidates passed local schema and consumer-graph checks.
These internal mappings do not verify upstream publication of government objects.
Candidate acceptance, release binding, independent geography replay and scoped
service activation remain separate gates. No crosswalk is inferred from FIPS or
municipal names, and this change adds neither pilot to the governed catalog or
hosted service.

Run `python -m unittest -v tests.test_factory_count_contract` for synthetic count
controls and exact compatibility comparisons against the five current Colorado
packages. The test fixtures do not assert new civic facts. Repository preparation,
PR creation, merge and live activation are distinct stages.
