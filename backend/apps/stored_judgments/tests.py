"""Stored judgments: an identical Stage 1 request in a later run reuses the earlier run's answer. No provider calls."""
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.extraction.services.openai_client import OpenAIExtractionService
from apps.scoring.capability.execution import policy
from apps.scoring.capability.provider import MeteredService
from apps.scoring.capability.second_layer_jobs import SecondLayerMeter

from .models import StoredAnswer
from .store import VERSION, RunAnswers, request_hash

SCHEMA = {'type': 'object'}


def reply(content):
    return SimpleNamespace(
        model='gpt-6-luna', usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                                                   prompt_tokens_details=None, completion_tokens_details=None),
        choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=content, refusal=None))])


@override_settings(AI_RATE_LIMIT_ENABLED=False, AI_PRICING_JSON='')
class ReuseTests(TestCase):
    def policy(self, **extra):
        return {'max_duration_seconds': 600, 'output_tokens': 1000, 'timeout_seconds': 60, 'stage': 'assessment',
                'input_token_bound_limit': 1000000, 'gemini_reasoning_effort': 'high', 'model_effort': 'low',
                'stored_judgments': VERSION, **extra}

    def run_meter(self, answers, policy=None, model='gpt-6-luna'):
        """A meter for a fresh run whose model answers `answers` in turn; returns (meter, sdk, events)."""
        sdk = MagicMock()
        sdk.with_options.return_value = sdk
        sdk.chat.completions.create.side_effect = [reply(a) for a in answers]
        service = OpenAIExtractionService(api_key='sk-x', model=model, client=sdk)
        policy = policy or self.policy()
        run_id = uuid.uuid4()
        execution = SimpleNamespace(run_id=run_id, run=SimpleNamespace(inputs={'execution_policy': policy}))
        meter = MeteredService(service, execution, execution_policy=policy, ledger_id=run_id)
        meter.reserve = lambda kwargs: 1
        meter.record = lambda event_id, data: None
        events = []
        meter.event = lambda state, payload: events.append(payload)
        meter.events = lambda: [SimpleNamespace(payload=p) for p in events]
        return meter, sdk, events

    def ask(self, meter, packet='packet', schema_name='decision'):
        return meter.extract_structured_data(system_prompt='judge', user_content=packet, response_schema=SCHEMA,
                                             schema_name=schema_name)

    def test_a_later_run_reuses_the_answer_to_an_identical_request(self):
        first, sdk, _ = self.run_meter(['{"state": "met"}'])
        self.assertEqual(self.ask(first), {'state': 'met'})
        second, sdk2, events = self.run_meter(['{"state": "not_met"}'])
        self.assertEqual(self.ask(second), {'state': 'met'})
        sdk2.chat.completions.create.assert_not_called()
        self.assertEqual(events[0]['kind'], 'stored_answer_reused')
        self.assertEqual(events[0]['answered_in_run'], str(first.run_id))
        summary = second.metadata()['stored_judgments']
        self.assertEqual((summary['reused_answers'], summary['stored_answers'], len(summary['reused'])), (1, 0, 1))
        self.assertEqual(first.metadata()['stored_judgments']['stored_answers'], 1)

    def test_the_passes_of_one_run_stay_independent_answers(self):
        first, _, _ = self.run_meter(['{"pass": 1}', '{"pass": 2}'])
        self.assertEqual([self.ask(first), self.ask(first)], [{'pass': 1}, {'pass': 2}])
        second, sdk2, _ = self.run_meter(['{"pass": 9}', '{"pass": 9}', '{"pass": 3}'])
        # Pass 1 and pass 2 come back as before; a third identical request (a tie-break) is asked afresh.
        self.assertEqual([self.ask(second), self.ask(second), self.ask(second)], [{'pass': 1}, {'pass': 2}, {'pass': 9}])
        self.assertEqual(sdk2.chat.completions.create.call_count, 1)
        self.assertEqual(StoredAnswer.objects.count(), 3)

    def test_any_change_to_the_request_asks_the_model_again(self):
        first, _, _ = self.run_meter(['{"a": 1}'])
        self.ask(first)
        for label, meter, packet in (
                ('new evidence', self.run_meter(['{"a": 2}'])[0], 'packet with a new page'),
                ('another effort', self.run_meter(['{"a": 2}'], self.policy(model_effort='high'))[0], 'packet'),
                ('another model', self.run_meter(['{"a": 2}'], model='claude-haiku-5-5-x')[0], 'packet')):
            with self.subTest(label):
                self.assertEqual(self.ask(meter, packet), {'a': 2})

    def test_without_the_setting_nothing_is_stored_or_reused(self):
        meter, _, _ = self.run_meter(['{"a": 1}'], self.policy(stored_judgments=None))
        self.assertIsNone(meter.answers)
        self.ask(meter)
        self.assertEqual(StoredAnswer.objects.count(), 0)
        self.assertNotIn('stored_judgments', meter.metadata())

    def test_only_stage_one_reuses(self):
        meter, _, _ = self.run_meter(['{"a": 1}'], self.policy(stage='recommendation'))
        self.assertIsNone(meter.answers)
        self.assertFalse(SecondLayerMeter.reuses_answers)

    def test_a_failed_request_stores_nothing(self):
        meter, sdk, _ = self.run_meter([])
        sdk.chat.completions.create.side_effect = RuntimeError('bug')
        with self.assertRaises(RuntimeError):
            self.ask(meter)
        self.assertEqual(StoredAnswer.objects.count(), 0)

    def test_the_first_stored_answer_stands(self):
        answers = RunAnswers(uuid.uuid4())
        self.assertTrue(answers.keep('h', 0, model='m', schema_name='s', answer={'a': 1}))
        self.assertFalse(RunAnswers(uuid.uuid4()).keep('h', 0, model='m', schema_name='s', answer={'a': 2}))
        self.assertEqual(StoredAnswer.objects.get().answer, {'a': 1})


class HashTests(SimpleTestCase):
    def test_the_timeout_does_not_change_the_request(self):
        base = dict(provider='openai', model='m', policy={'model_effort': 'low', 'output_tokens': 10}, tier='judging')
        self.assertEqual(request_hash(**base, kwargs={'user_content': 'x', 'timeout': 60}),
                         request_hash(**base, kwargs={'user_content': 'x', 'timeout': 600}))
        self.assertNotEqual(request_hash(**base, kwargs={'user_content': 'x'}),
                            request_hash(**{**base, 'policy': {'model_effort': 'low', 'output_tokens': 20}},
                                         kwargs={'user_content': 'x'}))


class PolicyTests(SimpleTestCase):
    def test_the_setting_is_frozen_into_the_assessment_policy_only(self):
        self.assertNotIn('stored_judgments', policy())
        with override_settings(CAPABILITY_STORED_JUDGMENTS=True):
            self.assertEqual(policy()['stored_judgments'], VERSION)
            self.assertNotIn('stored_judgments', policy('recommendation'))
