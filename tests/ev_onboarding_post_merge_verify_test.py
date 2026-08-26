#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TOOL=ROOT/'tools'/'ev_onboarding_post_merge_verify.py'
spec=importlib.util.spec_from_file_location('ev_post_merge',TOOL); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def request():
    return {'gate':'EV-IMP-015','status':'AUTHORIZED_FOR_ONE_SQUASH_MERGE','merge_method':'squash','merge_authorized':True,'pull_request_number':42,'expected_head_sha':'a'*40}
def evidence():
    return {'pull_request':{'number':42,'state':'closed','merged':True,'head_sha':'a'*40,'merge_commit_sha':'b'*40},'main_head_sha':'b'*40,'main_contains_merge_commit':True,'require_merge_as_current_main_head':True,'post_merge_checks':[{'name':'Empowered.Vote Essentials consumer','status':'PASS'},{'name':'Civic GPS live smoke','status':'PASS'},{'name':'EV onboarding live batch','status':'PASS'}],'production_materialization_status':'NOOP','canonical_writes':0,'publication_performed':False}
def must_fail(mutator):
    e=evidence(); mutator(e)
    try: mod.verify(request(),e)
    except mod.PostMergeVerificationError: return
    raise AssertionError('expected fail-closed')
def run():
    r=mod.verify(request(),evidence()); assert r['status']=='CLOSED_PASS'; assert r['closure_complete'] is True; assert len(r['closure_sha256'])==64
    must_fail(lambda e:e['pull_request'].__setitem__('head_sha','c'*40))
    must_fail(lambda e:e.__setitem__('main_contains_merge_commit',False))
    must_fail(lambda e:e['post_merge_checks'][0].__setitem__('status','FAIL'))
    must_fail(lambda e:e.__setitem__('production_materialization_status','ADD'))
    must_fail(lambda e:e.__setitem__('canonical_writes',1))
    must_fail(lambda e:e.__setitem__('publication_performed',True))
    print(json.dumps({'gate':'EV-IMP-016','status':'PASS','closure':'CLOSED_PASS','head_drift':'FAIL-CLOSED','main_reachability':'FAIL-CLOSED','post_merge_ci':'FAIL-CLOSED','idempotence':'FAIL-CLOSED','canonical_writes':0,'publication':False},sort_keys=True))
if __name__=='__main__': run()
