#!/usr/bin/env python3
"""Prepare a one-shot merge execution request after EV-IMP-014.

This gate does not merge by itself. It requires an exact human authorization
string bound to PR number and head SHA, reruns EV-IMP-014 against fresh evidence,
and emits deterministic squash-merge metadata for the companion manual workflow.
"""
from __future__ import annotations

import argparse, hashlib, importlib.util, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ev_onboarding_merge_eligibility.py"
_spec = importlib.util.spec_from_file_location("ev_imp_014_for_execute", TOOL)
if _spec is None or _spec.loader is None:
    raise ImportError("unable to load EV-IMP-014")
eligibility = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eligibility)

class MergeExecutionError(ValueError): pass

def canonical(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"

def authorization_text(pr_number: int, head_sha: str) -> str:
    return f"AUTHORIZE MERGE PR #{pr_number} @ {head_sha.lower()}"

def build_request(repo_root: Path, package_id: str, reviewed_sha: str, head_sha: str,
                  authorization: str, evidence: dict[str, Any]) -> dict[str, Any]:
    decision = eligibility.evaluate(repo_root, package_id, reviewed_sha, head_sha, evidence)
    if decision.get("status") == "NOOP":
        return {"gate":"EV-IMP-015","status":"NOOP","merge_required":False,
                "merge_authorized":False,"publication_authorized":False,"canonical_writes":0}
    if decision.get("status") != "MERGE_ELIGIBLE":
        raise MergeExecutionError("EV-IMP-014 did not return MERGE_ELIGIBLE")
    pr = int(decision["pull_request_number"])
    head = str(decision["head_sha"]).lower()
    expected = authorization_text(pr, head)
    if authorization.strip() != expected:
        raise MergeExecutionError(f"explicit merge authorization mismatch; expected exactly: {expected}")
    req = {
        "gate":"EV-IMP-015","status":"AUTHORIZED_FOR_ONE_SQUASH_MERGE",
        "package_jurisdiction_id":package_id,"reviewed_bundle_sha256":decision["reviewed_bundle_sha256"],
        "pull_request_number":pr,"expected_head_sha":head,"merge_method":"squash",
        "authorization":expected,"merge_required":True,"merge_authorized":True,
        "auto_merge_authorized":False,"publication_authorized":False,"canonical_writes":0,
    }
    req["request_sha256"] = hashlib.sha256(canonical(req).encode()).hexdigest()
    return req

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path(".")); ap.add_argument("--package-jurisdiction-id",required=True)
    ap.add_argument("--reviewed-bundle-sha256",required=True); ap.add_argument("--expected-head-sha",required=True)
    ap.add_argument("--merge-authorization",required=True); ap.add_argument("--evidence",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); ev=json.loads(a.evidence.read_text())
    r=build_request(a.repo_root.resolve(),a.package_jurisdiction_id,a.reviewed_bundle_sha256,a.expected_head_sha,a.merge_authorization,ev)
    a.output.mkdir(parents=True,exist_ok=True); (a.output/"merge-request.json").write_text(canonical(r)); print(canonical(r).strip())
if __name__ == "__main__": main()
