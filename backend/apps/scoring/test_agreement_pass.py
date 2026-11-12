"""Two-pass agreement: a requirement stands only when both assessments of the same packet agree."""
import unittest

from django.test import SimpleTestCase, override_settings

from apps.scoring.capability.decision_causes import ASSESSOR_DISAGREEMENT, summary
from apps.scoring.capability.engine import release
from apps.scoring.capability.evaluation import evaluate
from apps.scoring.capability.execution import AssessmentDisabled, policy

SOURCE = {'id': 'document-a:1', 'text': 'The institution approved an AI strategy for the current academic year.'}


class Scripted:
    """Returns the scripted responses in order and counts requests."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    def extract_structured_data(self, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


class AgreementPassTests(unittest.TestCase):
    def setUp(self):
        rubric = release('AIQIF-CAP-0.2')
        self.rubric = {**rubric, 'indicators': rubric['indicators'][:1]}
        self.ids = [c['id'] for c in self.rubric['indicators'][0]['conditions']]

    def response(self, first_state, quote=SOURCE['text']):
        rows = {cid: {'state': 'unknown', 'reason': 'Not shown.', 'scope_supported': False, 'period_supported': False,
                      'citations': []} for cid in self.ids}
        if first_state == 'met':
            rows[self.ids[0]] = {'state': 'met', 'reason': 'Scoped current evidence supplied.', 'scope_supported': True,
                                 'period_supported': True, 'citations': [{'source_id': SOURCE['id'], 'quote': quote}]}
        return {'conditions': rows}

    def first(self, result):
        return next(r for r in result['records'] if r['condition_id'] == self.ids[0])

    def run_eval(self, service, passes=2):
        return evaluate([SOURCE], service=service, population='All institution programmes', reference_period='2025-26',
                        rubric=self.rubric, agreement_passes=passes)

    def test_agreeing_passes_keep_the_credit_and_its_citations(self):
        service = Scripted(self.response('met'), self.response('met'))
        result = self.run_eval(service)
        record = self.first(result)
        self.assertEqual((record['state'], service.calls), ('met', 2))
        self.assertTrue(record['citations'])
        self.assertEqual(result['traces'][0]['agreement_audit']['disagreements'], [])

    def test_disagreement_becomes_unknown_routed_to_review_and_never_credited(self):
        result = self.run_eval(Scripted(self.response('met'), self.response('unknown')))
        record = self.first(result)
        self.assertEqual((record['state'], record['cause'], record['citations']),
                         ('unknown', ASSESSOR_DISAGREEMENT, []))
        self.assertIn('routed to review', record['reason'])
        audit = result['traces'][0]['agreement_audit']
        self.assertEqual([d['condition_id'] for d in audit['disagreements']], [self.ids[0]])
        self.assertEqual(audit['disagreements'][0]['first']['state'], 'met')
        self.assertEqual(summary(result['records'])['unknown_review'], 1)

    def test_second_pass_cannot_add_credit(self):
        record = self.first(self.run_eval(Scripted(self.response('unknown'), self.response('met'))))
        self.assertEqual((record['state'], record['cause']), ('unknown', ASSESSOR_DISAGREEMENT))

    def test_invalid_second_pass_citation_keeps_the_first_decision(self):
        result = self.run_eval(Scripted(self.response('met'), self.response('met', quote='An invented quotation here.')))
        self.assertEqual(self.first(result)['state'], 'met')
        self.assertEqual(result['traces'][0]['agreement_audit']['second_pass_unusable'], [self.ids[0]])

    def test_single_pass_is_unchanged(self):
        service = Scripted(self.response('met'))
        result = self.run_eval(service, passes=1)
        self.assertEqual((self.first(result)['state'], service.calls), ('met', 1))
        self.assertIsNone(result['traces'][0]['agreement_audit'])

    def test_rejects_unsupported_pass_counts(self):
        with self.assertRaises(ValueError):
            self.run_eval(Scripted(), passes=3)


class AgreementPolicyTests(SimpleTestCase):
    @override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_MAX_HTTP_CALLS=72)
    def test_two_passes_need_room_for_two_requests_per_indicator(self):
        with self.assertRaises(AssessmentDisabled):
            policy()

    @override_settings(CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_MAX_HTTP_CALLS=90,
                       CAPABILITY_GEMINI_REASONING_EFFORT='high', AI_GEMINI_REASONING_EFFORT='low')
    def test_policy_records_passes_and_assessor_reasoning_effort(self):
        frozen = policy()
        self.assertEqual((frozen['agreement_passes'], frozen['gemini_reasoning_effort']), (2, 'high'))

    @override_settings(CAPABILITY_GEMINI_REASONING_EFFORT=None, AI_GEMINI_REASONING_EFFORT='low')
    def test_assessor_effort_falls_back_to_the_shared_setting(self):
        self.assertEqual(policy()['gemini_reasoning_effort'], 'low')
