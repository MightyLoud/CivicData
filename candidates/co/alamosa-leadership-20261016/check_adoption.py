"""Read-only acceptance checks for the proposed canonical adoption; no certification."""
import copy,csv,hashlib,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from consumers.empowered_vote.package_source import load_jurisdiction_package
from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote.contract_v1 import validate_contract
from tools.jurisdiction_package import validate

def check():
 if not __debug__:raise RuntimeError('Assertions must be enabled')
 here=pathlib.Path(__file__).parent;p=json.loads((here/'proposal.json').read_text());baseline=json.loads((here/'baseline-package.json').read_text());folder=ROOT/pathlib.Path(p['canonical_path']).parent
 pkg=load_jurisdiction_package(folder);assert not validate(pkg)
 expected=copy.deepcopy(baseline)
 expected['records']['leadership_roles']=copy.deepcopy(pkg['records']['leadership_roles'])
 expected['provenance']['source_evidence'].append(p['source_evidence'])
 a=copy.deepcopy(p['source_assertion']);a['normalized_status']='NORMALIZED';a['notes']='Official roster supports the leadership title; exact leadership service dates remain unknown.'
 expected['provenance']['source_assertions'].append(a)
 assert pkg==expected
 roles=pkg['records']['leadership_roles'];assert len(roles)==1
 role=copy.deepcopy(roles[0]);role['notes']=p['leadership_record']['notes'];assert role==p['leadership_record']
 for line in (folder/'SHA256SUMS.txt').read_text().splitlines():
  digest,name=line.split('  ',1);assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
 manifest=json.loads((folder/'manifest.json').read_text())
 for table,rows in [('leadership_roles',roles),('source_evidence',pkg['provenance']['source_evidence']),('source_assertions',pkg['provenance']['source_assertions'])]:
  assert manifest['record_counts'][table]==len(rows)
  with (folder/(table+'.csv')).open(newline='') as f:actual=list(csv.DictReader(f))
  assert actual==[{k:'' if v is None else str(v) for k,v in ((key,row.get(key)) for key in actual[0])} for row in rows]
 old=export_factory_package(baseline,generated_at='2026-10-16T13:15:00Z',governed_package=True);new=export_factory_package(pkg,generated_at='2026-10-16T13:15:00Z',governed_package=True)
 for table in ['people','organizations','posts','roles']:assert old[table]==new[table]
 members=copy.deepcopy(old['memberships']);next(m for m in members if m['id']==p['existing_membership_id'])['label']='Mayor Pro Tem';assert new['memberships']==members
 new['certification']['status']='draft';assert not validate_contract(new,require_certified=False)
 print('ADOPTION_DRAFT_CHECKS_PASS; existing identifiers, service dates and historical QA preserved; no recertification')
if __name__=='__main__':check()
