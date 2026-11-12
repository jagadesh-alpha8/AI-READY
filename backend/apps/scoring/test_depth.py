"""Follow-up questions about the depth of evidence (depth.py, depth_service.py; skeleton).

The model is a stand-in: these tests check the plumbing and the deterministic rules (which conditions get questions,
what the model's output is allowed to do, the open-decision policies, the arithmetic, what is saved). Whether a real
model ranks a weak and a strong programme correctly is the phase-2 check, run with the fixtures in
docs/capability/depth_fixtures/.
"""
import io
import json
from fractions import Fraction
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from .capability import depth, depth_spec
from .capability.decision_causes import NOT_EVALUATED
from .capability.depth_service import (DepthError, create_questions, depth_report, judge_run, load_responses)
from .capability.engine import release
from .models import DepthJudgment, DepthPastCase, DepthQuestion, DepthResponse

WEAK = 'Three faculty members attended a three-session workshop on AI at a local institute in 2023.'
F1 = 'AIQIF-C4.1.F1'   # An AI-focused faculty learning activity has defined content.
F2 = 'AIQIF-C4.1.F2'   # Participation ... is documented for an identified faculty group.
SYLLABUS = 'AIQIF-C3.1.F1'


def export(run_id='run-1', credited=None, unjudged=()):
    """An assessment export with every condition uncredited except `credited` {condition_id: credit}."""
    rubric = release()
    credited = credited or {}
    records = []
    for indicator in rubric['indicators']:
        for condition in indicator['conditions']:
            cid = condition['id']
            credit = credited.get(cid, 0)
            record = {'condition_id': cid, 'state': 'met' if credit == 1 else 'unknown', 'credit': credit,
                      'parts': [{'id': 'p1', 'finding': 'full' if credit else 'not_found',
                                 'credited_as': 'full' if credit else 'not_found',
                                 'citations': [{'source_id': 's1', 'quote': WEAK}] if credit else []}]}
            if cid in unjudged:
                record['cause'] = NOT_EVALUATED
            records.append(record)
    return {'run_id': run_id, 'rubric': rubric, 'assessment': {'records': records}}


class FakeModel:
    """Questions: one per dimension, plus a question about an unknown dimension and one about a dimension the
    evidence answers (both must be dropped). Judgment: 'strong' when an answer mentions an accredited programme,
    'substantiated' when it gives hours, else 'evidenced'; flags from the answers."""
    model_name = 'fake'

    def __init__(self):
        self.calls = []

    def __call__(self, system_prompt, user_content, response_schema, schema_name):
        payload = json.loads(user_content)
        self.calls.append((schema_name, payload))
        if schema_name == 'depth_questions':
            dims = [d['id'] for d in payload['dimensions']]
            return {'dimensions': [{'dimension_id': d, 'answered_by_evidence': d == dims[0], 'evidence_quote': WEAK}
                                   for d in dims],
                    'questions': ([{'dimension_ids': [d], 'text': f'About the workshop: {d}?'} for d in dims]
                                  + [{'dimension_ids': ['bogus'], 'text': 'Unknown dimension'}])}
        answers = ' '.join(e['answer'] for e in payload['follow_up'])
        level = 'strong' if 'accredited' in answers else 'substantiated' if 'hours' in answers else 'evidenced'
        return {'level': level, 'contradicts_evidence': 'never ran' in answers,
                'relies_on_unsupported': not all(e['supported'] for e in payload['follow_up']),
                'dimension_findings': [{'dimension_id': payload['dimensions'][0]['id'], 'finding': 'stated'},
                                       {'dimension_id': 'bogus', 'finding': 'dropped'}],
                'reason': 'test'}


class SpecTests(SimpleTestCase):
    def test_spec_covers_the_rubric_and_matches_its_source(self):
        built = depth_spec.build()
        self.assertEqual(len(built['indicators']), 36)
        self.assertEqual(sum(len(i['conditions']) for i in built['indicators'].values()), 216)
        on_disk = json.loads((Path(depth_spec.__file__).parent / depth.SPEC_FILE).read_text(encoding='utf-8'))
        self.assertEqual(on_disk, json.loads(json.dumps(built)), 'Regenerate depth_spec_v0.json from depth_spec.py.')

    def test_spec_is_marked_as_an_unapproved_draft(self):
        self.assertEqual(depth.spec()['status'], 'draft-model-written')

    def test_faculty_readiness_is_open_and_syllabus_standard(self):
        spec = depth.spec()
        self.assertEqual(spec['indicators']['AIQIF-C4.1']['openness'], 'open')
        self.assertEqual(spec['indicators']['AIQIF-C3.1']['openness'], 'standard')


