#!/usr/bin/env python3
"""Prepare a held Maui release; execute only with separate, exact approval."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import ev_maui_publication_candidate as manifest

require, encoded, sha, load_json = manifest.require, manifest.encoded, manifest.sha, manifest.load_json
GATE = "EV-MAUI-RELEASE-EXECUTION-CANDIDATE-001"
REPOSITORY = manifest.REPOSITORY
BASE = "9e3e85a2a16cef0387b9f76cdcd7e01aaca5c419"
BASE_TREE = "a4079595d7f91a6e3f3631060601a388214aaae3"
CANDIDATE = Path("candidates/ev/maui_release_execution.v0.1")
CONTRACT = CANDIDATE / "contract.json"
APPROVAL = CANDIDATE / "approval.template.json"
RECHECK = CANDIDATE / "source-recheck.json"
NOTES = Path("docs/ev-maui-integration-release-notes-v0.1.md")
ARTIFACTS = Path("artifacts/ev-maui-release-execution")
ASSET_SHA = "eb577b26a899f5e03bb6450225438bcbebd0efb3b53993e14426eddb8506683a"
NOTES_SHA = "b49808473dd60f622f1b4ce219d350c10a43605d8bac9dc019e755e528001245"
RECHECK_SHA = "e4a8c8ed6aa7f7745daeebf2b522803757dd850e4d056bfcc660a2b06fab5139"
TITLE = "Maui countywide Mayor/Council integration v0.1"
RAILWAY_REF = "agent/day12-tx-post-activation-runtime-v0.2"
RAILWAY_SHA = "bf95d7e79c8cfc8be644326d0b0ea2c1065b0a67"
TEXAS_ID = 383744766
TEXAS_TARGET = "defefa6d31987187839fa90434b201a287518e34"
TEXAS_ASSET_SHA = "80bcb6f3d4d668ce62af84450b1db726156c0beaf7bc24b053b8c6291704cffe"
ALLOWED_PATHS = {str(CONTRACT), str(APPROVAL), str(RECHECK), str(NOTES),
    "tools/ev_maui_release_execution.py", "tests/ev_maui_release_execution_test.py",
    "docs/ev-maui-release-execution-candidate-001.md",
    ".github/workflows/ev-maui-release-execution-candidate.yml"}
MODIFIED_PATHS = {"tools/ev_maui_activation_diff.py", ".github/workflows/ev-maui-publication-candidate.yml"}
ALLOWED_PATHS |= MODIFIED_PATHS
PATH_STATUS = {p: "modified" if p in MODIFIED_PATHS else "added" for p in ALLOWED_PATHS}
KAUAI_ID = 387664986
KAUAI_TARGET = "a24dd03a9958ffe7bc7a5ba2d0808ef9d1d81eed"
KAUAI_ASSET_SHA = "7a40e104999c2bb891b5ecadb2dfefec511f1fcc783e122f7cd31402987f850f"
ASSERTIONS_SHA = "bb7d3c587e319d123e22dd6db6ac3987c88a83ed4a806c06b5785d9e90d1b810"
WORKFLOWS = {
    ".github/workflows/ev-maui-publication-candidate.yml",
    ".github/workflows/ev-maui-countywide-preview.yml",
    ".github/workflows/ev-kauai-adapter-candidate.yml",
    ".github/workflows/ev-kauai-production-activation.yml",
    ".github/workflows/ev-maui-release-execution-candidate.yml",
    ".github/workflows/ev-maui-adapter-candidate.yml",
    ".github/workflows/ev-maui-production-activation.yml",
    ".github/workflows/civic-gps-live-smoke.yml"}
PINS = {str(manifest.MANIFEST): ASSET_SHA, str(NOTES): NOTES_SHA, str(RECHECK): RECHECK_SHA,
    str(manifest.SCHEMA): "d0bc60a7606b1868e73b02f8236e68c94ceea2b2f4df397a0a331bbb18285468",
    str(manifest.RETENTION): "58a846500e41f66c042d229e8ba52f6350b26b7a939121add9196df76b0eaea2",
    str(manifest.EVIDENCE): "1b9bd935af167dbbb443f65a5d0e6ce5e69aa9165fa2f7d4cd0dacb2f65a61c6",
    "tools/ev_maui_publication_candidate.py": "2beed85502ef7851b77558a9877888538558ee2af3b1b20dffa81b3c3a0cd5eb"}


def contract():
    return {"schema": "maui-release-execution-contract/0.1", "gate": GATE,
        "status": "CANDIDATE_EXECUTION_HELD", "repository": REPOSITORY,
        "preparation_base": BASE, "preparation_base_tree": BASE_TREE,
        "certified_manifest_head": "33d1e2bd34804dc5e188d4e9b7db8be0002f937e",
        "integration_target": manifest.TARGET, "integration_target_tree": manifest.TARGET_TREE,
        "tag": manifest.TAG, "release_name": TITLE, "make_latest": "false", "prerelease": False,
        "asset": {"path": str(manifest.MANIFEST), "name": manifest.ASSET,
                  "content_type": "application/json", "bytes": 5596, "sha256": ASSET_SHA},
        "input_sha256": PINS, "allowed_changed_paths": sorted(ALLOWED_PATHS),
        "changed_path_status": PATH_STATUS,
        "required_candidate_workflows": sorted(WORKFLOWS),
        "execution_steps": ["PREFLIGHT", "CREATE_DRAFT", "UPLOAD_ONE_MANIFEST", "VERIFY_DRAFT_ASSET",
                            "CREATE_OR_VERIFY_EXACT_TAG", "RECHECK", "PUBLISH", "VERIFY_PUBLISHED_RELEASE"],
        "collision_policy": "FAIL_CLOSED_NO_OVERWRITE_DELETE_OR_AUTOMATIC_RETRY",
        "execution_authority": "SEPARATELY_APPROVED_MANUAL_MAIN_DISPATCH_AND_BOUND_RECEIPT",
        "approval_max_age_hours": 24, "source_recheck_max_age_hours": 24,
        "source_review_expires_on": "2026-10-12",
        "candidate_source_recheck_status": "PASS",
        "execution_blockers": ["SEPARATE_PUBLICATION_AUTHORIZATION_REQUIRED", "FRESH_APPROVAL_BOUND_SOURCE_RECHECK_REQUIRED_AT_EXECUTION"],
        "holds": {"merge_authorized": False, "publication_authorized": False, "deployment_authorized": False,
                  "canonical_writes": 0, "catalog_promotion": False, "kalawao_work": False},
        "external_boundaries": {"texas_release_id": TEXAS_ID, "texas_target": TEXAS_TARGET,
                                "texas_asset_sha256": TEXAS_ASSET_SHA,
                                "kauai_release_id": KAUAI_ID, "kauai_target": KAUAI_TARGET,
                                "kauai_asset_sha256": KAUAI_ASSET_SHA,
                                "railway_source_ref": RAILWAY_REF, "railway_source_sha": RAILWAY_SHA}}


def approval_template():
    return {"schema": "maui-release-execution-approval/0.1", "approved": False,
        "publication_authorized": False, "deployment_authorized": False, "canonical_writes": 0,
        "catalog_promotion": False, "kalawao_work": False, "repository": REPOSITORY,
        "tag": manifest.TAG, "target_commit": manifest.TARGET, "contract_sha256": sha(encoded(contract())),
        "asset_sha256": ASSET_SHA, "notes_sha256": NOTES_SHA,
        "expected_execution_head": None, "certified_candidate_head": None, "candidate_pr": None,
        "source_recheck_sha256": None, "approved_at_utc": None, "expires_at_utc": None,
        "approval_reference": None, "operation_id": None}


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    require(isinstance(value, str), "TIMESTAMP_REQUIRED")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.utcoffset() == timedelta(0), "TIMESTAMP_MUST_BE_UTC")
    return result


def validate_recheck(raw, now=None):
    """Validate operator evidence bindings, integrity and age; not an independent scraper."""
    now = now or utcnow()
    value = load_json(raw)
    require(value.get("schema") == "maui-release-source-recheck/0.1", "RECHECK_SCHEMA_INVALID")
    require(value.get("status") == "PASS" and value.get("blockers") == [] and
            all(value.get(k) is True for k in ("roster_matches_package", "leadership_matches_package",
                "scope_matches_package", "residency_matches_package", "selection_matches_package",
                "address_controls_match_receipt")), "COMPLETE_LIVE_SOURCE_RECHECK_REQUIRED")
    require(value.get("archive_sha256") == manifest.production.candidate.ARTIFACT["archive_sha256"]
            and value.get("package_sha256") == manifest.PACKAGE_SHA
            and value.get("source_review_expires_on") == "2026-10-12"
            and value.get("production_receipt_extended") is False
            and value.get("publication_authorized") is False, "RECHECK_SCOPE_DRIFT")
    checked = timestamp(value.get("checked_at_utc"))
    require(timedelta(0) <= now - checked <= timedelta(hours=24)
            and now < datetime(2026, 10, 12, tzinfo=timezone.utc), "RECHECK_EXPIRED_OR_FUTURE")
    sources = value.get("sources", [])
    require(isinstance(sources, list) and len(sources) == 13, "THIRTEEN_PRIMARY_SOURCES_REQUIRED")
    roles, source_ids = set(), set()
    for source in sources:
        for field in ("url", "final_url"):
            url = urlsplit(source.get(field, ""))
            require(url.scheme == "https" and url.hostname in {
                    "elections.hawaii.gov", "mauicounty.us", "www.mauicounty.us", "mauicounty.gov", "www.mauicounty.gov"}
                    and not url.username and not url.password and url.port in {None, 443}, "RECHECK_SOURCE_NOT_PRIMARY")
        require(source.get("authority") == "PRIMARY_OFFICIAL" and source.get("retrieval") == "DIRECT_FETCH"
                and source.get("http_status") == 200, "DIRECT_PRIMARY_EVIDENCE_REQUIRED")
        sid = source.get("source_id")
        require(isinstance(sid, str) and sid and sid not in source_ids, "SOURCE_ID_INVALID_OR_DUPLICATE")
        source_ids.add(sid)
        retrieved = timestamp(source.get("retrieved_at_utc"))
        require(retrieved <= checked and timedelta(0) <= now - retrieved <= timedelta(hours=24), "SOURCE_EXPIRED_OR_FUTURE")
        excerpts = source.get("raw_excerpts")
        require(isinstance(excerpts, list) and excerpts and all(isinstance(x, str) and x.strip() for x in excerpts)
                and source.get("raw_excerpts_sha256") == sha(encoded(excerpts))
                and re.fullmatch(r"[0-9a-f]{64}", source.get("response_sha256", "")) is not None,
                "SOURCE_EVIDENCE_INTEGRITY_DRIFT")
        require(isinstance(source.get("supports"), list) and all(isinstance(x, str) for x in source["supports"]),
                "SOURCE_SUPPORTS_INVALID")
        roles.update(source["supports"])
    require({"MAYOR_ROSTER", "COUNCIL_ROSTER", "COUNCIL_CHAIR", "COUNCIL_VICE_CHAIR", "COUNTYWIDE_SCOPE",
             "RESIDENCY_AREAS", "APPOINTED_SELECTION", "TERM_POLICY", "WAILUKU_ADDRESS", "LANAI_ADDRESS"} <= roles,
            "DIRECT_LEADERSHIP_AND_SCOPE_EVIDENCE_REQUIRED")
    assertions = value.get("normalized_assertions", [])
    require(isinstance(assertions, list) and len(assertions) == 25, "TWENTY_FIVE_ASSERTIONS_REQUIRED")
    ids = set()
    for assertion in assertions:
        aid, joined = assertion.get("assertion_id"), assertion.get("source_ids")
        require(isinstance(aid, str) and aid and aid not in ids, "ASSERTION_ID_INVALID_OR_DUPLICATE")
        ids.add(aid)
        require(isinstance(joined, list) and joined and all(isinstance(x, str) and x in source_ids for x in joined),
                "ASSERTION_SOURCE_JOIN_INVALID")
    payload = sorted([{k: v for k, v in a.items() if k not in {"assertion_id", "source_ids"}}
                      for a in assertions], key=encoded)
    require(sha(encoded(payload)) == ASSERTIONS_SHA, "NORMALIZED_BINDINGS_DRIFT")
    expected_qa = {"status": "PASS", "raw_count": 13, "normalized_count": 25, "holder_parity": 10,
        "residency_parity": 9, "leadership_parity": 2, "source_joins_valid": True,
        "parity_ok": True, "blocking_gap_count": 0}
    require(encoded(value.get("qa")) == encoded(expected_qa), "SOURCE_QA_PARITY_DRIFT")
    return value


def validate_approval(raw, source_raw, expected_head, now=None):
    now = now or utcnow()
    value = load_json(raw)
    require(isinstance(value, dict) and set(value) == set(approval_template()), "APPROVAL_SCHEMA_INVALID")
    expected = approval_template()
    for key in ("schema", "repository", "tag", "target_commit", "contract_sha256", "asset_sha256", "notes_sha256",
                "deployment_authorized", "canonical_writes", "catalog_promotion", "kalawao_work"):
        require(encoded(value[key]) == encoded(expected[key]), "APPROVAL_BINDING_DRIFT: " + key)
    require(value["approved"] is True and value["publication_authorized"] is True, "SEPARATE_PUBLICATION_APPROVAL_REQUIRED")
    require(re.fullmatch(r"[0-9a-f]{40}", expected_head or "") is not None
            and value["expected_execution_head"] == expected_head
            and re.fullmatch(r"[0-9a-f]{40}", value["certified_candidate_head"] or "") is not None,
            "APPROVED_HEAD_REQUIRED")
    require(type(value["candidate_pr"]) is int and value["candidate_pr"] > 66, "CANDIDATE_PR_REQUIRED")
    require(isinstance(value["approval_reference"], str) and 1 <= len(value["approval_reference"]) <= 500
            and all(ord(c) >= 32 for c in value["approval_reference"]), "APPROVAL_REFERENCE_REQUIRED")
    require(re.fullmatch(r"[A-Za-z0-9_-]{8,80}", value["operation_id"] or "") is not None, "OPERATION_ID_REQUIRED")
    approved, expires = timestamp(value["approved_at_utc"]), timestamp(value["expires_at_utc"])
    require(approved <= now < expires and timedelta(0) < expires - approved <= timedelta(hours=24), "APPROVAL_EXPIRED_OR_FUTURE")
    require(value["source_recheck_sha256"] == sha(source_raw), "APPROVED_RECHECK_HASH_DRIFT")
    validate_recheck(source_raw, now)
    return value


def verify_local(root, today=None):
    receipt = manifest.verify_inputs(root, today)
    for path, digest in PINS.items():
        require(sha((root / path).read_bytes()) == digest, "PINNED_INPUT_DRIFT: " + path)
    raw = (root / manifest.MANIFEST).read_bytes()
    require(len(raw) == 5596, "MANIFEST_SIZE_DRIFT")
    manifest.validate_manifest(load_json(raw), receipt, today)
    require((root / CONTRACT).read_bytes() == encoded(contract()), "EXECUTION_CONTRACT_DRIFT")
    require((root / APPROVAL).read_bytes() == encoded(approval_template()), "UNAPPROVED_TEMPLATE_DRIFT")
    review_raw = (root / RECHECK).read_bytes()
    # Candidate evidence is historical; execution requires freshness at the actual clock.
    validate_recheck(review_raw, timestamp(load_json(review_raw)["checked_at_utc"]))
    return raw


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def verify_checkout(root, head):
    require(re.fullmatch(r"[0-9a-f]{40}", head or "") is not None, "HEAD_REQUIRED")
    require(git(root, "rev-parse", "HEAD") == head, "CHECKOUT_HEAD_DRIFT")
    require(not git(root, "status", "--porcelain", "--untracked-files=no"), "TRACKED_WORKTREE_DIRTY")


def verify_git(root, head, base):
    require(base == BASE, "CANDIDATE_BASE_DRIFT")
    verify_checkout(root, head)
    require(git(root, "rev-parse", BASE + "^{tree}") == BASE_TREE, "BASE_TREE_DRIFT")
    changed = git(root, "diff", "--no-renames", "--name-status", BASE, head).splitlines()
    require(len(changed) == 10 and set(changed) == {
        ("M\t" if path in MODIFIED_PATHS else "A\t") + path for path in ALLOWED_PATHS}, "EXACT_TEN_PATHS_REQUIRED")
    return {"head": head, "base": base, "changed_path_status": PATH_STATUS, "status": "PASS"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    """Fixed repository, no retries; authenticated redirects are never followed."""
    def __init__(self, token):
        require(bool(token), "GITHUB_TOKEN_REQUIRED")
        self.token, self.allow_writes = token, False
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, data=None, *, binary=False):
        require(method in {"GET", "POST", "PATCH"}, "UNSUPPORTED_API_METHOD")
        require(method == "GET" or self.allow_writes, "API_WRITES_HELD")
        require(not path.startswith("/") and ".." not in path and "://" not in path, "API_PATH_INVALID")
        host = "uploads.github.com" if method == "POST" and binary else "api.github.com"
        url = "https://" + host + "/repos/" + REPOSITORY + "/" + path
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/octet-stream" if binary and method == "GET"
                   else "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        body = data if binary else (encoded(data) if data is not None else None)
        try:
            with self.opener.open(Request(url, data=body, headers=headers, method=method), timeout=30) as response:
                raw = response.read(1048577)
        except HTTPError as exc:
            if binary and method == "GET" and exc.code == 302:
                location = exc.headers.get("Location", "")
                parsed = urlsplit(location)
                require(parsed.scheme == "https" and (parsed.hostname or "").endswith(".githubusercontent.com")
                        and not parsed.username and not parsed.password and parsed.port in {None, 443}, "ASSET_REDIRECT_REJECTED")
                # Use a new unauthenticated request: never send the GitHub credential to asset storage.
                with self.opener.open(Request(location), timeout=30) as response:
                    raw = response.read(1048577)
            else:
                raise ValueError("GITHUB_HTTP_" + str(exc.code)) from None
        require(len(raw) <= 1048576, "API_RESPONSE_TOO_LARGE")
        return raw if binary and method == "GET" else load_json(raw)

    def get(self, path):
        return self.request("GET", path)

    def pages(self, path, key=None):
        rows = []
        for page in range(1, 101):
            result = self.get(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            batch = result[key] if key else result
            require(isinstance(batch, list), "API_INVENTORY_INVALID")
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise ValueError("API_PAGINATION_INCOMPLETE")


def boundaries(api):
    release = api.get(f"releases/{TEXAS_ID}")
    assets = api.pages(f"releases/{TEXAS_ID}/assets")
    require(api.get("releases/latest")["id"] == TEXAS_ID, "LATEST_RELEASE_BOUNDARY_DRIFT")
    require(release["id"] == TEXAS_ID and release["target_commitish"] == TEXAS_TARGET
            and release["tag_name"] == "tx-legislative-two-office-v0.1" and release["draft"] is False
            and len(assets) == 1, "TEXAS_RELEASE_BOUNDARY_DRIFT")
    asset = assets[0]
    require(asset["id"] == 547794640 and asset["size"] == 1766
            and asset["digest"] == "sha256:" + TEXAS_ASSET_SHA, "TEXAS_ASSET_BOUNDARY_DRIFT")
    kauai = api.get(f"releases/{KAUAI_ID}")
    kauai_assets = api.pages(f"releases/{KAUAI_ID}/assets")
    require(kauai["id"] == KAUAI_ID and kauai["target_commitish"] == KAUAI_TARGET
            and kauai["tag_name"] == "kauai-mayor-council-integration-v0.1" and kauai["draft"] is False
            and len(kauai_assets) == 1, "KAUAI_RELEASE_BOUNDARY_DRIFT")
    ka = kauai_assets[0]
    require(ka["id"] == 559746136 and ka["size"] == 4593
            and ka["name"] == "kauai-mayor-council-integration-manifest-v0.1.json"
            and ka["digest"] == "sha256:" + KAUAI_ASSET_SHA, "KAUAI_ASSET_BOUNDARY_DRIFT")
    require(api.get("git/ref/heads/" + RAILWAY_REF)["object"]["sha"] == RAILWAY_SHA, "RAILWAY_SOURCE_PIN_DRIFT")
    return {"texas_release_id": TEXAS_ID, "texas_asset_sha256": TEXAS_ASSET_SHA,
            "kauai_release_id": KAUAI_ID, "kauai_asset_sha256": KAUAI_ASSET_SHA,
            "railway_source_sha": RAILWAY_SHA, "railway_live_deployment_checked": False}


def destination(api):
    target = api.get("git/commits/" + manifest.TARGET)
    require(target["sha"] == manifest.TARGET and target["tree"]["sha"] == manifest.TARGET_TREE, "RELEASE_TARGET_DRIFT")
    refs = api.get("git/matching-refs/tags/" + manifest.TAG)
    require(not any(x["ref"] == "refs/tags/" + manifest.TAG for x in refs)
            and not any(x["tag_name"] == manifest.TAG for x in api.pages("releases")), "TAG_OR_RELEASE_COLLISION")
    return boundaries(api)


def context(api, approval):
    head, certified = approval["expected_execution_head"], approval["certified_candidate_head"]
    require(api.get("git/ref/heads/main")["object"]["sha"] == head, "MAIN_HEAD_DRIFT")
    pr = api.get("pulls/" + str(approval["candidate_pr"]))
    require(pr["merged"] is True and pr["state"] == "closed" and pr["draft"] is False
            and pr["base"]["ref"] == "main" and pr["base"]["sha"] == BASE
            and pr["head"]["sha"] == certified and pr["merge_commit_sha"] == head
            and pr["head"]["repo"]["full_name"] == REPOSITORY, "APPROVED_MERGED_CANDIDATE_REQUIRED")
    files = api.pages("pulls/" + str(approval["candidate_pr"]) + "/files")
    require(len(files) == 10 and {x["filename"] for x in files} == ALLOWED_PATHS
            and all(x["status"] == PATH_STATUS[x["filename"]] for x in files), "CANDIDATE_DIFF_DRIFT")
    merged = api.get("git/commits/" + head)
    original = api.get("git/commits/" + certified)
    require(merged["tree"]["sha"] == original["tree"]["sha"]
            and [x["sha"] for x in merged["parents"]] == [BASE], "CERTIFIED_TREE_OR_SQUASH_PARENT_DRIFT")
    runs = api.pages("actions/runs?event=pull_request&head_sha=" + certified, "workflow_runs")
    latest = {}
    for run in sorted(runs, key=lambda x: x["id"]):
        if run["head_sha"] == certified and run["event"] == "pull_request":
            latest[run["path"]] = run
    require(WORKFLOWS <= set(latest) and all(r["status"] == "completed" and r["conclusion"] == "success"
            for r in latest.values()), "EXACT_CANDIDATE_CI_REQUIRED")
    return {"head": head, "certified_head": certified,
            "workflow_runs": sorted(r["id"] for r in latest.values())}


def release_body(root, approval):
    return (root / NOTES).read_text() + "\nExecution references:\n" + "\n".join(
        "- " + key + ": `" + str(approval[key]) + "`" for key in (
            "operation_id", "expected_execution_head", "certified_candidate_head", "candidate_pr",
            "contract_sha256", "source_recheck_sha256", "approval_reference")) + "\n"


def verify_metadata(api, release_id, body, draft):
    release = api.get("releases/" + str(release_id))
    require(release["id"] == release_id and release["tag_name"] == manifest.TAG
            and release["target_commitish"] == manifest.TARGET and release["name"] == TITLE
            and release["body"] == body and release["draft"] is draft and release["prerelease"] is False,
            "RELEASE_METADATA_DRIFT")


def verify_release(api, release_id, body, draft):
    verify_metadata(api, release_id, body, draft)
    assets = api.pages(f"releases/{release_id}/assets")
    require(len(assets) == 1, "EXACTLY_ONE_RELEASE_ASSET_REQUIRED")
    asset = assets[0]
    require(asset["name"] == manifest.ASSET and asset["size"] == 5596 and asset["state"] == "uploaded"
            and asset["content_type"] == "application/json"
            and asset["digest"] == "sha256:" + ASSET_SHA, "UPLOADED_ASSET_METADATA_DRIFT")
    raw = api.request("GET", "releases/assets/" + str(asset["id"]), binary=True)
    require(len(raw) == 5596 and sha(raw) == ASSET_SHA, "UPLOADED_ASSET_BYTES_DRIFT")
    return asset["id"]


def verify_tag(api):
    refs = api.get("git/matching-refs/tags/" + manifest.TAG)
    exact = [x for x in refs if x["ref"] == "refs/tags/" + manifest.TAG]
    require(len(exact) == 1 and exact[0]["object"]["type"] == "commit"
            and exact[0]["object"]["sha"] == manifest.TARGET, "EXACT_LIGHTWEIGHT_TAG_REQUIRED")


class ExecutionFailure(ValueError):
    def __init__(self, receipt):
        super().__init__(receipt["error"])
        self.receipt = receipt


def execute(root, api, approval_raw, source_raw, expected_head, now=None):
    # Validation precedes even a read request, and the real client's mutation switch stays off.
    approval = validate_approval(approval_raw, source_raw, expected_head, now)
    raw = verify_local(root, (now or utcnow()).date())
    body = release_body(root, approval)
    receipt = {"gate": GATE, "status": "EXECUTION_STARTED", "phase": "PREFLIGHT",
        "operation_id": approval["operation_id"], "approval": approval, "release_id": None, "asset_id": None,
        "manifest_sha256": ASSET_SHA, "canonical_writes": 0, "catalog_promotion": False,
        "deployment_authorized": False, "kalawao_work": False, "completed_phases": []}
    try:
        receipt["context"] = context(api, approval)
        receipt["boundaries_before"] = destination(api)
        receipt["completed_phases"].append("PREFLIGHT")
        api.allow_writes = True
        receipt["phase"] = "CREATE_DRAFT"
        release = api.request("POST", "releases", {"tag_name": manifest.TAG, "target_commitish": manifest.TARGET,
            "name": TITLE, "body": body, "draft": True, "prerelease": False, "make_latest": "false"})
        receipt["release_id"] = release["id"]
        verify_metadata(api, release["id"], body, True)
        require(api.pages(f"releases/{release['id']}/assets") == [], "NEW_DRAFT_MUST_HAVE_NO_ASSETS")
        receipt["completed_phases"].append(receipt["phase"])
        receipt["phase"] = "UPLOAD_ONE_MANIFEST"
        asset = api.request("POST", f"releases/{release['id']}/assets?name=" + quote(manifest.ASSET), raw, binary=True)
        receipt["asset_id"] = asset["id"]
        receipt["completed_phases"].append(receipt["phase"])
        receipt["phase"] = "VERIFY_DRAFT_ASSET"
        require(verify_release(api, release["id"], body, True) == asset["id"], "ASSET_ID_DRIFT")
        receipt["completed_phases"].append(receipt["phase"])
        receipt["phase"] = "CREATE_OR_VERIFY_EXACT_TAG"
        refs = api.get("git/matching-refs/tags/" + manifest.TAG)
        if not any(x["ref"] == "refs/tags/" + manifest.TAG for x in refs):
            api.request("POST", "git/refs", {"ref": "refs/tags/" + manifest.TAG, "sha": manifest.TARGET})
        verify_tag(api)
        receipt["completed_phases"].append(receipt["phase"])
        receipt["phase"] = "RECHECK"
        validate_approval(approval_raw, source_raw, expected_head, now)
        verify_local(root, (now or utcnow()).date())
        context(api, approval)
        require(boundaries(api) == receipt["boundaries_before"], "EXTERNAL_BOUNDARY_DRIFT")
        require(verify_release(api, release["id"], body, True) == asset["id"], "ASSET_ID_DRIFT")
        verify_tag(api)
        receipt["completed_phases"].append(receipt["phase"])
        receipt["phase"] = "PUBLISH"
        api.request("PATCH", "releases/" + str(release["id"]), {"draft": False, "make_latest": "false"})
        receipt["completed_phases"].append(receipt["phase"])
        receipt["phase"] = "VERIFY_PUBLISHED_RELEASE"
        require(verify_release(api, release["id"], body, False) == asset["id"], "ASSET_ID_DRIFT")
        verify_tag(api)
        receipt["boundaries_after"] = boundaries(api)
        require(receipt["boundaries_after"] == receipt["boundaries_before"], "EXTERNAL_BOUNDARY_DRIFT")
        receipt["completed_phases"].append(receipt["phase"])
        receipt.update(status="PASS", finished_at_utc=(now or utcnow()).isoformat(), publication_completed=True)
        return receipt
    except Exception as exc:
        # HTTP/network errors may follow a successful write. Never infer rollback or retry.
        receipt.update(status="FAIL_CLOSED_RECONCILIATION_REQUIRED", publication_completed=None,
                       error=str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
                       automatic_retry=False, automatic_cleanup=False)
        raise ExecutionFailure(receipt) from None
    finally:
        api.allow_writes = False


def prepare_output(root, output):
    root, output = root.resolve(), output.absolute()
    allowed = root / ARTIFACTS
    require(output != allowed and output.is_relative_to(allowed), "OUTPUT_OUTSIDE_ARTIFACT_DIRECTORY")
    require(all(not p.is_symlink() for p in [output, *output.parents] if p.is_relative_to(root)), "OUTPUT_SYMLINK_REJECTED")
    require(output.resolve() == output and not output.exists(), "OUTPUT_COLLISION_OR_TRAVERSAL")
    output.mkdir(parents=True, exist_ok=False)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--head")
    parser.add_argument("--base")
    parser.add_argument("--read-destination", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--source-recheck", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    raw = verify_local(root)
    require(bool(args.head) == bool(args.base) or (args.execute and args.head and not args.base), "HEAD_BASE_ARGUMENTS_INVALID")
    verification = verify_git(root, args.head, args.base) if args.head and args.base else None
    api = None
    if args.execute:
        require(args.approval is not None and args.source_recheck is not None and args.head, "EXECUTION_INPUTS_REQUIRED")
        approval_raw, source_raw = args.approval.read_bytes(), args.source_recheck.read_bytes()
        validate_approval(approval_raw, source_raw, args.head)
        verify_checkout(root, args.head)
    else:
        require(args.approval is None and args.source_recheck is None, "APPROVAL_INPUTS_REQUIRE_EXPLICIT_EXECUTION")
    output = prepare_output(root, args.output_dir)
    if args.execute or args.read_destination:
        api = GitHub(os.environ.get("GH_TOKEN"))
    if args.execute:
        try:
            report = execute(root, api, approval_raw, source_raw, args.head)
        except ExecutionFailure as exc:
            (output / "execution-receipt.json").write_bytes(encoded(exc.receipt))
            print(json.dumps({"status": exc.receipt["status"], "phase": exc.receipt["phase"], "error": str(exc)}))
            raise SystemExit(1)
        (output / "execution-receipt.json").write_bytes(encoded(report))
    else:
        report = {"gate": GATE, "status": "PASS", "execution_status": "HELD", "git_verification": verification,
            "contract_sha256": sha(encoded(contract())), "manifest_sha256": ASSET_SHA, "manifest_bytes": len(raw),
            "release_asset_count": 1, "source_recheck_status": "PASS", "source_review_expires_on": "2026-10-12",
            "blockers": contract()["execution_blockers"], "publication_authorized": False, "deployment_authorized": False,
            "canonical_writes": 0, "remote_writes": 0,
            "destination_read": destination(api) if api else "NOT_REQUESTED",
            "destination_visibility": "TOKEN_VISIBLE_ONLY; EXECUTION_REPEATS_WITH_WRITE_CAPABILITY"}
        assets = output / "release-assets"
        assets.mkdir()
        (assets / manifest.ASSET).write_bytes(raw)
        (output / "verification.json").write_bytes(encoded(report))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
