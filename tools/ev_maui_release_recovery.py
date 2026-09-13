#!/usr/bin/env python3
"""Reconcile and finish only Maui draft 388004869; never recreate release objects."""
from __future__ import annotations
import argparse
import json
from datetime import timedelta
import os
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from tools import ev_maui_release_execution as original

require,encoded,sha,load_json=original.require,original.encoded,original.sha,original.load_json
GATE="EV-MAUI-RELEASE-RECOVERY-001"
BASE="6260d0c6da3971f2e13309e3746c51cc02044543"
BASE_TREE="78975d979409484ee4f6318d17a6c6e0436154f6"
ORIGINAL_CERTIFIED="d9c3878f558c571eeed87661653a1416ac4d9e2b"
DIRECTORY=Path("recovery/ev/maui_publication.v0.1")
CONTRACT=DIRECTORY/"contract.json"
APPROVAL=DIRECTORY/"approval.template.json"
FAILURE=DIRECTORY/"failed-execution-receipt.json"
FAILURE_SHA="c997dd25cb7d5348f4ffe480590181b1016c46173fae34d34743765782204601"
RELEASE_ID,ASSET_ID=388004869,561768290
FAILED_RUN,FAILED_JOB=34776975180,103776766384
ARTIFACTS=Path("artifacts/ev-maui-release-recovery")
PATHS={str(CONTRACT),str(APPROVAL),str(FAILURE),"tools/ev_maui_release_recovery.py",
 "tests/ev_maui_release_recovery_test.py",".github/workflows/ev-maui-release-recovery.yml",
 "docs/ev-maui-release-recovery-001.md"}
WORKFLOWS={".github/workflows/ev-maui-release-recovery.yml",
 ".github/workflows/ev-maui-adapter-candidate.yml",".github/workflows/ev-maui-production-activation.yml",
 ".github/workflows/ev-maui-countywide-preview.yml",".github/workflows/ev-kauai-adapter-candidate.yml",
 ".github/workflows/ev-kauai-production-activation.yml",".github/workflows/civic-gps-live-smoke.yml"}
PINS={str(FAILURE):FAILURE_SHA,
 "tools/ev_maui_release_execution.py":"0e7553258458f053ce404b819d6e42192676d47cc970d73fc51418e9faedb13f",
 ".github/workflows/ev-maui-release-execution-candidate.yml":"b399ec5ac35e25a14bf25e7f8881674007c36e8669af49e0033acd6ed7aa759a"}

def contract():
 return {"schema":"maui-release-recovery-contract/0.1","gate":GATE,"status":"RECOVERY_CANDIDATE_HELD",
  "repository":original.REPOSITORY,"base":BASE,"base_tree":BASE_TREE,"allowed_added_paths":sorted(PATHS),
  "required_workflows":sorted(WORKFLOWS),"pinned_inputs":PINS,
  "original_certified_head":ORIGINAL_CERTIFIED,"original_pr":67,
  "failed_run":FAILED_RUN,"failed_job":FAILED_JOB,"failure_artifact_id":10323877402,
  "failure_artifact_sha256":"f84a9546af7ee67a7671e78b671ddf9800471a6fb83ac1c7cf96e907d797bb71",
  "release_id":RELEASE_ID,"asset_id":ASSET_ID,"tag":original.manifest.TAG,
  "integration_target":original.manifest.TARGET,"asset_sha256":original.ASSET_SHA,"asset_bytes":5596,
  "only_mutation":{"method":"PATCH","path":f"releases/{RELEASE_ID}","data":{"draft":False,"make_latest":"false"}},
  "creates":0,"uploads":0,"tag_writes":0,"deletes":0,"automatic_retry":False,"automatic_cleanup":False,
  "published_readback_attempts":3,"readback_wait_seconds":1,
  "source_recheck_max_age_hours":24,"approval_max_age_hours":24,
  "source_review_expires_on":"2026-10-12","original_authorization":"RETAINED_HISTORICAL_RECEIPT",
  "execution_authority":"CURRENT_APPROVAL_BOUND_MANUAL_MAIN_DISPATCH",
  "holds":{"publication_authorized":False,"deployment_authorized":False,
           "canonical_writes":0,"catalog_promotion":False,"kalawao_work":False}}

def approval_template():
 return {"schema":"maui-release-recovery-approval/0.1","approved":False,"publication_authorized":False,
  "repository":original.REPOSITORY,"release_id":RELEASE_ID,"asset_id":ASSET_ID,
  "tag":original.manifest.TAG,"target_commit":original.manifest.TARGET,"asset_sha256":original.ASSET_SHA,
  "contract_sha256":sha(encoded(contract())),"failure_receipt_sha256":FAILURE_SHA,
  "deployment_authorized":False,"canonical_writes":0,"catalog_promotion":False,"kalawao_work":False,
  "expected_execution_head":None,"certified_candidate_head":None,"candidate_pr":None,
  "source_recheck_sha256":None,"approved_at_utc":None,"expires_at_utc":None,
  "approval_reference":None,"operation_id":None}

