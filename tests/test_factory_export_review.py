"""Hash/authority/scope controls for Factory export review, with real package data."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from tools.factory_export_review import prepare_review, apply_certification, fingerprint, ExportReviewError
from adapters.factory.export_representation import export_factory_package
from consumers.empowered_vote.contract_v1 import validate_contract, build_representation_from_civic_gps_result

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'candidates/co/alamosa-leadership-20261016'


class FactoryExportReviewTests(unittest.TestCase):
    def setUp(self):
        self.package = json.loads((ROOT / 'data/normalized/co/jurisdiction-co-alamosa/jurisdiction.json').read_text())
        baseline = json.loads((CANDIDATE / 'baseline-package.json').read_text())
        self.old = export_factory_package(baseline, generated_at='2026-10-16T12:00:00Z', governed_package=True)
        self.review = prepare_review(self.package, self.old, generated_at='2026-10-16T15:25:00Z')
        # Synthetic approval only: no real reviewer decision or runtime artifact.
        self.decision = {key: self.review[key] for key in ('source_sha256','prior_contract_sha256','draft_sha256')}
        self.decision.update(scope='FULL_RUNTIME_CONTRACT', approved=True, reviewer='TEST REVIEWER', reviewer_authority='civicdata_certification', reason='Synthetic full-scope test decision', verified_at='2026-10-16T15:26:00Z', gates={k: True for k in ('raw_complete','normalized_complete','qa_passed','parity_ok')}, evidence_refs=['test-fixture'])

    def test_draft_preserves_dates_and_is_rejected(self):
        before = deepcopy((self.package, self.old))
        draft = self.review['contract']
        self.assertEqual(draft['certification']['status'], 'draft')
        self.assertIsNone(draft['certification']['verified_at'])
        self.assertEqual(validate_contract(draft, require_certified=False), [])
        response = build_representation_from_civic_gps_result(draft, 'TEST', {}, binding={})
        self.assertEqual(response['error'], 'CONTRACT_NOT_CERTIFIED')
        old = {a['id']: a for a in self.old['assertions']}
        for a in draft['assertions']:
            if a['id'] in old:
                self.assertEqual(a, old[a['id']])
            else:
                self.assertIsNone(a['asserted_at']); self.assertIsNone(a['reviewed_at'])
        self.assertEqual((self.package, self.old), before)

    def test_explicit_synthetic_full_review_appends_audit(self):
        prior = [{'historical': 'unchanged'}]; before = deepcopy((self.review,self.decision,prior))
        result = apply_certification(self.review,self.decision,source_package=self.package,history=prior)
        self.assertEqual(validate_contract(result['contract']), [])
        self.assertEqual(result['certification_history'][0], prior[0])
        self.assertEqual(len(result['certification_history']),2)
        self.assertEqual(result['certification_history'][-1]['certified_contract_sha256'],fingerprint(result['contract']))
        self.assertFalse(result['runtime_publication_granted']); self.assertFalse(result['activation_granted'])
        self.assertEqual((self.review,self.decision,prior),before)

    def test_incomplete_or_wrong_scope_decisions_reject(self):
        cases=[('scope','TITLE_OBSERVATION'),('approved',False),('approved',1),('reviewer',''),('reviewer_authority','civicdata_representation'),('reason',''),('verified_at','2026-10-16'),('evidence_refs',[])]
        cases += [(key,'0'*64) for key in ('source_sha256','prior_contract_sha256','draft_sha256')]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                d=deepcopy(self.decision);d[key]=value
                with self.assertRaises(ExportReviewError):apply_certification(self.review,d,source_package=self.package)
        for key in self.decision['gates']:
            for value in (False,1,None):
                with self.subTest(gate=key,value=value):
                    d=deepcopy(self.decision);d['gates'][key]=value
                    with self.assertRaises(ExportReviewError):apply_certification(self.review,d,source_package=self.package)

    def test_changed_draft_rejects_approval(self):
        r=deepcopy(self.review);r['contract']['memberships'][0]['label']='tampered'
        with self.assertRaisesRegex(ExportReviewError,'DRAFT_FINGERPRINT_MISMATCH'):apply_certification(r,self.decision,source_package=self.package)

    def test_review_cannot_predate_draft(self):
        decision=deepcopy(self.decision);decision['verified_at']='2026-08-19T00:00:00Z'
        with self.assertRaisesRegex(ExportReviewError,'REVIEW_PREDATES_DRAFT'):
            apply_certification(self.review,decision,source_package=self.package)

    def test_changed_source_rejects_stored_review(self):
        package=deepcopy(self.package);package['records']['people'][0]['notes']='Changed after review'
        with self.assertRaisesRegex(ExportReviewError,'SOURCE_FINGERPRINT_MISMATCH'):
            apply_certification(self.review,self.decision,source_package=package)

    def test_changed_prior_assertion_requires_review(self):
        old=deepcopy(self.old);old['assertions'][0]['value']='old different value'
        with self.assertRaisesRegex(ExportReviewError,'EXISTING_ASSERTION_CHANGED'):prepare_review(self.package,old,generated_at='2026-10-16T15:25:00Z')


if __name__=='__main__':unittest.main()
