"""Candidate drift and evidence-link rejection checks; no source writes."""
import copy,importlib.util,json,pathlib,unittest,subprocess,sys
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('alamosa_candidate',HERE/'validate.py');candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
class CandidateTests(unittest.TestCase):
 def test_read_only_candidate_passes(self):self.assertEqual(candidate.validate()['status'],'CANDIDATE_CHECKS_PASS_NOT_ADOPTED')
 def test_optimized_execution_is_rejected(self):
  result=subprocess.run([sys.executable,'-O',str(HERE/'validate.py')],capture_output=True,text=True)
  self.assertNotEqual(result.returncode,0);self.assertIn('requires assertions enabled',result.stderr)
 def test_drift_rejected(self):
  original=json.loads((HERE/'proposal.json').read_text())
  mutations=[('canonical_sha256','wrong'),('production_eligible',True),('status','ADOPTED'),('canonical_path','README.md')]
  for key,value in mutations:
   with self.subTest(key=key):
    p=copy.deepcopy(original);p[key]=value
    with self.assertRaises(AssertionError):candidate.validate(p)
 def test_linked_fact_and_capture_tampering_rejected(self):
  original=json.loads((HERE/'proposal.json').read_text())
  mutations=[('leadership_record','person_id','person-co-alamosa-ty-coleman'),('leadership_record','role_title','Mayor'),('source_evidence','content_hash','0'*64),('source_evidence','url','https://example.invalid/'),('source_assertion','source_id','missing'),('source_assertion','subject_id','missing'),('source_assertion','normalized_status','NORMALIZED')]
  for section,key,value in mutations:
   with self.subTest(section=section,key=key):
    p=copy.deepcopy(original);p[section][key]=value
    with self.assertRaises(AssertionError):candidate.validate(p)
if __name__=='__main__':unittest.main()
