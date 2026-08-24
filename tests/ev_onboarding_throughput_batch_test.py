#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TOOL=ROOT/'tools'/'ev_onboarding_throughput_batch.py'
s=importlib.util.spec_from_file_location('ev_throughput',TOOL); mod=importlib.util.module_from_spec(s); s.loader.exec_module(mod)

def run():
    original_propose=mod.proposal.propose
    original_materialize=mod.materialize.materialize
    try:
        def fake_propose(root,jid):
            if jid=='jurisdiction:ready': return {'status':'READY','profile':'municipal_representation','routing_candidate':{'status':'GOVERNED_MATCH'}}
            if jid=='jurisdiction:review': return {'status':'REVIEW_REQUIRED','profile':'municipal_representation','routing_candidate':{'status':'RESEARCH_REQUIRED'}}
            if jid=='jurisdiction:proposal-error': raise ValueError('bad package')
            if jid=='jurisdiction:materialize-error': return {'status':'READY','profile':'municipal_essentials','routing_candidate':{'status':'GOVERNED_MATCH'}}
            raise AssertionError(jid)
        def fake_materialize(root,jid,out):
            if jid=='jurisdiction:materialize-error': raise RuntimeError('collision')
            return {'status':'ADD','changed_files':['onboarding/ev/ready.v0.1.json']}
        mod.proposal.propose=fake_propose; mod.materialize.materialize=fake_materialize
        with tempfile.TemporaryDirectory() as td:
            r=mod.run(ROOT,Path(td),['jurisdiction:ready','jurisdiction:review','jurisdiction:proposal-error','jurisdiction:materialize-error'])
        assert r['status']=='PASS' and r['targets']==4
        assert r['ready']==1 and r['review_required']==1 and r['blocked']==2
        rows={x['package_jurisdiction_id']:x for x in r['jurisdictions']}
        assert rows['jurisdiction:ready']['materialization_status']=='ADD'
        assert rows['jurisdiction:review']['disposition']=='REVIEW_REQUIRED'
        assert rows['jurisdiction:proposal-error']['disposition']=='BLOCKED'
        assert rows['jurisdiction:materialize-error']['disposition']=='BLOCKED'
        assert r['canonical_writes']==0
    finally:
        mod.proposal.propose=original_propose; mod.materialize.materialize=original_materialize
    print(json.dumps({'gate':'EV-IMP-017','status':'PASS','failure_isolation':'PASS','review_isolation':'PASS','canonical_writes':0},sort_keys=True))
if __name__=='__main__': run()
