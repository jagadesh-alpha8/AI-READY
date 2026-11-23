"""Fixes from the A2 audit (claude/ai-ready-a2-audit.md, 23 Nov 2026). Each test failed before its fix."""
import json
from fractions import Fraction

from django.test import SimpleTestCase, TestCase, override_settings

from .capability import depth, reserve
from .capability.depth_service import create_questions, judge_run, latest_levels, load_responses
from .capability.engine import documented, release
from .models import DepthJudgment, DepthPastCase, DepthPlan, DepthQuestion
from .test_depth import DOCUMENT, F1, F2, WEAK, FakeModel, export


class AllShownModel(FakeModel):
    """Plans: every dimension of every credited requirement is answered by its own quotation, so no depth question."""

    def __call__(self, system_prompt, user_content, response_schema, schema_name):
        if schema_name == 'depth_question_plan':
            payload = json.loads(user_content)
            self.calls.append((schema_name, payload))
            return {'answered': [{'condition_id': r['condition_id'], 'dimension_id': d['id'], 'evidence_quote': WEAK}
                                 for r in payload['credited_requirements'] for d in r['dimensions']],
                    'questions': [], 'missing_items': []}
        if schema_name == 'depth_judgment':
            payload = json.loads(user_content)
            self.calls.append((schema_name, payload))
            return {'level': 'strong', 'contradicts_evidence': False, 'relies_on_unsupported': False,
                    'dimension_findings': [], 'reason': 'Every dimension is in the quotations.'}
        return super().__call__(system_prompt, user_content, response_schema, schema_name)


class Strong(FakeModel):
    """The same answers, read as strong (a second reading that differs from the first)."""

    def __call__(self, s, u, r, name):
        out = super().__call__(s, u, r, name)
        if name == 'depth_judgment':
            out['level'] = 'strong'
        return out


@override_settings(DEPTH_MAX_QUESTIONS=0)
class DepthJudgingFixes(TestCase):
    """Audit bugs 1 and 2."""

    def test_requirements_shown_by_their_own_quotations_are_judged_on_them(self):
        data = export(credited={F1: 1})
        model = AllShownModel()
        create_questions(data, model, commit=True)
        self.assertIn(F1, DepthPlan.objects.get(run_ref='run-1').shown_by_evidence)
        self.assertFalse(DepthQuestion.objects.filter(kind='depth').exists())
        result = judge_run(data, model, commit=True)
        judged = {j['condition_id']: j for j in result['judged']}
        self.assertEqual(judged[F1]['final_level'], 'strong')
        self.assertTrue(judged[F1]['on_own_quotes'])
        payload = [p for n, p in model.calls if n == 'depth_judgment'][0]
        self.assertEqual(payload['follow_up'], [])          # judged on the credited quotations alone
        self.assertEqual(latest_levels('run-1')[F1], 'strong')

    def answer_all(self):
        rows = [{'question_id': str(q.pk), 'kind': 'answer', 'answer': 'About 40 hours.', 'supported': True,
                 'document_ids': [DOCUMENT]} for q in DepthQuestion.objects.filter(kind='depth')]
        load_responses(rows, commit=True)

    def test_a_second_depth_job_keeps_judgments_whose_answers_have_not_changed(self):
        data = export(credited={F1: 1, F2: 1})
        create_questions(data, FakeModel(), commit=True)
        self.answer_all()
        judge_run(data, FakeModel(), commit=True)
        self.assertEqual(latest_levels('run-1')[F1], 'substantiated')
        second = Strong()
        result = judge_run(data, second, commit=True)   # no new answers in between
        self.assertFalse([n for n, _ in second.calls if n == 'depth_judgment'])   # nothing paid for again
        self.assertEqual(latest_levels('run-1')[F1], 'substantiated')           # level unchanged
        self.assertEqual(sorted(result['kept']), sorted([F1, F2]))
        self.assertEqual(result['judged'], [])
        self.assertEqual(DepthJudgment.objects.filter(condition_id=F1).count(), 1)
        self.assertEqual(DepthPastCase.objects.filter(condition_id=F1).count(), 1)

    def test_a_new_answer_is_judged_again(self):
        data = export(credited={F1: 1, F2: 1})
        create_questions(data, FakeModel(), commit=True)
        self.answer_all()
        judge_run(data, FakeModel(), commit=True)
        # A later answer to one of F1's questions (for example a follow-up answer): F1 is judged again.
        question = DepthQuestion.objects.filter(kind='depth', condition_ids__0=F1).first()
        load_responses([{'question_id': str(question.pk), 'kind': 'answer', 'answer': 'An accredited programme.',
                         'supported': True, 'document_ids': [DOCUMENT]}], commit=True)
        model = Strong()
        result = judge_run(data, model, commit=True)
        self.assertIn(F1, [j['condition_id'] for j in result['judged']])
        self.assertEqual(latest_levels('run-1')[F1], 'strong')

    def test_requirements_shown_by_their_quotations_are_judged_once(self):
        data = export(credited={F1: 1})
        create_questions(data, AllShownModel(), commit=True)
        judge_run(data, AllShownModel(), commit=True)
        model = AllShownModel()
        result = judge_run(data, model, commit=True)
        self.assertFalse([n for n, _ in model.calls if n == 'depth_judgment'])
        self.assertEqual(result['kept'], [F1])