def validate_approval(raw,source,head,now=None):
 now=now or original.utcnow();value=load_json(raw);expected=approval_template()
 require(isinstance(value,dict) and set(value)==set(expected),"RECOVERY_APPROVAL_SCHEMA_INVALID")
 dynamic={"approved","publication_authorized","expected_execution_head","certified_candidate_head","candidate_pr",
          "source_recheck_sha256","approved_at_utc","expires_at_utc","approval_reference","operation_id"}
 for key in set(expected)-dynamic:
  require(encoded(value[key])==encoded(expected[key]),"RECOVERY_APPROVAL_BINDING_DRIFT: "+key)
 require(value["approved"] is True and value["publication_authorized"] is True,"RECOVERY_APPROVAL_REQUIRED")
 require(re.fullmatch(r"[0-9a-f]{40}",head or "") is not None and value["expected_execution_head"]==head
         and re.fullmatch(r"[0-9a-f]{40}",value["certified_candidate_head"] or "") is not None,
         "RECOVERY_APPROVED_HEAD_REQUIRED")
 require(type(value["candidate_pr"]) is int and value["candidate_pr"]>67,"RECOVERY_PR_REQUIRED")
 require(isinstance(value["approval_reference"],str) and 1<=len(value["approval_reference"])<=500
         and all(ord(x)>=32 for x in value["approval_reference"]),"APPROVAL_REFERENCE_REQUIRED")
 require(re.fullmatch(r"[A-Za-z0-9_-]{8,80}",value["operation_id"] or "") is not None,"OPERATION_ID_REQUIRED")
 start,end=original.timestamp(value["approved_at_utc"]),original.timestamp(value["expires_at_utc"])
 require(start<=now<end and timedelta(0)<end-start<=timedelta(hours=24),"APPROVAL_EXPIRED_OR_FUTURE")
 require(value["source_recheck_sha256"]==sha(source),"APPROVED_RECHECK_HASH_DRIFT")
 original.validate_recheck(source,now)
 return value