class SelectionTests(SimpleTestCase):
    def test_credited_conditions_rank_by_weight_times_credit(self):
        data = export(credited={F1: 0.4, F2: 1, 'AIQIF-C3.2.F1': 1})   # C3.2 carries half C4.1's weight
        targets, _ = depth.select_targets(data['assessment']['records'], data['rubric'])
        self.assertEqual([t['condition_ids'][0] for t in targets], [F2, 'AIQIF-C3.2.F1', F1])
        self.assertAlmostEqual(targets[0]['impact'], 31.25 / 6)

    def test_uncredited_conditions_are_grouped_per_indicator_and_capped(self):
        data = export(credited={F1: 1}, unjudged={'AIQIF-C1.1.F1'})
        _, missing = depth.select_targets(data['assessment']['records'], data['rubric'], missing_slots=10)
        self.assertEqual(len(missing), 10)
        c41 = [m for m in depth.select_targets(data['assessment']['records'], data['rubric'],
                                               max_questions=36, missing_slots=36)[1] if m['indicator'] == 'AIQIF-C4.1'][0]
        self.assertNotIn(F1, c41['condition_ids'])
        self.assertEqual(len(c41['condition_ids']), 5)
        c11 = [m for m in depth.select_targets(data['assessment']['records'], data['rubric'],
                                               max_questions=36, missing_slots=36)[1] if m['indicator'] == 'AIQIF-C1.1'][0]
        self.assertNotIn('AIQIF-C1.1.F1', c11['condition_ids'], 'an unjudged condition needs a rerun, not a question')

    def test_missing_question_names_each_condition_and_its_evidence_forms(self):
        text = depth.missing_question({'indicator': 'AIQIF-C4.1', 'condition_ids': [F1, F2]})
        self.assertIn('An AI-focused faculty learning activity has defined content.', text)
        self.assertIn('attendance list or participation certificates', text)
        self.assertIn('If you do not have them, please say so.', text)


class QuestionTests(SimpleTestCase):
    def test_model_output_is_checked(self):
        data = export(credited={F1: 1})
        record = data['assessment']['records'][[r['condition_id'] for r in data['assessment']['records']].index(F1)]
        result = depth.questions_for_depth_target({'condition_ids': [F1]}, record, FakeModel())
        dims = [q['dimension_ids'][0] for q in result['questions']]
        self.assertNotIn('bogus', dims)
        self.assertNotIn('content', dims, 'the evidence answered it, so no question')   # F1's first dimension
        self.assertLessEqual(len(result['questions']), 4)   # open indicator cap
        self.assertEqual(result['answered'][0]['dimension_id'], 'content')

    def test_the_model_sees_the_credited_quotes_and_the_condition_dimensions(self):
        data = export(credited={F1: 1})
        model = FakeModel()
        record = [r for r in data['assessment']['records'] if r['condition_id'] == F1][0]
        depth.questions_for_depth_target({'condition_ids': [F1]}, record, model)
        payload = model.calls[0][1]
        self.assertEqual(payload['quotes'][0]['quote'], WEAK)
        self.assertEqual([d['id'] for d in payload['dimensions']], ['content', 'provider', 'intensity'])

    def test_budget_is_shared_and_conditions_are_kept_whole(self):
        data = export(credited={F1: 1, F2: 1})
        targets, missing = depth.select_targets(data['assessment']['records'], data['rubric'], max_questions=6,
                                                missing_slots=2)
        by_id = {r['condition_id']: r for r in data['assessment']['records']}
        planned, notes = depth.plan_questions(targets, missing, by_id, FakeModel(), max_questions=6)
        # 2 reserved missing-evidence questions; F1 asks 2 (content is answered); F2's 3 do not fit the 2 left.
        self.assertEqual(sum(q['kind'] == 'missing' for q in planned), 2)
        self.assertEqual([q['condition_ids'] for q in planned if q['kind'] == 'depth'], [[F1], [F1]])
        self.assertTrue(any(F2 in n and 'do not fit' in n for n in notes))
        self.assertEqual([q['rank'] for q in planned], list(range(1, 5)))

    def test_call_limit(self):
        data = export(credited={F1: 1, F2: 1})
        targets, _ = depth.select_targets(data['assessment']['records'], data['rubric'])
        by_id = {r['condition_id']: r for r in data['assessment']['records']}
        model = FakeModel()
        depth.plan_questions(targets, [], by_id, model, max_calls=1)
        self.assertEqual(len(model.calls), 1)


