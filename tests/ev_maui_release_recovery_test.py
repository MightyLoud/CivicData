#!/usr/bin/env python3
"""Recovery tests use an in-memory API; no external mutation is made."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"tests"))
from tools import ev_maui_release_recovery as r
from ev_maui_release_execution_test import FakeAPI as OriginalFakeAPI
e=r.original
HEAD,CERTIFIED="a"*40,"b"*40
NOW=datetime(2026,9,13,20,tzinfo=timezone.utc)

def source():
 value=e.load_json((ROOT/e.RECHECK).read_bytes())
 value["checked_at_utc"]=NOW.isoformat()
 for row in value["sources"]:row["retrieved_at_utc"]=NOW.isoformat()
 return value

def approved(review):
 value=r.approval_template()
 value.update(approved=True,publication_authorized=True,expected_execution_head=HEAD,
  certified_candidate_head=CERTIFIED,candidate_pr=68,source_recheck_sha256=e.sha(e.encoded(review)),
  approved_at_utc=NOW.isoformat(),expires_at_utc=(NOW+timedelta(hours=1)).isoformat(),
  approval_reference="SYNTHETIC_TEST_ONLY",operation_id="synthetic_recovery_001")
 return value

class FakeAPI(OriginalFakeAPI):
 def __init__(self):
  super().__init__()
  failure=e.load_json((ROOT/r.FAILURE).read_bytes())
  self.release={"id":r.RELEASE_ID,"tag_name":e.manifest.TAG,"target_commitish":e.manifest.TARGET,
   "name":e.TITLE,"body":e.release_body(ROOT,failure["approval"]),"draft":True,"prerelease":False}
  self.raw=(ROOT/e.manifest.MANIFEST).read_bytes()
  self.assets=[{"id":r.ASSET_ID,"name":e.manifest.ASSET,"size":5596,"digest":"sha256:"+e.ASSET_SHA,
                "content_type":"application/json","state":"uploaded"}]
  self.extra_release,self.timeout,self.bad_recovery_diff=False,False,False
  self.stale_after_publish=0;self.bad_failed_run=False
 def request(self,method,path,data=None,*,binary=False):
  self.calls.append((method,path))
  if method=="PATCH":
   e.require(self.allow_writes,"FAKE_WRITES_HELD")
   self.writes.append((method,path,deepcopy(data)))
   if path!=f"releases/{r.RELEASE_ID}":raise AssertionError(path)
   self.release.update(data)
   if self.timeout:raise TimeoutError("Synthetic ambiguous PATCH outcome")
   return deepcopy(self.release)
  if method!="GET":raise AssertionError("Recovery must never create, upload or delete")
  if path=="actions/runs/"+str(r.FAILED_RUN):
   return {"head_sha":HEAD if self.bad_failed_run else r.BASE,"event":"workflow_dispatch","status":"completed",
    "conclusion":"failure","run_attempt":1,"path":".github/workflows/ev-maui-release-execution-candidate.yml"}
  if path in {"pulls/67","pulls/68"}:
   old=path=="pulls/67"
   return {"merged":True,"state":"closed","draft":False,
    "head":{"sha":r.ORIGINAL_CERTIFIED if old else CERTIFIED,"repo":{"full_name":e.REPOSITORY}},
    "base":{"ref":"main","sha":e.BASE if old else r.BASE},"merge_commit_sha":r.BASE if old else HEAD}
  if path.startswith("pulls/67/files?") or path.startswith("pulls/68/files?"):
   old=path.startswith("pulls/67/")
   statuses=e.PATH_STATUS if old else {p:"added" for p in r.PATHS}
   rows=[{"filename":p,"status":s} for p,s in sorted(statuses.items())]
   if self.bad_diff or (self.bad_recovery_diff and not old):rows[0]["status"]="removed"
   return rows
  if path in {"git/commits/"+r.BASE,"git/commits/"+r.ORIGINAL_CERTIFIED}:
   return {"tree":{"sha":r.BASE_TREE},"parents":[{"sha":e.BASE}]}
  if path in {"git/commits/"+HEAD,"git/commits/"+CERTIFIED}:
   return {"tree":{"sha":"f"*40},"parents":[{"sha":r.BASE}]}
  if path.startswith("actions/runs?"):
   old=r.ORIGINAL_CERTIFIED in path
   workflows=e.WORKFLOWS if old else r.WORKFLOWS
   return {"workflow_runs":[{"id":i,"path":p,"head_sha":r.ORIGINAL_CERTIFIED if old else CERTIFIED,
    "event":"pull_request","status":"completed","conclusion":"failure" if self.bad_ci else "success"}
    for i,p in enumerate(sorted(workflows))]}
  if path=="git/ref/tags/"+e.manifest.TAG:
   return {"ref":"refs/tags/"+e.manifest.TAG,"object":{"type":"commit","sha":HEAD if self.bad_tag else e.manifest.TARGET}}
  if path.startswith("releases?"):
   rows=[deepcopy(self.release)]
   if self.extra_release:rows.append(dict(self.release,id=42))
   return rows
  if path==f"releases/{r.RELEASE_ID}":
   if self.fail_final and not self.release["draft"]:raise ValueError("FINAL_READBACK_FAILED")
   value=deepcopy(self.release)
   if self.stale_after_publish and not self.release["draft"]:
    value["draft"]=True;self.stale_after_publish-=1
   if self.bad_target:value["target_commitish"]=HEAD
   return value
  if path.startswith(f"releases/{r.RELEASE_ID}/assets?"):
   value=deepcopy(self.assets)
   if self.extra_asset:value.append(dict(value[0],id=42))
   return value
  if path==f"releases/assets/{r.ASSET_ID}" and binary:
   return self.raw+(b"x" if self.corrupt_bytes else b"")
  return super().request(method,path,data,binary=binary)

class RecoveryTests(unittest.TestCase):
 def execute(self,api=None,review=None,approval=None):
  review=review if review is not None else source()
  approval=approval if approval is not None else approved(review)
  return r.execute(ROOT,api or FakeAPI(),e.encoded(approval),e.encoded(review),HEAD,NOW)
 def test_local_contract_and_retained_failure(self):
  raw,failure=r.verify_local(ROOT,NOW.date())
  self.assertEqual(len(raw),5596)
  self.assertEqual(failure["release_id"],388004869)
  self.assertFalse(r.approval_template()["approved"])
 def test_unapproved_template_makes_zero_requests(self):
  api=FakeAPI()
  with self.assertRaisesRegex(ValueError,"RECOVERY_APPROVAL_REQUIRED"):
   self.execute(api,approval=r.approval_template())
  self.assertEqual(api.calls,[])
 def test_all_fixed_approval_bindings_reject_before_requests(self):
  for key,bad in {"release_id":42,"asset_id":42,"contract_sha256":"0"*64,
   "failure_receipt_sha256":"0"*64,"asset_sha256":"0"*64,"repository":"other/repo",
   "target_commit":HEAD,"tag":"wrong","deployment_authorized":True,"canonical_writes":1,
   "catalog_promotion":True,"kalawao_work":True,"expected_execution_head":CERTIFIED,
   "candidate_pr":67,"source_recheck_sha256":"0"*64,"operation_id":"../bad","approval_reference":""}.items():
   with self.subTest(key=key):
    api=FakeAPI();a=approved(source());a[key]=bad
    with self.assertRaises(ValueError):self.execute(api,approval=a)
    self.assertEqual(api.calls,[])
 def test_invalid_approval_dates_and_json(self):
  for start,end in [(NOW-timedelta(hours=2),NOW),(NOW+timedelta(seconds=1),NOW+timedelta(hours=1)),
                    (NOW,NOW+timedelta(hours=25))]:
   a=approved(source());a.update(approved_at_utc=start.isoformat(),expires_at_utc=end.isoformat())
   with self.assertRaisesRegex(ValueError,"APPROVAL_EXPIRED_OR_FUTURE"):self.execute(approval=a)
  for raw in [b'{"approved":true,"approved":false}',b'{"approved":NaN}']:
   with self.assertRaises(ValueError):r.validate_approval(raw,e.encoded(source()),HEAD,NOW)
 def test_stale_and_tampered_source_evidence_fail_before_requests(self):
  for change in [lambda x:x.update(status="PARTIAL"),
   lambda x:x.update(checked_at_utc=(NOW-timedelta(hours=25)).isoformat()),
   lambda x:x["sources"][0].update(retrieved_at_utc=(NOW-timedelta(hours=25)).isoformat()),
   lambda x:x["normalized_assertions"][0].update(person_id="wrong"),
   lambda x:x["normalized_assertions"][0].update(source_ids=["missing"]),
   lambda x:x["sources"][0].update(raw_excerpts=["unbound evidence"])]:
   api=FakeAPI();review=source();change(review)
   with self.assertRaises(ValueError):self.execute(api,review)
   self.assertEqual(api.calls,[])
 def test_context_boundary_and_existing_object_drift_make_zero_writes(self):
  for field in ["bad_main","bad_ci","bad_diff","bad_recovery_diff","bad_texas","bad_kauai","bad_failed_run",
                "bad_target","bad_tag","extra_asset","extra_release","corrupt_bytes"]:
   with self.subTest(field=field):
    api=FakeAPI();setattr(api,field,True)
    with self.assertRaises(e.ExecutionFailure):self.execute(api)
    self.assertEqual(api.writes,[]);self.assertFalse(api.allow_writes)
 def test_altered_body_or_asset_identity_rejected(self):
  for field in ["body","asset_id"]:
   api=FakeAPI()
   if field=="body":api.release["body"]+="unexpected"
   else:api.assets[0]["id"]=42
   with self.assertRaises(e.ExecutionFailure):self.execute(api)
   self.assertEqual(api.writes,[])
 def test_already_published_release_is_not_retried(self):
  api=FakeAPI();api.release["draft"]=False
  with self.assertRaises(e.ExecutionFailure):self.execute(api)
  self.assertEqual(api.writes,[])
 def test_success_is_one_patch_without_any_creation_upload_or_tag_write(self):
  api=FakeAPI();result=self.execute(api)
  self.assertEqual(api.writes,[("PATCH",f"releases/{r.RELEASE_ID}",{"draft":False,"make_latest":"false"})])
  self.assertTrue(result["publication_completed"]);self.assertEqual(result["status"],"PASS")
  self.assertEqual(result["boundaries_before"],result["boundaries_after"])
  self.assertEqual(result["completed_phases"],["PREFLIGHT","RECHECK","PUBLISH_EXISTING_DRAFT","VERIFY_PUBLISHED_RELEASE"])
  downloads=[x for x in api.calls if x==("GET",f"releases/assets/{r.ASSET_ID}")]
  self.assertEqual(len(downloads),3);self.assertFalse(api.allow_writes)
 def test_transient_postpublication_readback_repeats_only_reads(self):
  api=FakeAPI();api.stale_after_publish=1
  with patch.object(r.time,"sleep") as wait:result=self.execute(api)
  self.assertTrue(result["publication_completed"]);self.assertEqual(len(api.writes),1)
  wait.assert_called_once_with(1)
 def test_ambiguous_patch_does_not_retry_or_claim_success(self):
  api=FakeAPI();api.timeout=True
  with self.assertRaises(e.ExecutionFailure) as caught:self.execute(api)
  self.assertEqual(len(api.writes),1)
  self.assertEqual(caught.exception.receipt["phase"],"PUBLISH_EXISTING_DRAFT")
  self.assertIsNone(caught.exception.receipt["publication_completed"])
  self.assertFalse(caught.exception.receipt["automatic_retry"]);self.assertFalse(api.allow_writes)
 def test_final_readback_failure_preserves_known_ids(self):
  api=FakeAPI();api.fail_final=True
  with self.assertRaises(e.ExecutionFailure) as caught:self.execute(api)
  self.assertEqual(caught.exception.receipt["release_id"],r.RELEASE_ID)
  self.assertEqual(caught.exception.receipt["asset_id"],r.ASSET_ID)
  self.assertIsNone(caught.exception.receipt["publication_completed"])
  self.assertEqual(caught.exception.receipt["phase"],"VERIFY_PUBLISHED_RELEASE")
 def test_client_rejects_every_other_write_even_when_enabled(self):
  api=r.RecoveryGitHub("synthetic-not-a-credential");api.allow_writes=True
  for method,path,data in [("POST","releases",{}),("POST","git/refs",{}),
   ("DELETE",f"releases/{r.RELEASE_ID}",None),("PATCH","releases/42",{"draft":False,"make_latest":"false"}),
   ("PATCH",f"releases/{r.RELEASE_ID}",{"draft":False,"make_latest":"true"})]:
   with self.assertRaisesRegex(ValueError,"RECOVERY_MUTATION_REJECTED"):api.request(method,path,data)
  api.allow_writes=False
  with self.assertRaisesRegex(ValueError,"API_WRITES_HELD"):
   api.request("PATCH",f"releases/{r.RELEASE_ID}",{"draft":False,"make_latest":"false"})
 def test_exact_seven_added_paths(self):
  rows="\n".join("A\t"+p for p in sorted(r.PATHS))
  with patch.object(e,"git",side_effect=[HEAD,"",r.BASE_TREE,rows]):
   self.assertEqual(r.verify_git(ROOT,HEAD,r.BASE)["status"],"PASS")
  for bad in [rows+"\nA\tunrelated",rows.replace("A\t","M\t",1)]:
   with patch.object(e,"git",side_effect=[HEAD,"",r.BASE_TREE,bad]):
    with self.assertRaisesRegex(ValueError,"EXACT_SEVEN_RECOVERY_ADDITIONS_REQUIRED"):r.verify_git(ROOT,HEAD,r.BASE)
 def test_failure_receipt_and_original_executor_are_pinned(self):
  with patch.dict(r.PINS,{str(r.FAILURE):"0"*64}):
   with self.assertRaisesRegex(ValueError,"RECOVERY_PIN_DRIFT"):self.execute()
 def test_output_rejects_collision_traversal_and_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);out=root/r.ARTIFACTS/"new"
   r.output_directory(root,out)
   for bad in [out,root/"elsewhere",root/r.ARTIFACTS/"new/../other"]:
    with self.assertRaises(ValueError):r.output_directory(root,bad)
   link=root/r.ARTIFACTS/"link";link.symlink_to(out,target_is_directory=True)
   with self.assertRaises(ValueError):r.output_directory(root,link/"child")

if __name__=="__main__":unittest.main(verbosity=2)
