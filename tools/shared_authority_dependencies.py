"""Caller-reviewed shared authority dependencies; no identities or geography minted.

The review policy is trusted configuration supplied separately by the caller.
Package content, assertions, notes, QA flags and catalog entries cannot authorize
themselves. No production policy is shipped. Exact row comparison binds review
to its source snapshot; a changed row needs a new independent review.
"""
from __future__ import annotations

import copy
import json
from datetime import date
from collections.abc import Mapping


class SharedAuthorityError(ValueError):
    pass


KEYS = {"bodies": "body_id", "divisions": "division_id",
        "identifier_crosswalk": "crosswalk_id", "source_evidence": "source_id",
        "source_assertions": "assertion_id"}
FAMILIES = {"bodies": "Body", "divisions": "Division", "offices": "Office",
            "people": "Person", "role_terms": "RoleTerm",
            "leadership_roles": "LeadershipRole", "identifier_crosswalk": "IdentifierCrosswalk"}


def _fail(code):
    raise SharedAuthorityError(code)


def _same(a, b):
    # Python equality treats True as 1; a review must not.
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def _index(rows, key):
    if not isinstance(rows, list):
        _fail("SHARED_ROWS_INVALID:" + key)
    result = {}
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("SHARED_ROW_INVALID:" + key)
        value = row.get(key) or row.get("id")
        if not isinstance(value, str) or not value or value in result:
            _fail("SHARED_ID_INVALID_OR_DUPLICATE:" + key)
        if row.get(key) and row.get("id") and row[key] != row["id"]:
            _fail("SHARED_ID_ALIAS_CONFLICT:" + key)
        result[value] = row
    return result


def _sources(row):
    values = row.get("source_ids") or []
    if isinstance(values, str):
        values = [x.strip() for x in values.split(";") if x.strip()]
    if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values):
        _fail("SHARED_SOURCE_IDS_INVALID")
    return values + ([row["source_id"]] if row.get("source_id") else [])


def office_body_id(office, bodies):
    """Preserve the historical unscoped, single-body adapter convention only.

    Native scoped rows and all shared rows require explicit body_id. Missing
    bodies and ambiguous legacy collections never qualify for this fallback.
    """
    explicit = office.get("body_id") or office.get("parent_id")
    if explicit:
        return explicit
    if not office.get("jurisdiction_id") and all(not row.get("jurisdiction_id") for row in bodies.values()):
        exact = "body:" + str(office.get("office_id") or office.get("id") or "").removeprefix("office:")
        if exact in bodies:
            return exact
        if len(bodies) == 1:
            return next(iter(bodies))
    return None


def body_graph_errors(records):
    """Validate declared Body links without inventing standalone memberships.

    Legacy packages may contain standalone offices or omit the Body model.
    An absent association is not a dangling reference; every declared link must
    resolve. Shared policies separately require exact explicit Office links.
    """
    try:
        bodies = _index(records.get("bodies", []), "body_id")
        offices = _index(records.get("offices", []), "office_id")
        for body in bodies.values():
            parent = body.get("parent_body_id")
            if parent and (parent not in bodies or parent == (body.get("body_id") or body.get("id"))):
                _fail("BODY_PARENT_FK")
        for office in offices.values():
            body = office_body_id(office, bodies)
            if body is not None and body not in bodies:
                _fail("OFFICE_BODY_FK")
            if office.get("body_id") and office.get("parent_id") and office["body_id"] != office["parent_id"]:
                _fail("OFFICE_BODY_ALIAS_CONFLICT")
        for table in ("role_terms", "leadership_roles"):
            for row in records.get(table, []):
                office = offices.get(row.get("office_id"))
                body = row.get("body_id")
                if body and (body not in bodies or not office or body != office_body_id(office, bodies)):
                    _fail("ROLE_TERM_OFFICE_BODY_MISMATCH" if table == "role_terms" else "LEADERSHIP_OFFICE_BODY_MISMATCH")
        return []
    except (SharedAuthorityError, TypeError, AttributeError) as exc:
        return [str(exc)]


def resolve_dependencies(package, reviewed_dependencies=None):
    """Return validated associations; raises on missing, ambiguous or drifted review."""
    try:
        return _resolve(package, reviewed_dependencies)
    except SharedAuthorityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SharedAuthorityError("SHARED_DEPENDENCY_INPUT_INVALID") from exc