from .models import CapabilityRun, SecondLayerJob   # noqa: E402
from .test_product_flow import ATTACHMENT, SETTINGS, ProductFlowTests   # noqa: E402


@override_settings(**SETTINGS)
class ClosingFixes(ProductFlowTests):
    """Audit bugs 5, 6 and 7: a closed follow-up stage, set only by closing; no final label or tier without it; held
    credit wording that knows the stage is closed. Reuses the product-flow harness: run the methods below by name
    (the class also inherits the product-flow tests)."""

    def jobs_url(self, run):
        return f'{self.base}/{run.pk}/second-layer/jobs'

    def answer_missing(self, provisional):
        self.post(self.jobs_url(provisional), {'operation': 'questions'}, key='plan', expect=202)
        self.run_queued()
        question = DepthQuestion.objects.filter(run_ref=str(provisional.pk), kind='missing').order_by('rank').first()
        self.post(f'{self.base}/{provisional.pk}/questions/{question.pk}/responses',
                  {'answer': 'Our register.', 'document_ids': [self.document(ATTACHMENT)]}, expect=201)
        self.run_queued()
        return question

    def test_fix_evidence_report_shows_no_tier_eligibility_at_stage_one(self):
        provisional = self.assess()
        html = self.client.get(f'{self.base}/{provisional.pk}/report', {'audience': 'evidence', 'file': 'html'})
        self.assertNotIn('Current eligibility', html.content.decode())
        from unittest.mock import patch
        from .capability import pdf_report
        written, original = [], pdf_report.Report.paragraph

        def capture(pdf, value, **kwargs):
            written.append(value)
            return original(pdf, value, **kwargs)
        with patch.object(pdf_report.Report, 'paragraph', capture):
            self.client.get(f'{self.base}/{provisional.pk}/report', {'audience': 'evidence', 'file': 'pdf'})
        self.assertTrue(written)
        self.assertFalse([t for t in written if 'Pillar floor' in t or 'no badge awarded' in t])
        closed = self.close(provisional)
        html = self.client.get(f'{self.base}/{closed.final_run_id}/report', {'audience': 'evidence', 'file': 'html'})
        self.assertIn('Current eligibility', html.content.decode())   # the final score shows it

    def close(self, provisional, key='close'):
        self.post(self.jobs_url(provisional), {'operation': 'rejudge', 'options': {'close': True}}, key=key, expect=202)
        job = self.run_queued()[0]
        self.assertIsNotNone(job.final_run_id, job.result)
        return job

    def test_fix_a_re_judge_without_close_publishes_nothing(self):
        provisional = self.assess()
        self.answer_missing(provisional)
        self.post(self.jobs_url(provisional), {'operation': 'rejudge'}, key='preview', expect=202)
        job = self.run_queued()[0]
        self.assertIsNone(job.final_run_id)
        self.assertTrue(job.result['targets'])                 # it still reports what would change
        self.assertIn('Preview only', job.result['note'])
        self.assertFalse(CapabilityRun.objects.filter(inputs__second_layer__provisional_run_id=str(provisional.pk)).exists())
        # Publishing without closing is refused outright, so the front end's old button cannot publish by accident.
        self.post(self.jobs_url(provisional), {'operation': 'rejudge', 'options': {'publish': True}}, key='publish',
                  expect=400)

    def test_fix_after_closing_nothing_more_is_accepted(self):
        provisional = self.assess()
        question = self.answer_missing(provisional)
        self.close(provisional)
        progress = self.client.get(f'{self.base}/{provisional.pk}/questions').data['progress']
        self.assertTrue(progress['closed'])
        other = DepthQuestion.objects.filter(run_ref=str(provisional.pk), status='open').exclude(pk=question.pk).first()
        response = self.post(f'{self.base}/{provisional.pk}/questions/{other.pk}/responses', {'skip': True}, expect=400)
        self.assertIn('closed', response.data['detail'])
        self.post(f'{self.base}/{provisional.pk}/additional-evidence',
                  {'document_ids': [self.document(ATTACHMENT)], 'picked': ['AIQIF-C1.1']}, expect=400)
        for operation, options in (('rejudge', {'close': True}), ('depth', {}), ('questions', {'replace': True})):
            self.post(self.jobs_url(provisional), {'operation': operation, 'options': options},
                      key=f'after-{operation}', expect=400)
        self.post(self.jobs_url(provisional), {'operation': 'explain', 'options': {'final': True}}, key='explain-again',
                  expect=202)   # explanations can still be written again
        finals = CapabilityRun.objects.filter(inputs__second_layer__provisional_run_id=str(provisional.pk))
        self.assertEqual(finals.count(), 1)

    def test_fix_closing_waits_for_checks_and_depth(self):
        provisional = self.assess()
        self.post(self.jobs_url(provisional), {'operation': 'questions'}, key='plan', expect=202)
        self.run_queued()
        depth_q = DepthQuestion.objects.filter(run_ref=str(provisional.pk), kind='depth', status='open').first()
        self.post(f'{self.base}/{provisional.pk}/questions/{depth_q.pk}/responses',
                  {'answer': 'The register.', 'document_ids': [self.document(ATTACHMENT)]}, expect=201)
        self.queued.clear()   # the check has not run yet: its job is cancelled before it starts
        from .capability.second_layer_jobs import finish
        for job in SecondLayerJob.objects.filter(run=provisional, status__in=('queued', 'running')):
            finish(job.pk, 'cancelled', 'cancelled_by_user')
        self.post(self.jobs_url(provisional), {'operation': 'rejudge', 'options': {'close': True}}, key='early',
                  expect=400)
        self.post(self.jobs_url(provisional), {'operation': 'checks'}, key='checks', expect=202)
        self.run_queued()
        self.post(self.jobs_url(provisional), {'operation': 'rejudge', 'options': {'close': True}}, key='before-depth',
                  expect=400)   # the checked answer has not been judged for depth
        self.post(self.jobs_url(provisional), {'operation': 'depth'}, key='depth', expect=202)
        self.run_queued()
        self.close(provisional)

    def test_fix_held_credit_wording_knows_the_stage_is_closed(self):
        provisional = self.assess()
        before = self.client.get(f'{self.base}/{provisional.pk}/report', {'audience': 'leadership', 'file': 'html'})
        self.assertIn('Answering them can raise this score to', before.content.decode())   # Stage 1, still open
        job = self.close(provisional)
        for run_id in (job.final_run_id, provisional.pk):
            for audience in ('leadership', 'evidence'):
                text = self.client.get(f'{self.base}/{run_id}/report', {'audience': audience, 'file': 'html'}).content.decode()
                self.assertNotIn('Answering them can raise this score', text, (run_id, audience))
                self.assertNotIn('held until your follow-up answers show', text, (run_id, audience))
            records = self.client.get(f'{self.base}/{run_id}').data['assessment']['records']
            self.assertFalse([r for r in records if 'held until your follow-up answers'
                              in str((r.get('explanation') or {}).get('follow_up'))])
        text = self.client.get(f'{self.base}/{job.final_run_id}/report', {'audience': 'leadership', 'file': 'html'}).content.decode()
        self.assertIn('stays held: the follow-up stage is closed', text)


