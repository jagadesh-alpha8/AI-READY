"""Plan checks (institution-plan-review-1.0): the pipeline, the projection, the limits and the downloads."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.extraction.exceptions import AIOutputTruncated
from apps.extraction.models import AIUsage
from apps.extraction.services.openai_client import OpenAIExtractionService
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .models import CapabilityExecution, InstitutionalPlanVersion, PlanScenario, PlanScenarioExecution
from .capability import plan_credit
from .capability.engine import release
from .capability.evaluation import evaluate
from .capability.plan_execution import claim, evaluate_institutional_plan
from .capability.plan_mapping import (ADDS, ALREADY, DOCUMENTS, MAX_ACTIONS, NEEDS_MORE, NO_MATCH, OVERLAPS,
                                      PlanError, run_pipeline, validate_parsed, wording_problems)
from .capability.storage import checkpoint, create_run, publish

TRAIN = 'Train every teacher in the BBA department on AI tools this term and assess what they can do.'
POLICY = 'The Academic Council approves an AI use policy for students.'
GATHER = 'Collect the attendance sheets from last year\'s AI seminars.'
VAGUE = 'Celebrate AI Day with a poster competition.'
TEXT = '\n'.join(['1. ' + TRAIN, '2. ' + POLICY, '3. ' + GATHER, '4. ' + VAGUE, 'Budget: INR 2,00,000 for the year.'])
FACULTY = 'AIQIF-C4.1.F1'
POLICY_ID = 'AIQIF-C2.1.F1'


def action(n, quote, areas, title=None):
    return {'id': f'a{n}', 'title': title or quote[:40], 'quote': quote, 'areas': areas, 'owner': 'Not stated',
            'timing': 'Not stated', 'resources': 'Not stated'}


class FixtureService:
    """A stand-in model: parses TEXT into four actions, links the first two, and proposes one change and one
    addition. Tests override pieces of it."""

    def __init__(self):
        self.calls = []

    def parse(self, payload):
        return {'actions': [action(1, TRAIN, ['AIQIF-C4']), action(2, POLICY, ['AIQIF-C2']),
                            action(3, GATHER, ['AIQIF-C4']), action(4, VAGUE, ['AIQIF-C5'])],
                'constraints': [{'kind': 'budget', 'quote': 'INR 2,00,000 for the year.'}], 'unclear': []}

    def link(self, payload):
        rows = []
        for a in payload['actions']:
            if a['text'].startswith('Train'):
                rows.append({'action_id': a['id'], 'note': 'Training with an assessment shows the teachers\' AI skills.',
                             'links': [{'practice_id': FACULTY, 'part_ids': ['p1', 'p2', 'p3'], 'phrase': 'assess what they can do',
                                        'documents_only': False}]})
            elif a['text'].startswith('The Academic Council'):
                rows.append({'action_id': a['id'], 'note': 'An approved student AI use policy.',
                             'links': [{'practice_id': POLICY_ID, 'part_ids': ['p1', 'p2'], 'phrase': 'approves an AI use policy',
                                        'documents_only': False}]})
            elif a['text'].startswith('Collect'):
                rows.append({'action_id': a['id'], 'note': 'Only gathers records of past seminars.',
                             'links': [{'practice_id': FACULTY, 'part_ids': ['p1'], 'phrase': 'Collect the attendance sheets',
                                        'documents_only': True}]})
            elif a['text'].startswith('Run the AI Day'):
                rows.append({'action_id': a['id'], 'note': 'Recorded entries show students taking part in AI work.',
                             'links': [{'practice_id': 'AIQIF-C5.1.F1', 'part_ids': ['p1', 'p2'],
                                        'phrase': 'record the entries', 'documents_only': False}]})
            elif a['text'].startswith('The Academic Council reviews'):
                rows.append({'action_id': a['id'], 'note': 'A yearly review of the AI use policy.', 'links': []})
            else:
                rows.append({'action_id': a['id'], 'note': 'A poster competition does not leave a record of AI practice.',
                             'links': []})
        return {'actions': rows}

    def improve(self, payload):
        return {'summary': 'The plan trains BBA teachers and sets a student AI policy. It does not say who reviews '
                           'the policy once it is in use.',
                'changes': [{'operation': 'change', 'action_id': 'a4', 'areas': ['AIQIF-C5'],
                             'text': 'Run the AI Day poster competition on responsible AI use and record the entries.',
                             'why': 'The poster theme then ties the day to the new student AI policy.',
                             'owner': 'the office responsible for student learning and careers',
                             'done_when': 'The entries and the judging sheet are filed.', 'builds_on': []},
                            {'operation': 'add', 'action_id': '', 'areas': ['AIQIF-C2'],
                             'text': 'The Academic Council reviews the AI use policy at the end of the year.',
                             'why': 'A yearly review keeps the policy current.', 'owner': 'Academic Council',
                             'done_when': 'The minutes record the review.', 'builds_on': []}]}

    def extract_structured_data(self, **kwargs):
        name = kwargs['schema_name'].removeprefix('institution_plan_')
        payload = json.loads(kwargs['user_content'])
        self.calls.append((name, payload))
        return getattr(self, name)(payload)


def rubric_inputs(text=TEXT):
    rubric = release()
    return {'plan_text': text, 'rubric': rubric, 'profile': {'name': 'Synthetic College'},
            'population': 'Source-specific', 'reference_period': 'Source-specific'}


def record(cid, credit, parts):
    """A judged record: parts as {part id: (first pass, second pass)}."""
    return {'condition_id': cid, 'state': 'met' if credit >= 1 else 'not_met', 'credit': credit,
            'parts': [{'id': pid, 'credited_as': a, 'second_credited_as': b} for pid, (a, b) in parts.items()]}


class ProjectionTests(SimpleTestCase):
    """The plan is scored by the judge's own credit rule, part by part."""

    def test_supplying_every_unshown_part_completes_the_practice(self):
        r = record(FACULTY, 0.25, {'p1': ('full', 'full'), 'p2': ('full', 'related'), 'p3': ('not_found', 'not_found')})
        self.assertEqual(plan_credit.credit_after(r, {'p2', 'p3'}), 1.0)
        self.assertEqual(plan_credit.credit_after(r, {'p1', 'p2', 'p3'}), 1.0)

    def test_a_part_without_its_gate_earns_nothing(self):
        r = record(FACULTY, 0.0, {'p1': ('not_found', 'not_found'), 'p2': ('not_found', 'not_found'),
                                  'p3': ('not_found', 'not_found')})
        self.assertEqual(plan_credit.credit_after(r, {'p2', 'p3'}), 0.0)   # the activity itself (p1) is a gate

    def test_part_of_a_practice_earns_part_of_its_credit_and_never_lowers_it(self):
        # Training on AI with no defined content: the two gates shown, content not -> half the substantive parts.
        r = record(FACULTY, 0.0, {'p1': ('not_found', 'not_found'), 'p2': ('not_found', 'not_found'),
                                  'p3': ('not_found', 'not_found')})
        self.assertEqual(plan_credit.credit_after(r, {'p1', 'p2'}), 0.5)
        # Content found only as related: the subject shown in full lifts it to the middle step.
        r = record(FACULTY, 0.0, {'p1': ('not_found', 'not_found'), 'p2': ('full', 'full'), 'p3': ('related', 'related')})
        self.assertEqual(plan_credit.credit_after(r, {'p1'}), 0.75)
        strong = record(FACULTY, 0.75, {'p1': ('full', 'full'), 'p2': ('full', 'full'), 'p3': ('full', 'related')})
        self.assertGreaterEqual(plan_credit.credit_after(strong, {'p1'}), 0.75)

    def test_score_matches_the_reported_arithmetic(self):
        from .capability.engine import documented
        rubric = release()
        records = {c['id']: {'condition_id': c['id'], 'credit': 0.0} for i in rubric['indicators'] for c in i['conditions']}
        before = plan_credit.baseline_score(records, rubric)
        after, changed = plan_credit.project(records, {FACULTY: {'p1', 'p2', 'p3'}}, rubric)
        credits = {cid: 0.0 for cid in records}
        self.assertEqual(before, documented(credits, rubric)['overall'])
        self.assertEqual(after, documented({**credits, FACULTY: 1.0}, rubric)['overall'])
        self.assertEqual(changed, {FACULTY: (0.0, 1.0)})