def _resolve(package, policy):
    records = package["records"]
    jid = package["jurisdiction"]["jurisdiction_id"]
    bodies = _index(records.get("bodies", []), "body_id")
    offices = _index(records.get("offices", []), "office_id")
    errors = body_graph_errors(records)
    if errors:
        _fail(errors[0])
    foreign = {bid: row for bid, row in bodies.items() if row.get("jurisdiction_id") not in (None, "", jid)}
    context = {"jurisdictions": {}, "body_jurisdictions": {}, "body_capacities": {},
               "approved": {table: {} for table in KEYS}, "shared_body_ids": set(), "jurisdiction_divisions": {}}
    # Legacy same-jurisdiction records may omit jurisdiction_id. A policy never
    # permits a shared Body to erase its institutional jurisdiction this way.
    if policy is None:
        if foreign:
            _fail("SHARED_AUTHORITY_REVIEW_REQUIRED")
        provenance = package.get("provenance", {})
        # Provenance also supports opaque snapshot metadata, not only row lists.
        # Only declared evidence/assertion collections carry entity scope.
        source_rows = [provenance.get(name, []) for name in ("source_evidence", "source_assertions")]
        for rows in list(records.values()) + source_rows:
            if not isinstance(rows, list):
                _fail("SHARED_DEPENDENCY_INPUT_INVALID")
            for row in rows:
                if not isinstance(row, Mapping):
                    _fail("SHARED_DEPENDENCY_INPUT_INVALID")
                if row.get("jurisdiction_id") not in (None, "", jid):
                    _fail("SHARED_UNREVIEWED_DEPENDENCY_SCOPE")
        for office in offices.values():
            body = bodies.get(office_body_id(office, bodies), {})
            if body and office.get("jurisdiction_id") and not body.get("jurisdiction_id"):
                _fail("BODY_JURISDICTION_REQUIRED")
        return context
    if not isinstance(policy, Mapping) or policy.get("package_jurisdiction_id") != jid:
        _fail("SHARED_REVIEW_SCOPE")
    if not all(isinstance(policy.get(k), str) and policy[k].strip() for k in ("review_id", "reviewed_by", "reviewed_at")):
        _fail("SHARED_REVIEW_METADATA_REQUIRED")
    jurisdictions = _index(policy["jurisdictions"], "jurisdiction_id")
    if not jurisdictions or jid in jurisdictions:
        _fail("SHARED_INSTITUTIONAL_JURISDICTION_INVALID")
    if set(policy["records"]) != {"bodies", "divisions", "identifier_crosswalk"} or set(policy["provenance"]) != {"source_evidence", "source_assertions"}:
        _fail("SHARED_DEPENDENCY_TABLE_SCOPE")
    for table, key in KEYS.items():
        section = "provenance" if table.startswith("source_") else "records"
        approved = _index(policy[section][table], key)
        actual = _index(package[section][table], key)
        for entity_id, row in approved.items():
            if entity_id not in actual or not _same(row, actual[entity_id]):
                _fail("SHARED_DEPENDENCY_ROW_DRIFT:" + table + ":" + entity_id)
        for entity_id, row in actual.items():
            if row.get("jurisdiction_id") not in (None, "", jid) and entity_id not in approved:
                _fail("SHARED_UNREVIEWED_DEPENDENCY:" + table + ":" + entity_id)
        context["approved"][table] = approved
    if set(context["approved"]["bodies"]) != set(foreign):
        _fail("SHARED_BODY_REVIEW_MISMATCH")
    if not foreign or {b.get("jurisdiction_id") for b in foreign.values()} != set(jurisdictions):
        _fail("SHARED_INSTITUTIONAL_JURISDICTION_MISMATCH")
    seen_ids = set()
    for table, key in {"bodies": "body_id", "divisions": "division_id", "offices": "office_id", "people": "person_id", "role_terms": "role_term_id", "leadership_roles": "leadership_id", "identifier_crosswalk": "crosswalk_id"}.items():
        ids = set(_index(records.get(table, []), key))
        if seen_ids & ids:
            _fail("SHARED_DUPLICATE_ENTITY_ID")
        seen_ids |= ids
    reviewed_offices = _index(policy["represented_offices"], "office_id")
    actual_shared_offices = {oid: row for oid, row in offices.items() if (row.get("body_id") or row.get("parent_id")) in foreign}
    if set(reviewed_offices) != set(actual_shared_offices) or not reviewed_offices:
        _fail("SHARED_REPRESENTED_OFFICE_SCOPE")
    divisions = _index(records["divisions"], "division_id")
    capacities = policy["body_capacities"]
    if not isinstance(capacities, Mapping) or set(capacities) != set(foreign):
        _fail("SHARED_BODY_CAPACITY_REQUIRED")
    for bid, total in capacities.items():
        if type(total) is not int or total <= 0:
            _fail("SHARED_BODY_CAPACITY_INVALID")
        allocations = 0
        for oid, row in actual_shared_offices.items():
            if not _same(row, reviewed_offices[oid]):
                _fail("SHARED_REPRESENTED_OFFICE_DRIFT:" + oid)
            division = divisions.get(row.get("represented_division_id"))
            if row.get("jurisdiction_id") != jid or not division or division.get("jurisdiction_id") != jid or row.get("represented_division_id") not in context["approved"]["divisions"]:
                _fail("SHARED_REPRESENTED_GEOGRAPHY_SCOPE")
            seats = row.get("seats")
            if type(seats) is not int or seats <= 0:
                _fail("SHARED_REPRESENTATIVE_CAPACITY_INVALID")
            if row.get("body_id") == bid:
                allocations += seats
        if allocations == 0:
            _fail("SHARED_BODY_NOT_REFERENCED")
        if allocations > total:
            _fail("SHARED_REPRESENTATION_EXCEEDS_BODY_CAPACITY")
    evidence = _index(package["provenance"]["source_evidence"], "source_id")
    crosswalks = _index(records["identifier_crosswalk"], "crosswalk_id")
    ocdids = {package["jurisdiction"].get("ocd_jurisdiction_id") or package["jurisdiction"].get("jurisdiction_ocdid")}
    institutional_divisions = policy.get("institutional_divisions")
    if institutional_divisions is None:
        institutional_divisions = {key: row.get("division_id") for key, row in jurisdictions.items()}
    if not isinstance(institutional_divisions, Mapping) or set(institutional_divisions) != set(jurisdictions):
        _fail("SHARED_INSTITUTIONAL_DIVISION_SCOPE")
    for native_id, jurisdiction in jurisdictions.items():
        ocdid = jurisdiction.get("ocd_jurisdiction_id")
        if not isinstance(ocdid, str) or not ocdid.startswith("ocd-jurisdiction/") or ocdid in ocdids:
            _fail("SHARED_INSTITUTIONAL_OCDID_INVALID")
        ocdids.add(ocdid)
        division_id = institutional_divisions[native_id]
        if jurisdiction.get("division_id") and jurisdiction["division_id"] != division_id:
            _fail("SHARED_INSTITUTIONAL_DIVISION_CONFLICT")
        division = divisions.get(division_id)
        if not division or division.get("jurisdiction_id") != native_id or not str(division.get("ocd_division_id") or "").startswith("ocd-division/"):
            _fail("SHARED_INSTITUTIONAL_DIVISION_REQUIRED")
        candidates = [r for r in crosswalks.values() if r.get("entity_id") == native_id and r.get("id_type") == "OCD_JURISDICTION_ID"]
        if len(candidates) != 1:
            _fail("SHARED_JURISDICTION_CROSSWALK_MISSING_OR_AMBIGUOUS")
        crosswalk = candidates[0]
        if crosswalk.get("entity_type") != "Jurisdiction" or crosswalk.get("status") != "VERIFIED" or crosswalk.get("external_id") != ocdid or crosswalk.get("source_id") not in evidence or crosswalk.get("crosswalk_id") not in context["approved"]["identifier_crosswalk"]:
            _fail("SHARED_JURISDICTION_CROSSWALK_INVALID")
    families = {jid: "Jurisdiction", **{x: "Jurisdiction" for x in jurisdictions}}
    for table, family in FAMILIES.items():
        key = {"people": "person_id", "offices": "office_id", "role_terms": "role_term_id", "leadership_roles": "leadership_id"}.get(table, KEYS.get(table))
        for row in records.get(table, []):
            entity_id = row.get(key) or row.get("id") or row.get("leadership_role_id")
            if entity_id:
                families[entity_id] = family
    for table, approved in context["approved"].items():
        for row in approved.values():
            if table == "source_evidence":
                if families.get(row.get("supports_entity_id")) != row.get("supports_entity_type") or not row.get("url"):
                    _fail("SHARED_EVIDENCE_TARGET_FK")
            elif table == "source_assertions":
                if families.get(row.get("subject_id")) != row.get("subject_type") or row.get("source_id") not in evidence:
                    _fail("SHARED_ASSERTION_FK")
                if row.get("object_type") == "ID" and row.get("object_value") not in families:
                    _fail("SHARED_ASSERTION_OBJECT_FK")
            else:
                refs = _sources(row)
                if not refs or any(src not in context["approved"]["source_evidence"] for src in refs):
                    _fail("SHARED_DEPENDENCY_SOURCE_FK")
                if table == "identifier_crosswalk" and families.get(row.get("entity_id")) != row.get("entity_type"):
                    _fail("SHARED_CROSSWALK_ENTITY_FK")
    for row in list(jurisdictions.values()) + list(reviewed_offices.values()):
        if not _sources(row) or any(src not in context["approved"]["source_evidence"] for src in _sources(row)):
            _fail("SHARED_REPRESENTATION_SOURCE_FK")
    for table in ("offices", "role_terms", "leadership_roles", "people"):
        for row in records.get(table, []):
            if row.get("jurisdiction_id") not in (None, "", jid):
                _fail("SHARED_UNREVIEWED_ENTITY_SCOPE:" + table)
    current_counts = {oid: 0 for oid in reviewed_offices}
    current_pairs = set()
    for term in records.get("role_terms", []):
        if term.get("office_id") in reviewed_offices:
            statuses = [str(term[key] or "UNKNOWN").upper() for key in ("status", "currentness_status", "role_term_status") if key in term]
            statuses = ["CURRENT" if value == "CURRENT_VERIFIED" else value for value in statuses]
            if len(set(statuses)) > 1:
                _fail("SHARED_ROLE_TERM_STATUS_CONFLICT")
            if statuses and statuses[0] == "CURRENT":
                oid = term["office_id"]
                pair = (term.get("person_id"), oid)
                if pair in current_pairs:
                    _fail("SHARED_DUPLICATE_CURRENT_MEMBERSHIP")
                current_pairs.add(pair)
                current_counts[oid] += 1
                if current_counts[oid] > reviewed_offices[oid]["seats"]:
                    _fail("SHARED_CURRENT_HOLDERS_EXCEED_ALLOCATION")
            for aliases in (("term_start", "start_date", "term_start_date"), ("term_end", "end_date", "term_end_date")):
                values = [term[key] or None for key in aliases if key in term]
                valid_key = "valid_from" if aliases[0] == "term_start" else "valid_to"
                if term.get("interval_semantics") == "ACTUAL_TENURE" and valid_key in term:
                    values.append(term[valid_key] or None)
                if values and any(value != values[0] for value in values):
                    _fail("SHARED_ROLE_TERM_DATE_CONFLICT")
                for value in values:
                    if value is not None:
                        try:
                            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                                raise ValueError("not an exact ISO date")
                        except ValueError:
                            _fail("SHARED_ROLE_TERM_DATE_INVALID")
            if term.get("body_id") != reviewed_offices[term["office_id"]]["body_id"] or term.get("jurisdiction_id") != jid:
                _fail("SHARED_ROLE_TERM_RELATION_REQUIRED")
            if not _sources(term) or any(src not in evidence for src in _sources(term)):
                _fail("SHARED_ROLE_TERM_SOURCE_FK")
    context.update(jurisdictions=jurisdictions, jurisdiction_divisions=dict(institutional_divisions), shared_body_ids=set(foreign), body_capacities=dict(capacities),
                   body_jurisdictions={bid: jurisdictions[row["jurisdiction_id"]]["ocd_jurisdiction_id"] for bid, row in foreign.items()})
    return context


