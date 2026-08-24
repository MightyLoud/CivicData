#!/usr/bin/env python3
"""Batch proposal/materialization planner for EV jurisdiction throughput.

Processes every staged governed package in one run. A bad or research-required
jurisdiction is isolated to its own row and never blocks classification of the
rest. No routing authority is inferred and no repository/canonical writes occur.
"""
from __future__ import annotations
import argparse, importlib.util, json, sys
from collections import Counter
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
 sys.path.insert(0,str(ROOT))

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
proposal=load('ev_proposal_batch',ROOT/'tools'/'ev_onboarding_proposal.py')
materialize=load('ev_materialize_batch',ROOT/'tools'/'ev_onboarding_materialize.py')

def canonical(v:Any)->str:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n'

def discover_ids(root:Path)->list[str]:
 ids=[]
 for prefix,paths in proposal._artifact_groups(root).items():
  try:
   raw=proposal._decode_group(paths,prefix); _,summary=proposal._inspect_archive(raw,prefix)
   jid=str(summary.get('jurisdiction',{}).get('jurisdiction_id') or '')
   if jid and jid not in ids: ids.append(jid)
  except Exception: continue
 return sorted(ids)

def run(root:Path,out:Path,ids:list[str]|None=None)->dict[str,Any]:
 targets=sorted(set(ids or discover_ids(root))); rows=[]
 for jid in targets:
  row={'package_jurisdiction_id':jid,'canonical_writes':0}
  try:
   p=proposal.propose(root,jid); row['proposal_status']=p.get('status'); row['profile']=p.get('profile'); row['routing_candidate']=p.get('routing_candidate')
   if p.get('status')=='READY':
    try:
     plan=materialize.materialize(root,jid,out/'jurisdictions'/jid.replace(':','_').replace('/','_'))
     row['materialization_status']=plan.get('status'); row['changed_files']=plan.get('changed_files',[]); row['disposition']='READY' if plan.get('status') in {'ADD','NOOP'} else 'BLOCKED'
    except Exception as exc:
     row.update(materialization_status='ERROR',disposition='BLOCKED',error=f'{type(exc).__name__}: {exc}')
   else:
    row.update(materialization_status='NOT_RUN',disposition='REVIEW_REQUIRED')
  except Exception as exc:
   row.update(proposal_status='ERROR',materialization_status='NOT_RUN',disposition='BLOCKED',error=f'{type(exc).__name__}: {exc}')
  rows.append(row)
 counts=Counter(r['disposition'] for r in rows)
 report={'gate':'EV-IMP-017','status':'PASS','targets':len(rows),'ready':counts['READY'],'review_required':counts['REVIEW_REQUIRED'],'blocked':counts['BLOCKED'],'canonical_writes':0,'jurisdictions':rows}
 out.mkdir(parents=True,exist_ok=True); (out/'throughput-report.json').write_text(canonical(report),encoding='utf-8'); return report

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--repo-root',type=Path,default=Path('.')); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--package-jurisdiction-id',action='append',dest='ids'); a=ap.parse_args(); print(canonical(run(a.repo_root.resolve(),a.output,a.ids)).strip())
if __name__=='__main__':main()