class ParseTests(SimpleTestCase):
    def test_limits_are_trimmed_not_fatal(self):
        text = '\n'.join(f'Step {n}: run an AI session for department {n}.' for n in range(MAX_ACTIONS + 5))
        parsed = {'actions': [action(n, f'Step {n}: run an AI session for department {n}.', ['AIQIF-C4'])
                              for n in range(MAX_ACTIONS + 5)], 'constraints': [], 'unclear': ['x'] * 30}
        result = validate_parsed(parsed, text)
        self.assertEqual(len(result['actions']), MAX_ACTIONS)
        self.assertEqual(len(result['unclear']), 10)
        self.assertTrue(any(f'only the first {MAX_ACTIONS}' in w for w in result['warnings']))

    def test_unfound_quote_is_dropped_and_money_is_registered(self):
        parsed = {'actions': [action(1, TRAIN, ['AIQIF-C4']), action(2, 'Buy a GPU cluster', ['AIQIF-C6'])],
                  'constraints': [], 'unclear': []}
        result = validate_parsed(parsed, TEXT)
        self.assertEqual([a['text'] for a in result['actions']], [TRAIN])
        self.assertIn('could not be found', result['warnings'][0])
        self.assertEqual(result['constraints'][0]['kind'], 'budget')
        self.assertIn('INR 2,00,000', result['constraints'][0]['quote'])

    def test_spans_tolerate_copying_changes(self):
        parsed = {'actions': [action(1, 'train every teacher in the  BBA department', ['AIQIF-C4'])],
                  'constraints': [], 'unclear': []}
        self.assertEqual(validate_parsed(parsed, TEXT)['actions'][0]['text'], 'Train every teacher in the BBA department')


