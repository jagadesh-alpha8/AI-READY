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