from .test_tie_break import A, SOURCES, QuoteRepairTests, rubric as one_indicator   # noqa: E402


class QuoteRepairFixes(SimpleTestCase):
    """Audit bug 3: the quotation repair runs only when every found part of a requirement failed its quotation."""

    class OneMisquoted(QuoteRepairTests.Service):
        def extract_structured_data(self, *, system_prompt, user_content, response_schema, schema_name):
            out = super().extract_structured_data(system_prompt=system_prompt, user_content=user_content,
                                                  response_schema=response_schema, schema_name=schema_name)
            if len(self.calls) == 1:   # first pass: the first part quoted exactly, the others misquoted
                for f in out['conditions'][A]['findings'][1:]:
                    f['citations'] = [{'source_id': f['citations'][0]['source_id'], 'quote': 'not on the page at all'}]
            return out

    def evaluate(self, service):
        from .capability.evaluation import evaluate
        return evaluate(SOURCES, service=service, population='Students', reference_period='2023-24',
                        rubric=one_indicator(), retrieval_policy={'mode': 'bm25'}, agreement_passes=2,
                        judgment='parts', tie_break=True, quote_repair=True)

    def test_one_misquoted_part_beside_a_validated_one_is_not_repaired(self):
        service = self.OneMisquoted(bad_quote_calls=set())
        result = self.evaluate(service)
        self.assertNotIn('quote_repair_audit', result['traces'][0])
        self.assertFalse([p for p in service.payloads if 'quotation_repair' in p])

    def test_every_found_part_misquoted_is_still_repaired(self):
        service = QuoteRepairTests.Service(bad_quote_calls={0})
        result = self.evaluate(service)
        self.assertEqual(result['traces'][0]['quote_repair_audit'][0]['pass'], 'first')
