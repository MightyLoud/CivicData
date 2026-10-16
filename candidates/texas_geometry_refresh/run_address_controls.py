"""Two new public-address attempts; append-only evidence, no automatic retries."""
from pathlib import Path
import copy
import datetime
import hashlib
import json
import sys
import requests

ROOT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
RUNTIME = None  # Supplied by run_controls.py after exact runtime reconstruction.
sys.path.insert(0, str(REPO))
from civic_gps_extensions.texas_legislative import resolve_texas_internal_preview

PACKAGE_PATH = None  # Supplied by run_controls.py from the committed successor package.
HOUSE = "div-wb020-8d372cd6f15770de5f452ceb224ec52929c30beddac3bdf9013864d538cbb449"
SENATE = "div-wb020-ed0238818cdb70336de04839d183a5a92c3af3ecb3f7bcd0cc330ba1e25d5f8b"
CASES = [
    {"case_id": "TX-LIVE-20261015-CAPITOL", "address": "1100 Congress Ave, Austin, TX 78701",
     "expect": "PASS", "address_authority": "https://tspb.texas.gov/plan/hours/hours.html"},
    {"case_id": "TX-LIVE-20261015-ROUND-ROCK", "address": "221 East Main Street, Round Rock, TX 78664",
     "expect": "FAIL-CLOSED", "address_authority": "https://www.roundrocktexas.gov/venue/round-rock-city-hall/"},
]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


class RecordedSession(requests.Session):
    def __init__(self, case, section="address_controls"):
        super().__init__()
        self.case = case
        self.directory = ROOT / section / case["case_id"]
        self.directory.mkdir(parents=True, exist_ok=True)
        self.calls = []
        self.geocoder_calls = 0

    def get(self, url, *, params, timeout):
        if "geocoding.geo.census.gov" in url:
            assert params["address"] == self.case["address"]
            self.geocoder_calls += 1
            assert self.geocoder_calls == 1, "A second geocoder request is forbidden in this attempt"
        index = len(self.calls) + 1
        item = {"request_number": index, "url": url, "params": copy.deepcopy(params),
                "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        self.calls.append(item)
        write(self.directory / "requests.json", self.calls)
        try:
            response = super().get(url, params=params, timeout=timeout)
            raw = self.directory / f"response_{index:02d}.json"
            raw.write_bytes(response.content)
            item.update(http_status=response.status_code, response_url=response.url,
                        response_file=raw.name, response_sha256=hashlib.sha256(response.content).hexdigest())
            return response
        except Exception as exc:
            item.update(exception_type=type(exc).__name__, exception=str(exc))
            raise
        finally:
            item["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            write(self.directory / "requests.json", self.calls)


def main():
    package_bytes = PACKAGE_PATH.read_bytes()
    package = json.loads(package_bytes)
    before = copy.deepcopy(package)
    summary = []
    for case in CASES:
        session = RecordedSession(case)
        started = session.directory / "attempt.json"
        with started.open("x") as f:
            json.dump(dict(case, attempt=1, retries_allowed=False, scope="INTERNAL_REVIEW"), f, indent=2)
        result = resolve_texas_internal_preview(
            package, case["address"], repo_root=RUNTIME, session=session,
            house_division_id=HOUSE, senate_division_id=SENATE, timeout_seconds=30)
        write(session.directory / "result.json", result)
        gps = result["geography"]
        payload = gps.get("payload", {})
        legislative = [a for a in payload.get("district_assignments", []) if a.get("adapter_id", "").startswith(("DIST-TX-HOUSE", "DIST-TX-SENATE"))]
        row = dict(case, status=result["status"], expected_status_met=result["status"] == case["expect"],
                   geocoder_requests=session.geocoder_calls, total_requests=len(session.calls),
                   error=result["representation"].get("error"), gps_error=gps.get("error"),
                   legislative_assignments=legislative, projections=len(result["representation"].get("projections", [])),
                   canonical_writes=result["canonical_writes"], publication_eligible=result["publication_eligible"],
                   source_unchanged=package == before and PACKAGE_PATH.read_bytes() == package_bytes)
        summary.append(row)
        write(ROOT / "address_control_summary.json", summary)
        print(json.dumps(row), flush=True)
    assert package == before and PACKAGE_PATH.read_bytes() == package_bytes


if __name__ == "__main__":
    main()