def dependency_errors(package, reviewed_dependencies=None):
    try:
        resolve_dependencies(package, reviewed_dependencies)
        return []
    except SharedAuthorityError as exc:
        return [str(exc)]


def include_reviewed_dependencies(package, snapshot_rows, reviewed_dependencies=None):
    """Copy only exact reviewed rows from a producer snapshot; never fabricate rows.

    snapshot_rows maps native table families (including jurisdictions) to rows.
    The caller remains responsible for all existing production/QA gates.
    """
    result = copy.deepcopy(package)
    if reviewed_dependencies is None:
        resolve_dependencies(result)
        return result
    try:
        for table, key in {**KEYS, "jurisdictions": "jurisdiction_id"}.items():
            section = "provenance" if table.startswith("source_") else "records"
            requested = reviewed_dependencies["jurisdictions"] if table == "jurisdictions" else reviewed_dependencies[section][table]
            available = _index(snapshot_rows[table], key)
            for entity_id, row in _index(requested, key).items():
                if entity_id not in available or not _same(row, available[entity_id]):
                    _fail("SHARED_SNAPSHOT_ROW_DRIFT:" + table + ":" + entity_id)
                if table != "jurisdictions":
                    existing = _index(result[section][table], key)
                    if entity_id in existing:
                        if not _same(row, existing[entity_id]):
                            _fail("SHARED_DEPENDENCY_ROW_DRIFT:" + table + ":" + entity_id)
                    else:
                        result[section][table].append(copy.deepcopy(row))
                    result[section][table].sort(key=lambda r: r[key])
        resolve_dependencies(result, reviewed_dependencies)
        return result
    except SharedAuthorityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SharedAuthorityError("SHARED_DEPENDENCY_INPUT_INVALID") from exc