class PolicyTests(SimpleTestCase):
    def judged(self, level='strong', contradicts=False, unsupported=False):
        return {'level': level, 'contradicts_evidence': contradicts, 'relies_on_unsupported': unsupported}

    def test_answers_lower_a_score_only_on_contradiction(self):
        self.assertEqual(depth.apply_policy(self.judged(contradicts=True)), 'withdrawn')
        self.assertEqual(depth.apply_policy(self.judged(contradicts=True), lowering='never'), 'strong')
        self.assertEqual(depth.apply_policy(self.judged('evidenced')), 'evidenced')

    def test_unsupported_answers(self):
        # Decision 3 (Harsha): an answer without a document counts for nothing, so the default is 'ignore'.
        self.assertEqual(depth.apply_policy(self.judged(unsupported=True)), 'evidenced')
        self.assertEqual(depth.apply_policy(self.judged('substantiated', unsupported=True)), 'evidenced')
        self.assertEqual(depth.apply_policy(self.judged(unsupported=False)), 'strong')
        self.assertEqual(depth.apply_policy(self.judged(unsupported=True), unsupported='cap_one_level'), 'substantiated')
        self.assertEqual(depth.apply_policy(self.judged(unsupported=True), unsupported='same'), 'strong')

    def test_typed_answers_without_documents_are_not_counted(self):
        exchanges = [{'kind': 'answer', 'answer': 'A 300-hour accredited programme.', 'supported': False},
                     {'kind': 'answer', 'answer': 'About 40 hours; register attached.', 'supported': True},
                     {'kind': 'upload', 'answer': '', 'supported': True},
                     {'kind': 'dont_know', 'answer': '', 'supported': False}]
        self.assertEqual([e['kind'] for e in depth.counted_exchanges(exchanges)], ['answer', 'upload', 'dont_know'])
        self.assertNotIn('accredited', ' '.join(e['answer'] for e in depth.counted_exchanges(exchanges)))

    def test_unknown_policy_is_refused(self):
        with self.assertRaises(ValueError):
            depth.apply_policy(self.judged(), lowering='sometimes')

    def test_credit_is_unchanged_until_decision_two_is_reserve(self):
        for mode in ('', 'separate'):
            self.assertEqual(depth.depth_credit(1, 'strong', mode=mode), 1)
            self.assertEqual(depth.depth_credit(Fraction(1, 2), 'evidenced', mode=mode), Fraction(1, 2))

    def test_reserved_credit(self):
        self.assertEqual(depth.depth_credit(1, 'evidenced', mode='reserve', share='0.4'), Fraction(3, 5))
        self.assertEqual(depth.depth_credit(1, 'substantiated', mode='reserve', share='0.4'), Fraction(4, 5))
        self.assertEqual(depth.depth_credit(1, 'strong', mode='reserve', share='0.4'), 1)
        self.assertEqual(depth.depth_credit(1, 'withdrawn', mode='reserve', share='0.4'), 0)
        with self.assertRaises(ValueError):
            depth.depth_credit(1, 'strong', mode='reserve', share='2')

    def test_depth_index(self):
        data = export(credited={F1: 1, F2: 1})
        records = data['assessment']['records']
        self.assertEqual(depth.depth_index({}, records, data['rubric']), 0)
        self.assertEqual(depth.depth_index({F1: 'strong', F2: 'substantiated'}, records, data['rubric']), 75)
        self.assertIsNone(depth.depth_index({}, export()['assessment']['records'], data['rubric']))


DOCUMENT = '00000000-0000-0000-0000-00000000d0c1'


