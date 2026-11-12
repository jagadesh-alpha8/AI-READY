from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from .capability.engine import release
from .capability.evidence_audit import audit_request
from .capability.reviewed_evidence import for_context
from .capability.selection_experiment import candidate_pools, compare_pools, pack_rankings
from .capability.passages import Passage


class EvidenceConsumptionAuditTests(SimpleTestCase):
    def setUp(self):
        self.rubric = release()
        full = self.rubric['indicators'][0]
        self.indicator = {**full, 'conditions': full['conditions'][:1]}
        self.cid = self.indicator['conditions'][0]['id']
        self.quote = 'The approved strategy identifies an accountable owner and eligible learners.'
        self.sources = [{'id':'p', 'document_id':'d', 'page_number':1, 'text':self.quote, 'text_offset':50}]
        self.ledger = {'claims':[self.claim('a', self.quote)], 'issues':[]}

    def claim(self, cid, quote):
        src = {'document_id':'d', 'page':'1', 'quote':quote, 'version':1, 'current':True}
        return {'id':cid, 'attribute':'strategy', 'label':'Strategy', 'value':'owner named', 'kind':'context',
                'disposition':'confirmed', 'verification':{'grounding':'exact', 'validation':'pass'},
                'scope':{}, 'source':src, 'original_source':deepcopy(src), 'decisions':[]}

    def request(self, **extra):
        return {'id':'synthetic', 'payload':{'indicator':self.indicator, 'sources':self.sources,
            'reviewed_evidence':for_context(self.ledger, self.sources)}, **extra}

    def response(self, **extra):
        return {'conditions':[{'condition_id':self.cid, 'state':'met', 'reason':'Scoped strategy documented.',
            'scope_supported':True, 'period_supported':True,
            'citations':[{'source_id':'p','quote':self.quote}], **extra}]}

    def test_prepared_packet_is_not_a_model_decision(self):
        r = audit_request(self.request(), self.ledger, self.rubric)
        self.assertEqual(r['status'], 'prepared_unexecuted')
        self.assertNotIn('validated', r)
        self.assertFalse(r['model_execution_verified'])
        self.assertTrue(r['review_packet_matches_current_projection'])
        self.assertEqual(r['attachment_audit']['claims'][0]['current_references'], [{'source_id':'p','text_offset':50}])

    def test_credit_validation_and_evidentiary_unknown_are_distinct(self):
        good = audit_request(self.request(response=self.response()), self.ledger, self.rubric)
        self.assertGreater(good['demonstrated_points_from_this_packet'], 0)
        self.assertIsNone(good['recommendation_audit'][0]['kind'])
        bad = audit_request(self.request(response=self.response(citations=[{'source_id':'p','quote':'Invented unsupported quotation longer than twenty characters.'}])), self.ledger, self.rubric)
        self.assertEqual(bad['demonstrated_points_from_this_packet'], 0)
        self.assertTrue(bad['recommendation_audit'][0]['processing_failure'])
        self.assertTrue(bad['validated'][0]['validation_issue'])
        unknown = audit_request(self.request(response=self.response(state='unknown', citations=[], reason='Only a title is supplied.')), self.ledger, self.rubric)
        self.assertFalse(unknown['recommendation_audit'][0]['processing_failure'])
        self.assertEqual(unknown['recommendation_audit'][0]['kind'], 'supply_evidence')

    def test_conflict_resolution_and_rejected_alternative_use_full_ledger(self):
        alternative = 'A different approved strategy assigns incompatible responsibility.'
        self.ledger['claims'].append(self.claim('b', alternative))
        self.ledger['issues'] = [{'id':'conflict', 'kind':'conflict', 'status':'open', 'claim_ids':['a','b'], 'rationale':'Same scope, different owners.'}]
        opened = audit_request(self.request(response=self.response()), self.ledger, self.rubric)
        self.assertEqual(opened['validated'][0]['state'], 'unknown')
        self.assertEqual(opened['attachment_audit']['claims'][1]['reason'], 'conflict_alternative_context_only')
        self.ledger['issues'][0].update(status='resolved', rationale='The signed policy is authoritative.')
        self.ledger['claims'][1]['disposition'] = 'rejected'
        resolved = audit_request(self.request(response=self.response()), self.ledger, self.rubric)
        self.assertEqual(resolved['validated'][0]['state'], 'met')
        self.assertEqual(resolved['attachment_audit']['issues'][0]['status'], 'resolved')
        self.sources.append({'id':'p2', 'document_id':'d', 'page_number':1, 'text':alternative, 'text_offset':150})
        rejected = audit_request(self.request(response=self.response(citations=[{'source_id':'p2','quote':alternative}])), self.ledger, self.rubric)
        self.assertEqual(rejected['validated'][0]['state'], 'unknown')

    def test_bounded_omission_differs_from_no_overlap_without_mutating_ledger(self):
        self.ledger['claims'] = [self.claim(f'{n:03}', self.quote) for n in range(22)] + [self.claim('missing', 'An unrelated quotation outside selected source excerpts.')]
        before = deepcopy(self.ledger)
        rows = audit_request(self.request(), self.ledger, self.rubric)['attachment_audit']['claims']
        self.assertEqual(sum(x['reason']=='bounded_packet_omission' for x in rows), 2)
        self.assertEqual(rows[-1]['reason'], 'no_selected_quote_overlap')
        self.assertEqual(self.ledger, before)

    def test_evaluator_trace_retains_the_actual_sent_review_packet(self):
        from .capability.evaluation import evaluate
        from unittest.mock import patch
        sent = []
        response = self.response()
        class Service:
            def extract_structured_data(self, **kwargs):
                sent.append(json.loads(kwargs['user_content']))
                return response
        with patch('apps.scoring.capability.evaluation.select_context', return_value=self.sources):
            result = evaluate(self.sources, service=Service(), population='Learners',
                reference_period='2024-25', rubric={'indicators':[self.indicator]},
                reviewed_evidence=self.ledger, retrieval_policy={'mode':'bm25'})
        trace = result['traces'][0]
        self.assertEqual(trace['reviewed_evidence_packet'],sent[0]['reviewed_evidence'])
        self.assertEqual(trace['reviewed_attachment_audit']['claims'][0]['reason'],'current_quote_overlap')
        self.assertEqual(result['records'][0]['state'],'met')

    def test_mismatched_ledger_and_changed_assertions_fail_closed(self):
        req = self.request(response=self.response()); req['payload']['reviewed_evidence'] = None
        with self.assertRaises(ValueError):audit_request(req, self.ledger, self.rubric)
        req = self.request(); req['payload']['indicator'] = deepcopy(self.indicator)
        req['payload']['indicator']['conditions'][0]['text'] = 'A changed assertion'
        with self.assertRaises(ValueError):audit_request(req, self.ledger, self.rubric)

    def test_offline_command_refuses_overwrite(self):
        with TemporaryDirectory() as folder:
            src, dst = Path(folder)/'in.json', Path(folder)/'out.json'
            src.write_text(json.dumps({'rubric':self.rubric, 'reviewed_evidence':self.ledger, 'requests':[self.request()]}))
            call_command('capability_evidence_audit', str(src), output=str(dst), stdout=StringIO())
            self.assertTrue(json.loads(dst.read_text())['no_provider_calls'])
            with self.assertRaises(CommandError):call_command('capability_evidence_audit', str(src), output=str(dst))


