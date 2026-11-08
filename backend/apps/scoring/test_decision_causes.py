"""Structured decision causes: evidentiary unknowns are never processing failures."""
from django.test import SimpleTestCase, TestCase

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .capability import decision_causes as dc
from .capability.engine import release
from .capability.evaluation import evaluate, validate_decisions
from .capability.recommendation_execution import deterministic_advice
from .capability.recommendations import processing_failure
from .capability.storage import checkpoint, create_run, publish
from apps.scoring.capability.storage import frozen_sources

PASSAGE = 'The IT committee reviewed laboratory computing capacity and recorded upgrade needs for each department.'


def indicator():
    return release()['indicators'][0]


def row(condition_id, **kw):
    return {'condition_id': condition_id, 'state': 'unknown', 'reason': 'Insufficient evidence.',
            'scope_supported': False, 'period_supported': False, 'citations': [], **kw}


class ValidateCauseTests(SimpleTestCase):
    def setUp(self):
        self.ind = indicator()
        self.ids = [c['id'] for c in self.ind['conditions']]
        self.sources = [{'id': 's1', 'document_id': 'd1', 'page_number': 4, 'text': PASSAGE}]

    def decide(self, first):
        rows = [first] + [row(cid) for cid in self.ids[1:]]
        return {r['condition_id']: r for r in validate_decisions(self.ind, {'conditions': rows}, self.sources)}

    def test_undated_substantive_fit_is_evidentiary_not_processing(self):
        out = self.decide(row(self.ids[0], state='met', reason='Review recorded.', scope_supported=True,
                              period_supported=False, citations=[{'source_id': 's1', 'quote': PASSAGE}]))
        record = out[self.ids[0]]
        self.assertEqual(record['state'], 'unknown')
        self.assertEqual(record['cause'], dc.SCOPE_OR_PERIOD_UNSUPPORTED)
        self.assertEqual(record['withheld_state'], 'met')
        self.assertFalse(dc.is_processing(record))

    def test_fabricated_quote_is_response_invalid(self):
        out = self.decide(row(self.ids[0], state='met', reason='x', scope_supported=True, period_supported=True,
                              citations=[{'source_id': 's1', 'quote': 'This sentence is not anywhere in the page text.'}]))
        self.assertEqual(out[self.ids[0]]['cause'], dc.RESPONSE_INVALID)
        self.assertTrue(dc.is_processing(out[self.ids[0]]))

    def test_model_chosen_unknown_is_assessed(self):
        out = self.decide(row(self.ids[0]))
        self.assertEqual(out[self.ids[0]]['cause'], dc.ASSESSED)
        self.assertNotIn('withheld_state', out[self.ids[0]])

    def test_model_chosen_unknown_can_identify_a_missing_period(self):
        out = self.decide(row(self.ids[0], scope_supported=True, period_supported=False))
        record = out[self.ids[0]]
        self.assertEqual(record['cause'], dc.SCOPE_OR_PERIOD_UNSUPPORTED)
        self.assertFalse(dc.is_processing(record))
        self.assertFalse(record['validation_issue'])

    def test_malformed_state_does_not_crash(self):
        out = self.decide(row(self.ids[0], state=['met'], reason='x'))
        self.assertEqual(out[self.ids[0]]['cause'], dc.RESPONSE_INVALID)
        self.assertIsNone(out[self.ids[0]]['withheld_state'])

    def test_unevaluated_indicator_records_not_evaluated(self):
        result = evaluate([], service=None, population='All', reference_period='2025-26', max_calls=0)
        self.assertTrue(all(r['cause'] == dc.NOT_EVALUATED for r in result['records']))


class LegacyAndAdviceTests(SimpleTestCase):
    def test_legacy_period_reason_is_evidentiary(self):
        legacy = {'state': 'unknown', 'reason': dc.SCOPE_OR_PERIOD_ISSUE, 'validation_issue': dc.SCOPE_OR_PERIOD_ISSUE}
        self.assertEqual(dc.cause_of(legacy), dc.SCOPE_OR_PERIOD_UNSUPPORTED)
        self.assertFalse(processing_failure(legacy))

    def test_legacy_processing_reasons_remain_processing(self):
        for reason in ('No readable source context. Capability is unknown.',
                       'Model evaluation failed (output_truncated). Capability is unknown.',
                       'Quote does not match a supplied source passage.'):
            self.assertTrue(processing_failure({'state': 'unknown', 'reason': reason}), reason)

    def test_legacy_review_guard_is_not_processing(self):
        reason = 'Citation reuses a rejected or superseded claim; independent supporting evidence is required.'
        self.assertEqual(dc.cause_of({'state': 'unknown', 'reason': reason}), dc.REVIEW_GUARD)
        self.assertFalse(processing_failure({'state': 'unknown', 'reason': reason}))

    def test_period_unsupported_advice_requests_a_dated_scoped_record(self):
        action = {'id': 'X', 'requirement': 'Review computing capacity', 'type': 'supply_evidence', 'operation': 'supply',
                  'completion_evidence': '', 'citations': [], 'cause': dc.SCOPE_OR_PERIOD_UNSUPPORTED,
                  'reason': dc.SCOPE_OR_PERIOD_ISSUE, 'state': 'unknown'}
        advice = deterministic_advice(action, {'population': 'All', 'reference_period': '2025-26'},
                                      'deterministic_evidence_request')
        self.assertIn('dated period', advice['steps'][0])
        self.assertNotIn('processing result', advice['steps'][0])

    def test_summary_separates_evidence_review_and_processing(self):
        records = [{'state': 'met', 'cause': dc.ASSESSED}, {'state': 'unknown', 'cause': dc.ASSESSED},
                   {'state': 'unknown', 'cause': dc.SCOPE_OR_PERIOD_UNSUPPORTED},
                   {'state': 'unknown', 'cause': dc.REVIEW_GUARD}, {'state': 'unknown', 'cause': dc.NOT_EVALUATED}]
        s = dc.summary(records)
        self.assertEqual((s['unknown_evidentiary'], s['unknown_review'], s['unknown_processing']), (2, 1, 1))


class PublishedCauseTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='College')
        self.sprint = Sprint.objects.create(institution=self.institution)
        doc = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        self.page = DocumentPage.objects.create(document=doc, page_number=1, text=PASSAGE)

    def test_publication_keeps_evaluator_cause_and_summary(self):
        run = create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk,
                         population='All faculty and students', reference_period='2025-26')
        args = {'institution_id': self.institution.pk, 'run_id': run.pk}
        checkpoint(**args, state='running')
        evaluation = evaluate(frozen_sources(run), service=None, population='All', reference_period='2025-26', max_calls=0)
        event = publish(**args, evaluation=evaluation,
                        inference={'provider': 'none', 'model': 'none', 'settings': {}, 'calls': []})
        self.assertTrue(all(r['cause'] == dc.NOT_EVALUATED for r in event.payload['records']))
        self.assertEqual(event.payload['decision_causes']['unknown_processing'], 216)
        # Score arithmetic is unchanged by the additive cause fields.
        self.assertNotIn('decision_causes', event.payload['result'])