def verify_local(root,today=None):
 raw=original.verify_local(root,today)
 for path,digest in PINS.items():require(sha((root/path).read_bytes())==digest,"RECOVERY_PIN_DRIFT: "+path)
 require((root/CONTRACT).read_bytes()==encoded(contract()),"RECOVERY_CONTRACT_DRIFT")
 require((root/APPROVAL).read_bytes()==encoded(approval_template()),"RECOVERY_TEMPLATE_DRIFT")
 receipt=load_json((root/FAILURE).read_bytes())
 require(receipt["release_id"]==RELEASE_ID and receipt["asset_id"]==ASSET_ID
         and receipt["phase"]=="CREATE_OR_VERIFY_EXACT_TAG"
         and receipt["completed_phases"]==["PREFLIGHT","CREATE_DRAFT","UPLOAD_ONE_MANIFEST","VERIFY_DRAFT_ASSET"]
         and receipt["error"]=="EXACT_LIGHTWEIGHT_TAG_REQUIRED" and receipt["publication_completed"] is None,
         "RECONCILED_FAILURE_REQUIRED")
 # The retained authorization is historical. Actual execution needs a current recovery approval.
 a=receipt["approval"]
 source=json.dumps(load_json((root/original.RECHECK).read_bytes()),
  ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")
 original.validate_approval(encoded(a),source,BASE,original.timestamp(a["approved_at_utc"]))
 return raw,receipt

def verify_git(root,head,base):
 require(base==BASE,"RECOVERY_BASE_DRIFT");original.verify_checkout(root,head)
 require(original.git(root,"rev-parse",BASE+"^{tree}")==BASE_TREE,"RECOVERY_BASE_TREE_DRIFT")
 rows=original.git(root,"diff","--no-renames","--name-status",BASE,head).splitlines()
 require(len(rows)==7 and set(rows)=={"A\t"+p for p in PATHS},"EXACT_SEVEN_RECOVERY_ADDITIONS_REQUIRED")
 return {"status":"PASS","head":head,"base":base,"added_paths":sorted(PATHS)}

def verify_pr(api,number,merged,certified,base,statuses,workflows):
 pr=api.get("pulls/"+str(number))
 require(pr["merged"] is True and pr["state"]=="closed" and pr["draft"] is False
  and pr["base"]["ref"]=="main" and pr["base"]["sha"]==base and pr["head"]["sha"]==certified
  and pr["merge_commit_sha"]==merged and pr["head"]["repo"]["full_name"]==original.REPOSITORY,
  "CERTIFIED_MERGED_PR_REQUIRED")
 files=api.pages("pulls/"+str(number)+"/files")
 require(len(files)==len(statuses) and {x["filename"] for x in files}==set(statuses)
         and all(x["status"]==statuses[x["filename"]] for x in files),"CERTIFIED_PR_SCOPE_DRIFT")
 left,right=api.get("git/commits/"+merged),api.get("git/commits/"+certified)
 require(left["tree"]["sha"]==right["tree"]["sha"] and [x["sha"] for x in left["parents"]]==[base],
         "CERTIFIED_TREE_OR_PARENT_DRIFT")
 runs=api.pages("actions/runs?event=pull_request&head_sha="+certified,"workflow_runs")
 latest={}
 for run in sorted(runs,key=lambda x:x["id"]):
  if run["head_sha"]==certified and run["event"]=="pull_request":latest[run["path"]]=run
 require(workflows<=set(latest) and all(x["status"]=="completed" and x["conclusion"]=="success"
         for x in latest.values()),"EXACT_CERTIFIED_CI_REQUIRED")
 return sorted(x["id"] for x in latest.values())

def context(api,a):
 run=api.get("actions/runs/"+str(FAILED_RUN))
 require(run["head_sha"]==BASE and run["event"]=="workflow_dispatch" and run["status"]=="completed"
  and run["conclusion"]=="failure" and run["run_attempt"]==1
  and run["path"]==".github/workflows/ev-maui-release-execution-candidate.yml","FAILED_RUN_PROVENANCE_DRIFT")
 require(api.get("git/ref/heads/main")["object"]["sha"]==a["expected_execution_head"],"MAIN_HEAD_DRIFT")
 original_runs=verify_pr(api,67,BASE,ORIGINAL_CERTIFIED,original.BASE,original.PATH_STATUS,original.WORKFLOWS)
 recovery_runs=verify_pr(api,a["candidate_pr"],a["expected_execution_head"],a["certified_candidate_head"],
                        BASE,{p:"added" for p in PATHS},WORKFLOWS)
 require(api.get("git/commits/"+BASE)["tree"]["sha"]==BASE_TREE,"ORIGINAL_MERGE_TREE_DRIFT")
 return {"original_runs":original_runs,"recovery_runs":recovery_runs,"head":a["expected_execution_head"]}

def verify_existing(api,root,receipt,draft):
 # Exact-ref lookup avoids reusing the pre-creation matching-refs inventory.
 tag=api.get("git/ref/tags/"+original.manifest.TAG)
 require(tag["ref"]=="refs/tags/"+original.manifest.TAG and tag["object"]["type"]=="commit"
         and tag["object"]["sha"]==original.manifest.TARGET,"EXACT_EXISTING_TAG_REQUIRED")
 matches=[r for r in api.pages("releases") if r["tag_name"]==original.manifest.TAG]
 require(len(matches)==1 and matches[0]["id"]==RELEASE_ID,"EXACT_EXISTING_RELEASE_REQUIRED")
 asset=original.verify_release(api,RELEASE_ID,original.release_body(root,receipt["approval"]),draft)
 require(asset==ASSET_ID,"EXISTING_ASSET_ID_DRIFT")

def verify_published(api,root,receipt):
 # Only reads repeat. A write is never retried, even after an ambiguous response.
 for attempt in range(3):
  try:
   verify_existing(api,root,receipt,False)
   return
  except ValueError:
   if attempt==2:raise
   time.sleep(1)

class RecoveryGitHub(original.GitHub):
 """Only one existing-release PATCH is allowed; POST and DELETE are never supported."""
 def request(self,method,path,data=None,*,binary=False):
  require(method=="GET" or (method=="PATCH" and path==f"releases/{RELEASE_ID}" and not binary
          and encoded(data)==encoded({"draft":False,"make_latest":"false"})),"RECOVERY_MUTATION_REJECTED")
  return super().request(method,path,data,binary=binary)

def execute(root,api,approval_raw,source,head,now=None):
 a=validate_approval(approval_raw,source,head,now)
 _,failure=verify_local(root,(now or original.utcnow()).date())
 result={"gate":GATE,"status":"RECOVERY_STARTED","phase":"PREFLIGHT","release_id":RELEASE_ID,
  "asset_id":ASSET_ID,"operation_id":a["operation_id"],"approval":a,"failure_receipt_sha256":FAILURE_SHA,
  "manifest_sha256":original.ASSET_SHA,"publication_completed":None,"completed_phases":[],
  "creates":0,"uploads":0,"tag_writes":0,"deletes":0,"automatic_retry":False,"automatic_cleanup":False,
  "published_readback_attempts":3,"readback_wait_seconds":1,
  "canonical_writes":0,"catalog_promotion":False,"deployment_authorized":False,"kalawao_work":False}
 try:
  result["context"]=context(api,a)
  result["boundaries_before"]=original.boundaries(api)
  require(result["boundaries_before"]==failure["boundaries_before"],"ORIGINAL_BOUNDARY_DRIFT")
  verify_existing(api,root,failure,True)
  result["completed_phases"].append("PREFLIGHT")
  result["phase"]="RECHECK"
  validate_approval(approval_raw,source,head,now);verify_local(root,(now or original.utcnow()).date())
  context(api,a);verify_existing(api,root,failure,True)
  require(original.boundaries(api)==result["boundaries_before"],"EXTERNAL_BOUNDARY_DRIFT")
  result["completed_phases"].append("RECHECK")
  result["phase"]="PUBLISH_EXISTING_DRAFT"
  api.allow_writes=True
  api.request("PATCH",f"releases/{RELEASE_ID}",{"draft":False,"make_latest":"false"})
  api.allow_writes=False
  result["completed_phases"].append("PUBLISH_EXISTING_DRAFT")
  result["phase"]="VERIFY_PUBLISHED_RELEASE"
  verify_published(api,root,failure)
  result["boundaries_after"]=original.boundaries(api)
  require(result["boundaries_after"]==result["boundaries_before"],"EXTERNAL_BOUNDARY_DRIFT")
  result["completed_phases"].append("VERIFY_PUBLISHED_RELEASE")
  result.update(status="PASS",publication_completed=True,finished_at_utc=(now or original.utcnow()).isoformat())
  return result
 except Exception as exc:
  result.update(status="FAIL_CLOSED_RECONCILIATION_REQUIRED",
                error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
  raise original.ExecutionFailure(result) from None
 finally:api.allow_writes=False

def output_directory(root,output):
 root,output=root.resolve(),output.absolute();allowed=root/ARTIFACTS
 require(output!=allowed and output.is_relative_to(allowed),"OUTPUT_OUTSIDE_RECOVERY_ARTIFACTS")
 require(all(not p.is_symlink() for p in [output,*output.parents] if p.is_relative_to(root)),
         "OUTPUT_SYMLINK_REJECTED")
 require(output.resolve()==output and not output.exists(),"OUTPUT_COLLISION_OR_TRAVERSAL")
 output.mkdir(parents=True,exist_ok=False);return output

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--repo-root",type=Path,default=ROOT);parser.add_argument("--output-dir",type=Path,required=True)
 parser.add_argument("--head");parser.add_argument("--base");parser.add_argument("--execute",action="store_true")
 parser.add_argument("--approval",type=Path);parser.add_argument("--source-recheck",type=Path)
 args=parser.parse_args();root=args.repo_root.resolve()
 raw,_=verify_local(root)
 require(bool(args.head)==bool(args.base) or (args.execute and args.head and not args.base),"HEAD_BASE_ARGUMENTS_INVALID")
 git_result=verify_git(root,args.head,args.base) if args.head and args.base else None
 if args.execute:
  require(args.head and args.approval and args.source_recheck,"RECOVERY_EXECUTION_INPUTS_REQUIRED")
  a,source=args.approval.read_bytes(),args.source_recheck.read_bytes()
  validate_approval(a,source,args.head);original.verify_checkout(root,args.head)
 else:require(args.approval is None and args.source_recheck is None,"APPROVAL_INPUTS_REQUIRE_EXECUTION")
 output=output_directory(root,args.output_dir)
 if args.execute:
  try:result=execute(root,RecoveryGitHub(os.environ.get("GH_TOKEN")),a,source,args.head)
  except original.ExecutionFailure as exc:
   (output/"recovery-receipt.json").write_bytes(encoded(exc.receipt))
   print(encoded(exc.receipt).decode());raise SystemExit(1)
  (output/"recovery-receipt.json").write_bytes(encoded(result))
 else:
  result={"gate":GATE,"status":"PASS","execution_status":"HELD","git_verification":git_result,
   "contract_sha256":sha(encoded(contract())),"failure_receipt_sha256":FAILURE_SHA,
   "release_id":RELEASE_ID,"asset_id":ASSET_ID,"manifest_bytes":len(raw),"manifest_sha256":sha(raw),
   "remote_writes":0,"publication_authorized":False,"deployment_authorized":False,"canonical_writes":0}
  (output/"verification.json").write_bytes(encoded(result))
 print(encoded(result).decode())

if __name__=="__main__":main()
