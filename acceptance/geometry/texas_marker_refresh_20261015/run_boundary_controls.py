"""Live coordinate controls on the actual adapter; no address/geocoder requests."""
import json
from run_address_controls import ROOT, REPO, RUNTIME, PACKAGE_PATH, HOUSE, SENATE, RecordedSession, write
from civic_gps_extensions.texas_legislative import build_texas_internal_configuration
from civic_gps_extensions.loader import load_resolver_with_extensions
from civic_gps_extensions.legislative import _query_adapter, GeographyFailure


def main():
    package = json.loads(PACKAGE_PATH.read_text())
    groups, _ = build_texas_internal_configuration(package, house_division_id=HOUSE, senate_division_id=SENATE)
    fixtures = json.loads((ROOT / "boundary_fixtures.json").read_text())
    summary = []
    for fixture in fixtures:
        adapter = next(a for a in groups[0]["district_adapters"] if fixture["chamber"].upper() in a["adapter_id"])
        for position, expected in [("midpoint", "CONFLICT"), ("near_inside_025m", "CONFLICT"), ("clear_inside_10m", "PASS")]:
            case = {"case_id": "TX-BOUNDARY-" + fixture["chamber"].upper() + "-" + position,
                    "chamber": fixture["chamber"], "address": None, "point": fixture[position],
                    "expected": expected, "control_scope": "LIVE_COORDINATE_ADAPTER_ONLY"}
            session = RecordedSession(case, section="boundary_controls")
            with (session.directory / "attempt.json").open("x") as f:
                json.dump(case, f, indent=2)
            resolver = load_resolver_with_extensions(RUNTIME, session=session)
            engine = getattr(resolver, "engine", resolver)
            lon, lat = case["point"]
            try:
                key, evidence_urls = _query_adapter(engine, adapter, {"longitude": lon, "latitude": lat})
                result = {"status": "PASS", "key": key, "evidence_urls": evidence_urls}
            except GeographyFailure as exc:
                result = {"status": exc.status, "code": exc.code, "message": str(exc)}
            except Exception as exc:
                result = {"status": "SOURCE_ERROR", "code": type(exc).__name__, "message": str(exc)}
            counts = []
            for call in session.calls:
                body = json.loads((session.directory / call["response_file"]).read_text()) if call.get("response_file") else {}
                counts.append({"phase": "probe" if "distance" in call["params"] else "exact",
                               "feature_count": len(body.get("features", [])),
                               "district_keys": [f.get("attributes", {}).get("DIST_NBR") for f in body.get("features", [])],
                               "error": body.get("error")})
            row = dict(case, result=result, expected_status_met=result["status"] == expected,
                       observations=counts, geocoder_requests=session.geocoder_calls)
            write(session.directory / "result.json", row)
            summary.append(row)
            write(ROOT / "boundary_control_summary.json", summary)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