@override_settings(DEPTH_MAX_QUESTIONS=8, DEPTH_MISSING_QUESTION_SLOTS=2)
class FlowTests(TestCase):
    def setUp(self):
        self.data = export(credited={F1: 1, F2: 1})

    def answer_all(self, text, supported=True):
        rows = [{'question_id': str(q.pk), 'kind': 'answer', 'answer': text, 'supported': supported,
                 'document_ids': [DOCUMENT] if supported else []}
                for q in DepthQuestion.objects.filter(kind='depth')]
        return load_responses(rows, commit=True, via='consultant')

    def test_dry_run_saves_nothing(self):
        result = create_questions(self.data, FakeModel())
        self.assertFalse(result['saved'])
        self.assertTrue(result['questions'])
        self.assertFalse(DepthQuestion.objects.exists())

    def test_strong_answers_with_documents_reach_strong(self):
        create_questions(self.data, FakeModel(), commit=True)
        self.assertEqual(DepthQuestion.objects.filter(kind='missing').count(), 2)
        self.answer_all('A 300-hour accredited programme; certificates attached.')
        result = judge_run(self.data, FakeModel(), commit=True)
        self.assertEqual({r['final_level'] for r in result['judged']}, {'strong'})
        self.assertEqual(DepthPastCase.objects.filter(status='proposed').count(), 2)
        self.assertEqual(DepthJudgment.objects.get(condition_id=F1).dimension_findings[0]['finding'], 'stated')
        self.assertEqual(len(DepthJudgment.objects.get(condition_id=F1).dimension_findings), 1)

    def test_strong_answers_without_documents_count_for_nothing(self):
        create_questions(self.data, FakeModel(), commit=True)
        self.answer_all('A 300-hour accredited programme.', supported=False)
        model = FakeModel()
        result = judge_run(self.data, model, commit=True)
        # Nothing reaches the judge, no judgment is stored, and both conditions stay where the provisional score put them.
        self.assertEqual(result['judged'], [])
        self.assertEqual(result['answers_without_documents'], sorted([F1, F2]))
        self.assertFalse([n for n, _ in model.calls if n == 'depth_judgment'])
        self.assertFalse(DepthJudgment.objects.exists())
        report = depth_report(self.data)
        self.assertEqual(report['credited_conditions_by_level']['strong'], 0)

    @override_settings(DEPTH_UNSUPPORTED_ANSWERS='cap_one_level')
    def test_strong_answers_without_documents_drop_one_level_when_capped(self):
        create_questions(self.data, FakeModel(), commit=True)
        self.answer_all('A 300-hour accredited programme.', supported=False)
        result = judge_run(self.data, FakeModel())
        self.assertEqual({r['final_level'] for r in result['judged']}, {'substantiated'})

    def test_dont_know_leaves_it_evidenced_and_unanswered_is_listed(self):
        create_questions(self.data, FakeModel(), commit=True)
        question = [q for q in DepthQuestion.objects.filter(kind='depth') if q.condition_ids == [F1]][0]
        load_responses([{'question_id': str(question.pk), 'kind': 'dont_know'}], commit=True)
        result = judge_run(self.data, FakeModel())
        self.assertEqual([r['final_level'] for r in result['judged']], ['evidenced'])
        self.assertEqual(result['unanswered'], [F2])

    def test_approved_past_cases_reach_the_next_judgment(self):
        create_questions(self.data, FakeModel(), commit=True)
        self.answer_all('About 40 hours over a semester.')
        judge_run(self.data, FakeModel(), commit=True)
        DepthPastCase.objects.filter(condition_id=F1).update(status='approved')
        later = export('run-2', credited={F1: 1})
        create_questions(later, FakeModel(), commit=True)
        rows = [{'question_id': str(q.pk), 'kind': 'answer', 'answer': 'About 40 hours.', 'supported': True,
                 'document_ids': [DOCUMENT]} for q in DepthQuestion.objects.filter(run_ref='run-2', kind='depth')]
        load_responses(rows, commit=True)
        model = FakeModel()
        result = judge_run(later, model)
        judged_payload = [p for name, p in model.calls if name == 'depth_judgment'][0]
        self.assertEqual(judged_payload['approved_past_cases'][0]['level'], 'substantiated')
        self.assertEqual(len(result['judged'][0]['past_case_ids']), 1)

    def test_proposed_past_cases_do_not_guide_judgments(self):
        create_questions(self.data, FakeModel(), commit=True)
        self.answer_all('About 40 hours.')
        judge_run(self.data, FakeModel(), commit=True)
        model = FakeModel()
        judge_run(self.data, model)
        self.assertEqual([p['approved_past_cases'] for n, p in model.calls if n == 'depth_judgment'], [[], []])

    def test_uploads_for_missing_evidence_await_reassessment(self):
        create_questions(self.data, FakeModel(), commit=True)
        missing = DepthQuestion.objects.filter(kind='missing').first()
        load_responses([{'question_id': str(missing.pk), 'kind': 'upload', 'document_ids': ['doc-1']}], commit=True)
        result = judge_run(self.data, FakeModel())
        self.assertEqual(result['awaiting_reassessment'][0]['conditions'], missing.condition_ids)
        self.assertTrue(DepthResponse.objects.get().supported)

    def test_fixture_answers_load_by_condition(self):
        from django.core.management import call_command
        create_questions(self.data, FakeModel(), commit=True)
        fixtures = Path(__file__).resolve().parents[3] / 'docs' / 'capability' / 'depth_fixtures'
        for name, supported in (('faculty_training_weak.json', False), ('faculty_training_strong.json', True)):
            DepthResponse.objects.all().delete()
            call_command('depth_load_responses', str(fixtures / name), by_condition=True, run='run-1', commit=True,
                         stdout=io.StringIO())
            depth_questions = DepthQuestion.objects.filter(kind='depth').count()
            self.assertEqual(DepthResponse.objects.count(), depth_questions)
            self.assertEqual({r.supported for r in DepthResponse.objects.all()}, {supported})

    def test_bad_response_rows_save_nothing(self):
        create_questions(self.data, FakeModel(), commit=True)
        question = DepthQuestion.objects.first()
        with self.assertRaises(DepthError) as caught:
            load_responses([{'question_id': str(question.pk), 'kind': 'answer', 'answer': 'fine'},
                            {'question_id': 'not-a-uuid', 'kind': 'answer', 'answer': 'x'},
                            {'question_id': str(question.pk), 'kind': 'upload'},
                            {'question_id': str(question.pk), 'kind': 'maybe'}], commit=True)
        self.assertIn('row 2', str(caught.exception))
        self.assertIn('row 3', str(caught.exception))
        self.assertIn('row 4', str(caught.exception))
        self.assertFalse(DepthResponse.objects.exists())

    def test_questions_are_not_replaced_once_answered(self):
        create_questions(self.data, FakeModel(), commit=True)
        with self.assertRaises(DepthError):
            create_questions(self.data, FakeModel(), commit=True)
        self.answer_all('About 40 hours.')
        with self.assertRaises(DepthError):
            create_questions(self.data, FakeModel(), commit=True, replace=True)

    def test_report_without_decision_two_changes_no_credit(self):
        create_questions(self.data, FakeModel(), commit=True)
        self.answer_all('A 300-hour accredited programme.')
        judge_run(self.data, FakeModel(), commit=True)
        report = depth_report(self.data)
        self.assertIsNone(report['score_with_depth'])
        self.assertEqual(report['depth_index'], 100)
        self.assertEqual(report['credited_conditions_by_level']['strong'], 2)

    @override_settings(DEPTH_CREDIT_MODE='reserve', DEPTH_CREDIT_SHARE='0.4')
    def test_report_with_reserved_credit(self):
        create_questions(self.data, FakeModel(), commit=True)
        question = [q for q in DepthQuestion.objects.filter(kind='depth') if q.condition_ids == [F1]][0]
        load_responses([{'question_id': str(question.pk), 'kind': 'answer', 'answer': 'accredited', 'supported': True,
                         'document_ids': [DOCUMENT]}],
                       commit=True)
        judge_run(self.data, FakeModel(), commit=True)
        report = depth_report(self.data)
        # F1 strong keeps its full credit; F2 has no judgment, stays evidenced and keeps 60% of its credit.
        self.assertLess(report['score_with_depth'], report['provisional_score'])
        self.assertGreater(report['score_with_depth'], 0)

    @override_settings(DEPTH_CREDIT_MODE='reserve', DEPTH_CREDIT_SHARE='')
    def test_reserve_needs_a_share(self):
        with self.assertRaises(DepthError):
            depth_report(self.data)