class WordingTests(SimpleTestCase):
    def test_stock_words_codes_and_new_numbers_are_flagged(self):
        problems = wording_problems('Leverage synergies to train 50 staff on AIQIF-C4.1 requirements.',
                                    allowed_numbers='a plan')
        self.assertTrue(any('stock wording' in p for p in problems))
        self.assertTrue(any('internal word' in p for p in problems))
        self.assertTrue(any('"50"' in p for p in problems))

    def test_the_colleges_own_words_are_allowed(self):
        plan = 'Introduce a credit-bearing AI course for 60 students with industry stakeholders.'
        self.assertEqual(wording_problems('Make the credit-bearing course for 60 students count with stakeholders.',
                                          allowed_numbers=plan), [])


class PipelineTests(SimpleTestCase):
    def test_statuses_scores_and_calls(self):
        service = FixtureService()
        result = run_pipeline(rubric_inputs(), service)
        statuses = {a['id']: a['status'] for a in result['original']['actions']}
        self.assertEqual(statuses, {'a1': ADDS, 'a2': ADDS, 'a3': DOCUMENTS, 'a4': NO_MATCH})
        self.assertEqual([n for n, _ in service.calls], ['parse', 'link', 'link', 'link', 'improve', 'link', 'link'])
        scores = result['scores']
        self.assertGreater(scores['plan'], scores['today'])
        self.assertGreater(scores['recommended'], scores['plan'])
        rec = result['recommendation']
        self.assertEqual([a['origin'] for a in rec['actions']], ['kept', 'kept', 'kept', 'changed', 'added'])
        self.assertIn('(added)', result['improved']['text'])
        self.assertIn('INR 2,00,000', result['improved']['text'])
        # Kept actions are not linked again: the second round of link calls holds only the changed and added ones.
        relinked = [a['id'] for n, p in service.calls[5:] for a in p['actions']]
        self.assertEqual(sorted(relinked), ['a4', 'n1'])
        gather = next(a for a in result['original']['actions'] if a['id'] == 'a3')
        self.assertIn('follow-up answers', gather['note'])

    def test_link_calls_see_only_the_areas_their_actions_name(self):
        service = FixtureService()
        run_pipeline(rubric_inputs(), service)
        areas_of = {a['quote']: set(a['areas']) for a in FixtureService().parse({})['actions']}
        for name, payload in service.calls[:4]:
            if name == 'link':
                sent = {a['area_code'] for a in payload['areas']}
                named = set().union(*(areas_of[a['text']] for a in payload['actions']))
                self.assertEqual(sent, named)

    def test_already_shown_and_overlapping_actions(self):
        class Overlap(FixtureService):
            def link(self, payload):
                answer = super().link(payload)
                for row in answer['actions']:
                    if row['action_id'] == 'a3':   # the gathering action now repeats the training action
                        row['links'] = [{'practice_id': FACULTY, 'part_ids': ['p1', 'p2', 'p3'],
                                         'phrase': 'Collect the attendance sheets', 'documents_only': False}]
                return answer
        records = [record(POLICY_ID, 1.0, {'p1': ('full', 'full'), 'p2': ('full', 'full')})]
        result = run_pipeline(rubric_inputs(), Overlap(), records=records)
        statuses = {a['id']: a['status'] for a in result['original']['actions']}
        self.assertEqual(statuses['a2'], ALREADY)
        # Two actions show the same practice: each repeats the other, so neither adds on its own.
        self.assertEqual((statuses['a1'], statuses['a3']), (OVERLAPS, OVERLAPS))
        a3 = next(a for a in result['original']['actions'] if a['id'] == 'a3')
        self.assertIn('already covers the same ground', a3['note'])

    def test_a_link_to_a_part_without_its_gate_needs_another_step(self):
        class Gate(FixtureService):
            def link(self, payload):
                answer = super().link(payload)
                for row in answer['actions']:
                    if row['action_id'] == 'a1':
                        row['links'][0]['part_ids'] = ['p2', 'p3']
                return answer
        result = run_pipeline(rubric_inputs(), Gate())
        a1 = next(a for a in result['original']['actions'] if a['id'] == 'a1')
        self.assertEqual(a1['status'], NEEDS_MORE)
        self.assertIn('counts once your documents also show', a1['note'])

    def test_unknown_practices_parts_and_phrases_are_dropped(self):
        class Bad(FixtureService):
            def link(self, payload):
                answer = super().link(payload)
                for row in answer['actions']:
                    row['links'] = row['links'] + [
                        {'practice_id': 'AIQIF-C9.9.F9', 'part_ids': ['p1'], 'phrase': 'x', 'documents_only': False},
                        {'practice_id': FACULTY, 'part_ids': ['p7'], 'phrase': 'Train', 'documents_only': False},
                        {'practice_id': 'AIQIF-C4.2.F1', 'part_ids': ['p1'], 'phrase': 'words not in it',
                         'documents_only': False}]
                return answer
        result = run_pipeline(rubric_inputs(), Bad())
        links = {a['id']: [l['practice_id'] for l in a['links']] for a in result['original']['actions']}
        self.assertEqual(links['a1'], [FACULTY])
        self.assertEqual(links['a4'], [])

    def test_improvement_stays_within_the_plan(self):
        class Greedy(FixtureService):
            def improve(self, payload):
                add = lambda n, area: {'operation': 'add', 'action_id': '', 'areas': [area],
                                       'text': f'Hold a short AI clinic number {"one two three four five".split()[n]}.',
                                       'why': 'It gives teachers practice.', 'owner': 'Dr. Rao',
                                       'done_when': 'Attendance with results is filed.', 'builds_on': ['P99']}
                return {'summary': 'The plan trains BBA teachers.', 'changes': [
                    {'operation': 'drop', 'action_id': 'a1', 'areas': [], 'text': '', 'why': 'Not needed.',
                     'owner': '', 'done_when': '', 'builds_on': []},
                    {'operation': 'change', 'action_id': 'a2', 'areas': [], 'text': POLICY + ' It spends INR 5,00,000.',
                     'why': 'More money.', 'owner': 'Academic Council', 'done_when': 'Minutes.', 'builds_on': []},
                    add(0, 'AIQIF-C9'), add(1, 'AIQIF-C7'), add(2, 'AIQIF-C4'), add(3, 'AIQIF-C4'), add(4, 'AIQIF-C4')]}
        service = Greedy()
        result = run_pipeline(rubric_inputs(), service)
        changes = result['recommendation']['changes']
        ops = [c['operation'] for c in changes]
        self.assertNotIn('drop', ops)                          # a1 adds to the score: never dropped
        self.assertFalse(any(c['action_id'] == 'a2' for c in changes))   # new money: left out, a2 kept
        adds = [c for c in changes if c['operation'] == 'add']
        self.assertEqual(len(adds), 3)
        self.assertEqual(sum(c['areas'][0] not in {'AIQIF-C4', 'AIQIF-C2', 'AIQIF-C5'} for c in adds), 1)
        self.assertTrue(all(c['owner'] == 'the office responsible for faculty development' or 'responsible' in c['owner']
                            for c in adds))                      # never a person's name
        self.assertTrue(all(c['builds_on'] == [] for c in adds))  # unknown passage ids dropped
        self.assertIn('improve_again', [t['stage'] for t in result['traces']])

    def test_dropping_two_actions_that_repeat_each_other_is_undone(self):
        class Both(FixtureService):
            def link(self, payload):
                answer = super().link(payload)
                for row in answer['actions']:
                    if row['action_id'] == 'a3':
                        row['links'] = [{'practice_id': FACULTY, 'part_ids': ['p1', 'p2', 'p3'],
                                         'phrase': 'Collect the attendance sheets', 'documents_only': False}]
                return answer

            def improve(self, payload):
                return {'summary': 'The plan trains BBA teachers.', 'changes': [
                    {'operation': 'drop', 'action_id': a, 'areas': [], 'text': '', 'why': 'It repeats another action.',
                     'owner': '', 'done_when': '', 'builds_on': []} for a in ('a1', 'a3')]}
        result = run_pipeline(rubric_inputs(), Both())
        self.assertEqual(result['scores']['recommended'], result['scores']['plan'])
        self.assertEqual(result['recommendation']['changes'], [])

    def test_stock_wording_is_asked_again_then_replaced(self):
        class Stock(FixtureService):
            def link(self, payload):
                answer = super().link(payload)
                for row in answer['actions']:
                    row['note'] = 'This will leverage a robust ecosystem.'
                return answer
        service = Stock()
        result = run_pipeline(rubric_inputs(), service)
        a1 = next(a for a in result['original']['actions'] if a['id'] == 'a1')
        self.assertNotIn('leverage', a1['note'])
        self.assertTrue(a1['note'].startswith('Once done, this would show that'))
        self.assertTrue(any('problems_with_your_last_answer' in p for n, p in service.calls if n == 'link'))

    def test_long_link_answers_are_split(self):
        class Truncating(FixtureService):
            def link(self, payload):
                if len(payload['actions']) > 1:
                    raise AIOutputTruncated('too long')
                return super().link(payload)
        result = run_pipeline(rubric_inputs(), Truncating())
        self.assertEqual(next(a for a in result['original']['actions'] if a['id'] == 'a1')['status'], ADDS)

    def test_unusable_answer_is_asked_once_more(self):
        class Flaky(FixtureService):
            first = True

            def parse(self, payload):
                if self.first:
                    self.first = False
                    return {'actions': 'not a list'}
                return super().parse(payload)
        service = Flaky()
        run_pipeline(rubric_inputs(), service)
        self.assertEqual([n for n, _ in service.calls][:2], ['parse', 'parse'])

    def test_a_plan_without_actions_is_refused_plainly(self):
        class Empty(FixtureService):
            def parse(self, payload):
                return {'actions': [], 'constraints': [], 'unclear': []}
        with self.assertRaises(PlanError):
            run_pipeline(rubric_inputs('We are thinking about AI.'), Empty())

    def test_many_actions_in_one_area_are_linked_in_groups(self):
        text = '\n'.join(f'Step {n}: train department {n} on AI.' for n in range(13))

        class Many(FixtureService):
            def parse(self, payload):
                return {'actions': [action(n, f'Step {n}: train department {n} on AI.', ['AIQIF-C4']) for n in range(13)],
                        'constraints': [], 'unclear': []}

            def improve(self, payload):
                return {'summary': 'The plan trains departments one by one.', 'changes': []}
        service = Many()
        run_pipeline(rubric_inputs(text), service)
        self.assertEqual([len(p['actions']) for n, p in service.calls if n == 'link'], [6, 6, 1])