class MatchedSelectionExperimentTests(SimpleTestCase):
    def trace(self):
        source = {'id':'p','text':'H'*20+'A'*100+'B'*100}
        other = {'id':'q','text':source['text']}
        passages = [Passage(source,20,120,'prose',(0,20),'lexical',10),
                    Passage(source,120,220,'prose',(0,20),'semantic',10),
                    Passage(other,20,120,'prose',(0,20),'other',10)]
        req = {'condition_id':'a','anchor':'Scope','assertion':'Assertion',
               'lexical':[0,2],'semantic':[1,2], 'lexical_scores':[1.,0.,1.], 'similarity':[0.,1.,1.]}
        return {'passages':passages,'requirements':[req], 'expansion_exclusions':{}}

    def test_scores_queries_and_budgets_shared_between_arms(self):
        trace = self.trace(); calls=[]
        def score(query, texts):calls.append((query,texts)); return [1.,3.,2.]
        result = compare_pools(trace, score, budget=120)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 'Scope Assertion')
        self.assertEqual(result['arms']['lexical']['rankings']['a'], [2,0])
        self.assertEqual(result['arms']['combined']['rankings']['a'], [1,2,0])
        self.assertEqual(result['semantic_only_candidates'], [1])
        for arm in result['arms'].values():
            self.assertLessEqual(arm['used_chars'],120)
            for s in arm['sources']:
                original = next(p.source for p in trace['passages'] if p.source['id']==s['id'])
                self.assertEqual(s['text'],original['text'][s['text_offset']:s['text_offset']+len(s['text'])])

    def test_heading_overlap_and_separate_provenance(self):
        trace = self.trace(); result = pack_rankings(trace['passages'], {'a':[0,1,2]}, 340)
        self.assertEqual(result['used_chars'],340)
        self.assertEqual(len(result['sources']),2)
        self.assertEqual({s['id'] for s in result['sources']},{'p','q'})
        self.assertEqual(result['sources'][0]['text'],trace['passages'][0].source['text'])

    def test_bad_scores_pair_limit_and_exclusions(self):
        trace = self.trace()
        with self.assertRaises(ValueError):compare_pools(trace, lambda *a: [], max_pairs=2)
        with self.assertRaises(ValueError):compare_pools(trace, lambda *a: [float('nan')]*3)
        with self.assertRaises(ValueError):compare_pools(trace, lambda *a: [1.])
        trace['expansion_exclusions'] = {1:'instruction_only'}
        self.assertNotIn(1,candidate_pools(trace)['combined'])
