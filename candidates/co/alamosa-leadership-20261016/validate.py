"""Read-only, base-pinned leadership correction candidate checks."""
import copy,hashlib,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote.contract_v1 import validate_contract,build_representation_from_civic_gps_result
from tools.jurisdiction_package import validate_identity_graph,validate_role_term_sources

def validate(proposal=None):
 if not __debug__:raise RuntimeError('Candidate validator requires assertions enabled')
 if proposal is None:proposal=json.loads(pathlib.Path(__file__).with_name('proposal.json').read_text())
 assert proposal['status']=='PROPOSED_NOT_ADOPTED'
 assert proposal['canonical_path']=='data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json'
 assert proposal['production_eligible'] is False and proposal['publication_eligible'] is False
 leadership=proposal['leadership_record'];evidence=proposal['source_evidence'];assertion=proposal['source_assertion']
 assert leadership['person_id']=='person-co-alamosa-liz-hensley' and leadership['office_id']=='office-co-alamosa-council-ward-1'
 assert leadership['role_title']=='Mayor Pro Tem' and leadership['status']=='CURRENT'
 assert leadership['source_id']==evidence['source_id']==assertion['source_id']
 assert assertion['subject_type']=='LeadershipRole' and assertion['subject_id']==leadership['leadership_id']
 assert assertion['predicate']=='role_title' and assertion['object_value']=='Mayor Pro Tem' and assertion['normalized_status']=='PROPOSED'
 assert evidence['url']=='https://www.alamosa.gov/city-council-members'
 captured=pathlib.Path(__file__).with_name('evidence').joinpath('roster-facts.json').read_bytes()
 assert hashlib.sha256(captured).hexdigest()==evidence['capture_extract_sha256']
 facts=json.loads(captured);assert facts['source_url']==evidence['url'] and facts['retrieved_at']==evidence['accessed_at']
 assert facts['original_response_sha256']==evidence['content_hash']
 assert facts['observation']=={'name':'Liz Hensley','leadership':'Mayor Pro Tem','office':'City Councilor','ward':'1'}
 source=ROOT/proposal['canonical_path'];raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==proposal['canonical_sha256'],'Canonical baseline drift: reconcile before applying candidate'
 baseline=json.loads(raw);candidate=copy.deepcopy(baseline);assert not baseline['records']['leadership_roles']
 candidate['records']['leadership_roles'].append(proposal['leadership_record']);candidate['provenance']['source_evidence'].append(proposal['source_evidence']);candidate['provenance']['source_assertions'].append(proposal['source_assertion'])
 assert not validate_identity_graph(candidate['records']);assert not validate_role_term_sources(candidate['records'],candidate['provenance'])
 for table in baseline['records']:
  if table!='leadership_roles':assert candidate['records'][table]==baseline['records'][table]
 assert candidate['jurisdiction']==baseline['jurisdiction'];assert candidate['qa']==baseline['qa']
 base=export_factory_package(baseline,generated_at='2026-10-16T13:15:00Z',governed_package=True);exported=export_factory_package(candidate,generated_at='2026-10-16T13:15:00Z',governed_package=True)
 for table in ['people','organizations','posts','roles']:assert exported[table]==base[table]
 expected=copy.deepcopy(base['memberships']);member=next(m for m in expected if m['id']==proposal['existing_membership_id']);assert member['label'] is None;member['label']='Mayor Pro Tem';assert exported['memberships']==expected
 assert len(exported['evidence'])==len(base['evidence'])+1;assert len(exported['assertions'])==len(base['assertions'])+1
 added=[a for a in exported['assertions'] if a['id'] not in {b['id'] for b in base['assertions']}];assert len(added)==1 and added[0]['review_status']=='proposed'
 exported['certification']['status']='draft';assert not validate_contract(exported,require_certified=False);assert 'CONTRACT_NOT_CERTIFIED' in validate_contract(exported)
 response=build_representation_from_civic_gps_result(exported,'CANDIDATE REVIEW',{},binding={});assert response['error']=='CONTRACT_NOT_CERTIFIED' and 'applicable_offices' not in response
 assert proposal['leadership_record']['valid_from'] is None and proposal['leadership_record']['valid_to'] is None
 assert source.read_bytes()==raw
 return {'status':'CANDIDATE_CHECKS_PASS_NOT_ADOPTED','canonical_source_unchanged':True,'membership_delta':'Liz Hensley label: null -> Mayor Pro Tem','existing_ids_and_service_dates_preserved':True,'new_evidence_records':1,'new_proposed_assertions':1,'contract_status':'draft','production_consumer':'REJECTED_CONTRACT_NOT_CERTIFIED','production_eligible':False}
if __name__=='__main__':print(json.dumps(validate(),indent=2))