@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_PLANS_ENABLED=True, PLAN_REVIEW_MAX_CALLS=30,
    PLAN_REVIEW_MAX_COST_USD='5', CAPABILITY_OUTPUT_TOKENS=3000, CAPABILITY_REQUEST_TIMEOUT_SECONDS=60,
    AI_RATE_LIMIT_ENABLED=False, AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}', PLAN_EVALUATIONS_PER_SPRINT=10)
class PlanAPITests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Synthetic College')
        self.sprint = Sprint.objects.create(institution=self.institution)
        self.user = User.objects.create_user(username='planner', email='planner@example.com',
            role=User.Role.IQAC_COORDINATOR, institution=self.institution)
        self.client.force_authenticate(self.user)
        from .publication_fixtures import every_result_published
        every_result_published(self)
        self.run = create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk)
        checkpoint(institution_id=self.institution.pk, run_id=self.run.pk, state='running')
        self.event = publish(institution_id=self.institution.pk, run_id=self.run.pk,
            evaluation=evaluate([], service=None, population='Source-specific', reference_period='Source-specific'),
            inference={'provider': 'none', 'model': 'none', 'settings': {}, 'calls': []})
        CapabilityExecution.objects.create(run=self.run, sprint=self.sprint, idempotency_key='baseline', request_hash='baseline', status='completed')
        self.url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{self.run.pk}/plan-evaluations'
        self.fixture = FixtureService()
        self.sdk = MagicMock()
        self.sdk.with_options.return_value = self.sdk

        def response(**kwargs):
            schema_name = kwargs['response_format']['json_schema']['name']
            value = self.fixture.extract_structured_data(schema_name=schema_name,
                                                         user_content=kwargs['messages'][1]['content'])
            return SimpleNamespace(model='actual-model', usage=SimpleNamespace(prompt_tokens=200, completion_tokens=150,
                prompt_tokens_details=None, completion_tokens_details=None, total_tokens=350),
                choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(value), refusal=None))])
        self.sdk.chat.completions.create.side_effect = response

    def start(self, text=TEXT, key='plan1', expect=202):
        with patch('apps.scoring.capability.plan_execution.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, {'plan_text': text}, format='json', HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(response.status_code, expect, getattr(response, 'data', response))
        if expect != 202:
            return response
        return PlanScenarioExecution.objects.get(scenario_id=response.data['id'])

    def execute(self, execution):
        service = OpenAIExtractionService(api_key='sk-test', model='test-model', client=self.sdk)
        with patch('apps.scoring.capability.plan_execution.get_ai_service', return_value=service), patch(
                'apps.scoring.capability.plan_execution.get_router_pool', return_value=None):
            evaluate_institutional_plan.run(str(execution.scenario_id), str(execution.task_id))
        execution.refresh_from_db()
        return execution

    def test_full_check_downloads_and_baseline_unchanged(self):
        old_inputs, old_payload = deepcopy(self.run.inputs), deepcopy(self.event.payload)
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'completed')
        calls = self.sdk.chat.completions.create.call_count
        self.assertEqual(execution.requests_reserved, calls)
        self.assertEqual(AIUsage.objects.filter(capability_run=self.run, plan_scenario=execution.scenario).count(), calls)
        self.assertEqual(InstitutionalPlanVersion.objects.count(), 2)
        url = self.url + '/' + str(execution.scenario_id)
        detail = self.client.get(url)
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertFalse(detail.data['legacy'])
        with patch('apps.scoring.capability.publication.is_staff', lambda user: False):
            college = self.client.get(url)
            self.assertNotIn('traces', college.data['review'])         # internal, not for a college
            self.assertNotIn('internal_notes', college.data['review']['recommendation'])
            self.assertIsNone(college.data['inference'])
            self.assertEqual(self.client.get(url + '/report?file=json').status_code, 400)   # staff only
        self.assertEqual(self.client.get(url + '/report?file=json').status_code, 200)
        pdf = self.client.get(url + '/report?file=pdf')
        self.assertEqual(pdf.status_code, 200)
        self.assertIn(pdf['Content-Type'], ('application/pdf', 'text/html; charset=utf-8'))
        page = self.client.get(url + '/report?file=html')
        for words in (b'What works', b'What we recommend', b'How to read this', b'Your plan with our changes',
                      b'Synthetic College', b'INR 2,00,000'):
            self.assertIn(words, page.content)
        word = self.client.get(url + '/report?file=docx')
        self.assertEqual(word.status_code, 200)
        self.assertTrue(word.content.startswith(b'PK'))
        self.run.refresh_from_db(); self.event.refresh_from_db()
        self.assertEqual(self.run.inputs, old_inputs)
        self.assertEqual(self.event.payload, old_payload)
        listing = self.client.get(self.url)
        self.assertEqual(listing.data['limits']['used'], 1)
        self.assertEqual(listing.data['limits']['limit'], 10)
        retry = self.client.post(self.url, {'plan_text': TEXT}, format='json', HTTP_IDEMPOTENCY_KEY='plan1')
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.data['reused'])
        self.assertEqual(self.client.post(self.url, {'plan_text': 'Changed'}, format='json',
                                          HTTP_IDEMPOTENCY_KEY='plan1').status_code, 409)

    @override_settings(PLAN_EVALUATIONS_PER_SPRINT=2)
    def test_usage_limit_counts_done_and_cancelled_checks_not_failed_ones(self):
        self.execute(self.start(key='k1'))
        with override_settings(PLAN_REVIEW_MAX_CALLS=1):   # frozen into the check when it starts
            failed = self.execute(self.start(key='k2'))
        self.assertEqual(failed.status, 'failed')
        self.assertIn('not counted', self.client.get(self.url + '/' + str(failed.scenario_id)).data['error']['next_action'])
        cancelled = self.start(key='k3')
        self.client.post(self.url + '/' + str(cancelled.scenario_id) + '/cancel')
        refused = self.start(key='k4', expect=429)
        self.assertIn('Usage limit reached', str(refused.data))
        self.assertEqual(self.client.get(self.url).data['limits'], {'used': 2, 'limit': 2, 'remaining': 0,
                                                                   'max_chars': 40000, 'max_actions': MAX_ACTIONS})

    def test_a_plan_that_is_too_long_is_refused_before_any_call(self):
        refused = self.start(text='x' * 40001, key='long', expect=400)
        self.assertIn('about 12 pages', str(refused.data))
        self.assertFalse(PlanScenario.objects.exists())

    def test_a_check_that_stops_part_way_keeps_its_first_half(self):
        with override_settings(PLAN_REVIEW_MAX_CALLS=4):
            execution = self.execute(self.start())
        self.assertEqual(execution.status, 'failed')
        detail = self.client.get(self.url + '/' + str(execution.scenario_id))
        self.assertIsNone(detail.data['review'])
        self.assertEqual(len(detail.data['original_review']['actions']), 4)

    def test_tenant_mismatch_and_cancelled_late_delivery(self):
        execution = self.start()
        url = self.url + '/' + str(execution.scenario_id)
        other = Institution.objects.create(name='Other')
        self.user.institution = other; self.user.save()
        for suffix in ['', '/report', '/report?file=docx']:
            self.assertEqual(self.client.get(url + suffix).status_code, 403)
        self.user.institution = self.institution; self.user.save()
        self.assertEqual(self.client.post(url + '/cancel').status_code, 200)
        self.execute(execution)
        self.assertEqual(execution.status, 'cancelled')
        self.assertFalse(self.sdk.chat.completions.create.called)
        self.assertIsNone(claim(execution.scenario_id, 'wrong-task'))

    def test_immutable_records(self):
        execution = self.execute(self.start())
        scenario = execution.scenario
        with self.assertRaises(ValueError):
            scenario.save()
        with self.assertRaises(ValueError):
            PlanScenario.objects.filter(pk=scenario.pk).update(inputs={})
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('UPDATE scoring_institutionalplanversion SET text_hash = %s WHERE id = %s',
                           ['wrong', scenario.plan.pk.hex if connection.vendor == 'sqlite' else scenario.plan.pk])
        self.assertEqual(self.client.get(self.url + '/' + str(scenario.pk) + '/report').status_code, 409)

    @override_settings(CAPABILITY_PLANS_ENABLED=False)
    def test_feature_disabled(self):
        response = self.client.post(self.url, {'plan_text': TEXT}, format='json', HTTP_IDEMPOTENCY_KEY='disabled')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.client.get(self.url).data['enabled'])
