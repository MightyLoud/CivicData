"""Bounded Texas House 49 / Senate 14 routing for explicit internal review."""
from __future__ import annotations

from civic_gps_extensions.loader import load_resolver_with_extensions
from civic_gps_extensions.legislative import validate_legislative_groups
from civic_gps_extensions.texas_geometry_governance import (
    GeometryGovernanceFailure,
    PINS as GEOMETRY_PINS,
    POLICY_ID as GEOMETRY_POLICY_ID,
    verify_texas_geometry_governance,
)
from consumers.empowered_vote import representation
from tools.jurisdiction_package import validate_identity_graph

SOURCES = {
    "house": {
        "adapter_id": "DIST-TX-HOUSE-H2316", "district": "49", "division_kind": "SLDL",
        "division_type": "state_house_district", "plan_id": "PLANH2316",
        "service_url": GEOMETRY_PINS["house"]["service_url"],
        "authority_url": GEOMETRY_PINS["house"]["authority_url"],
        "vintage_status": "GOVERNED_ACCEPTANCE_REQUIRED__TLC_PLANH2316",
    },
    "senate": {
        "adapter_id": "DIST-TX-SENATE-S2168", "district": "14", "division_kind": "SLDU",
        "division_type": "state_senate_district", "plan_id": "PLANS2168",
        "service_url": GEOMETRY_PINS["senate"]["service_url"],
        "authority_url": GEOMETRY_PINS["senate"]["authority_url"],
        "vintage_status": "GOVERNED_ACCEPTANCE_REQUIRED__88TH_DESCRIPTION_89TH_LAYER_CAVEAT_RETAINED",
    },
}


def build_texas_internal_configuration(package, *, house_division_id, senate_division_id):
    """Caller supplies canonical IDs explicitly; labels never generate IDs."""
    if validate_identity_graph(package.get("records")):
        raise ValueError("invalid source package identity graph")
    jurisdiction = package.get("jurisdiction", {})
    if jurisdiction.get("state_abbr") != "TX" or jurisdiction.get("geoid") != "48":
        raise ValueError("the Texas state package is required")
    if not jurisdiction.get("jurisdiction_id") or not jurisdiction.get("name"):
        raise ValueError("canonical jurisdiction ID and name are required")
    jid = jurisdiction["jurisdiction_id"]
    divisions = {d.get("division_id"): d for d in package["records"]["divisions"]}
    adapters, bindings = [], []
    for chamber, did in (("house", house_division_id), ("senate", senate_division_id)):
        source = SOURCES[chamber]
        if not isinstance(did, str) or did not in divisions:
            raise ValueError("explicit canonical division ID is missing from package")
        division = divisions[did]
        if division.get("division_kind") != source["division_kind"] or not division.get("division_name"):
            raise ValueError("canonical division kind and name must agree with the chamber")
        # This helper is intentionally bound to the inspected two-district slice.
        # Validate the supplied mapping against the recorded label; do not derive an ID.
        if not division["division_name"].endswith(" District " + source["district"]):
            raise ValueError("canonical division label disagrees with the bounded district key")
        adapters.append({
            "adapter_id": source["adapter_id"], "service_url": source["service_url"],
            "district_field": "DIST_NBR", "division_type": source["division_type"],
            "districts": {source["district"]: {"division_id": did, "name": division["division_name"]}},
            "boundary_probe_distance_meters": 1,
            "source": {k: source[k] for k in ("plan_id", "authority_url", "vintage_status")},
        })
        bindings.append({
            "binding_id": "tx-" + chamber, "package_jurisdiction_id": jid,
            "civic_gps_jurisdiction_id": jid, "district_adapter_id": source["adapter_id"],
            "district_division_map": {source["district"]: did},
        })
    groups = [{
        "group_id": "GEO-TX-LEGISLATIVE-TWO-DISTRICTS", "state_geoid": "48",
        "jurisdiction": {"jurisdiction_id": jid, "name": jurisdiction["name"]},
        "district_adapters": adapters, "scope": "INTERNAL_REVIEW", "publication_eligible": False,
    }]
    validate_legislative_groups(groups)
    return groups, bindings


def resolve_texas_internal_preview(package, address, *, repo_root, house_division_id,
                                   senate_division_id, session=None, timeout_seconds=30.0):
    """Explicit opt-in; never registers a package or changes production QA."""
    groups, bindings = build_texas_internal_configuration(
        package, house_division_id=house_division_id, senate_division_id=senate_division_id)

    if session is None:
        try:
            geometry_governance = verify_texas_geometry_governance(timeout_seconds=timeout_seconds)
        except GeometryGovernanceFailure as exc:
            return {
                "status": "FAIL-CLOSED", "scope": "INTERNAL_REVIEW",
                "complete_jurisdiction": False, "publication_eligible": False, "canonical_writes": 0,
                "geometry_governance": {
                    "status": "FAIL", "policy_id": GEOMETRY_POLICY_ID,
                    "error_code": "GEOMETRY_VERSION_DRIFT", "summary": str(exc),
                },
                "geography": None,
                "representation": {"status": "FAIL-CLOSED", "error": "GEOMETRY_VERSION_DRIFT"},
            }
    else:
        geometry_governance = {
            "status": "CONTROLLED_TEST_SESSION_NOT_LIVE_VERIFIED",
            "policy_id": GEOMETRY_POLICY_ID,
        }

    resolver = load_resolver_with_extensions(
        repo_root, legislative_overlays=groups, session=session, timeout_seconds=timeout_seconds)
    gps = resolver.resolve(address, observed_on=None)
    preview = representation.preview_representation_for_bindings(package, address, gps, bindings=bindings)
    return {"status": preview["status"], "scope": "INTERNAL_REVIEW",
            "complete_jurisdiction": False, "publication_eligible": False, "canonical_writes": 0,
            "geometry_governance": geometry_governance,
            "geography": gps, "representation": preview}
