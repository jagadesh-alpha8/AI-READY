"""Offline transport, recovery and budget contracts; no provider requests."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase
import httpx
from openai import APITimeoutError

from apps.extraction.exceptions import AIOutputTruncated, ProviderQuotaExhausted, ProviderUnavailable
from apps.extraction.services.openai_client import OpenAIExtractionService
from apps.extraction.usage import openai_token_counts, record_openai_usage, usage_scope
from .capability.evaluation import evaluate
from .capability.execution import (policy, AssessmentDisabled, BudgetExceeded, ExecutionDeadlineExceeded,
                                   ExecutionStopped, InputBudgetExceeded)
from .capability.provider import MeteredService, UnpricedModel, UsageUnavailable
from .capability.request_recovery import request_with_split
from .capability.recommendation_execution import tailor_batch
from . import test_capability_api as api_fixtures


@override_settings(AI_RATE_LIMIT_ENABLED=False, AI_GEMINI_REASONING_EFFORT='low')
class TransportTests(SimpleTestCase):
    def service(self, finish='stop', content='{}'):
        self.sdk = Mock()
        self.sdk.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))], usage=None)
        return OpenAIExtractionService(api_key='test', model='gemini-2.5-flash',
            base_url='https://generativelanguage.googleapis.com/v1beta/openai/', client=self.sdk)

    def call(self, service):
        return service.extract_structured_data(system_prompt='Instructions', user_content='Evidence',
            response_schema={'type': 'object', 'properties': {'answer': {'type': 'string'}}})

    def test_truncation_is_not_retried_as_malformed_json(self):
        service = self.service('length', '{"answer":')
        with self.assertRaises(AIOutputTruncated):
            self.call(service)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 1)

    def test_google_receives_native_schema_without_prompt_duplication(self):
        self.call(self.service())
        sent = self.sdk.chat.completions.create.call_args.kwargs
        self.assertEqual(sent['messages'][0]['content'], 'Instructions')
        self.assertEqual(sent['response_format']['type'], 'json_schema')
        self.assertEqual(sent['reasoning_effort'], 'low')

    def test_unknown_proxy_does_not_receive_google_specific_option(self):
        service = self.service()
        service.base_url = 'https://proxy.example/v1'
        self.call(service)
        sent = self.sdk.chat.completions.create.call_args.kwargs
        self.assertNotIn('reasoning_effort', sent)
        self.assertIn('JSON Schema', sent['messages'][0]['content'])


class RecoveryTests(SimpleTestCase):
    def request(self, outcomes):
        self.service = Mock()
        self.service.extract_structured_data.side_effect = outcomes
        return request_with_split(service=self.service, items=[{'id': str(n)} for n in range(6)],
            identity=lambda item: item['id'], payload_for=lambda group: {'items': group},
            schema_for=lambda group: {}, rows_for=lambda response: response['conditions'],
            prompt='Evaluate', name='conditions', result_key='conditions')

    def test_split_preserves_good_child_and_excludes_foreign_child_ids(self):
        result, audit, errors = self.request([AIOutputTruncated(),
            {'conditions': [{'condition_id': '0'}, {'condition_id': '5'}]},
            ProviderUnavailable(kind='timeout')])
        self.assertEqual(result, {'conditions': [{'condition_id': '0'}]})
        self.assertEqual(errors, {str(n): 'provider_timeout' for n in (3, 4, 5)})
        self.assertTrue(audit['split_attempted'])
        self.assertEqual(self.service.extract_structured_data.call_count, 3)
        self.assertEqual([len(json.loads(c.kwargs['user_content'])['items'])
                          for c in self.service.extract_structured_data.call_args_list], [6, 3, 3])

    def test_input_preflight_also_splits_once_without_recursive_retries(self):
        _, _, errors = self.request([InputBudgetExceeded(), InputBudgetExceeded(), AIOutputTruncated()])
        self.assertEqual(len(errors), 6)
        self.assertEqual(self.service.extract_structured_data.call_count, 3)

    def test_terminal_errors_are_never_demoted_to_missing_evidence(self):
        for exc in (BudgetExceeded(), ExecutionDeadlineExceeded(), ExecutionStopped(), ProviderQuotaExhausted('quota')):
            with self.subTest(error=type(exc).__name__), self.assertRaises(type(exc)):
                self.request([AIOutputTruncated(), exc])


@override_settings(CAPABILITY_RETRIEVAL_MODE='bm25')
class AssessmentRecoveryTests(SimpleTestCase):
    def run_evaluation(self, outcomes):
        service = Mock()
        service.extract_structured_data.side_effect = outcomes
        rubric = {'indicators': [{'code': str(n), 'name': 'Faculty training', 'scoring_mode': 'independent_conditions',
                  'conditions': [{'id': str(n), 'text': 'Faculty training'}]} for n in range(4)]}
        result = evaluate([{'id': 'p', 'text': 'Faculty training evidence.'}], service=service,
            population='Faculty', reference_period='2026', rubric=rubric,
            strict_errors=True, recover_provider_errors=True)
        return service, result

    def test_two_provider_failures_open_circuit_and_remain_processing_unknowns(self):
        service, result = self.run_evaluation([ProviderUnavailable(kind='timeout'), ProviderUnavailable(kind='timeout')])
        self.assertEqual(service.extract_structured_data.call_count, 2)
        self.assertTrue(all(row['state'] == 'unknown' for row in result['records']))
        self.assertTrue(all(row['reason'].startswith('Model evaluation failed') for row in result['records']))
        self.assertIn('circuit open', result['records'][-1]['reason'])

    def test_repeated_single_item_truncation_is_bounded(self):
        service, result = self.run_evaluation([AIOutputTruncated(), AIOutputTruncated()])
        self.assertEqual(service.extract_structured_data.call_count, 2)
        self.assertIn('output_truncated', result['records'][0]['reason'])

    def test_quota_and_programming_errors_still_fail_execution(self):
        for exc in (ProviderQuotaExhausted('quota'), RuntimeError('bug'), BudgetExceeded(), ExecutionStopped()):
            with self.subTest(error=type(exc).__name__), self.assertRaises(type(exc)):
                self.run_evaluation([exc])


class AdviceRecoveryTests(SimpleTestCase):
    def setUp(self):
        self.citation = {'source_id': 'p', 'quote': 'Faculty training evidence.'}
        self.actions = [{'id': cid, 'operation': 'gather_evidence', 'type': 'supply_evidence', 'state': 'unknown',
            'requirement': 'Faculty training', 'citations': [self.citation], 'completion_evidence': 'Training records'}
            for cid in ('a', 'b', 'c')]
        self.rows = [{'condition_id': a['id'], 'operation': a['operation'], 'steps': ['Locate training records.'],
            'suggested_role': 'Coordinator (suggested)', 'effort': 'small', 'dependencies': [],
            'completion_evidence': 'Training records', 'basis': [self.citation]} for a in self.actions]
        self.payload = {'actions': self.actions, 'sources': [{'id': 'p', 'text': self.citation['quote']}],
                        'established_strengths': []}
        self.inputs = {'population': 'Faculty', 'reference_period': '2026'}

    def run_advice(self, outcomes):
        service = Mock()
        service.extract_structured_data.side_effect = outcomes
        batch, metrics = tailor_batch(service, self.payload, self.inputs)
        return service, batch, metrics

    def test_initial_timeout_returns_explicit_fallback_not_capability_deficiency(self):
        service, batch, metrics = self.run_advice([ProviderUnavailable(kind='timeout')])
        self.assertEqual(service.extract_structured_data.call_count, 1)
        self.assertEqual(metrics['provider_failure'], 'provider_timeout')
        self.assertTrue(all(row['origin'] == 'deterministic_fallback' for row in batch))
        self.assertTrue(all(row['operation'] == 'gather_evidence' for row in batch))

    def test_repair_timeout_preserves_valid_neighbours(self):
        rows = deepcopy(self.rows)
        rows[1]['basis'] = []
        _, batch, metrics = self.run_advice([{'advice': rows}, ProviderUnavailable(kind='timeout')])
        self.assertEqual([row['origin'] for row in batch], ['model_tailored', 'deterministic_fallback', 'model_tailored'])
        self.assertEqual(metrics['repair_failure'], 'provider_timeout')
        self.assertEqual(metrics['final_fallback_ids'], ['b'])

    def test_split_keeps_first_child_when_second_child_times_out(self):
        service, batch, metrics = self.run_advice([AIOutputTruncated(), {'advice': self.rows[:1]},
                                                  ProviderUnavailable(kind='timeout')])
        self.assertEqual(service.extract_structured_data.call_count, 3)
        self.assertEqual([row['origin'] for row in batch], ['model_tailored', 'deterministic_fallback', 'deterministic_fallback'])
        self.assertFalse(metrics['repair_attempted'])

    def test_repair_deadline_is_not_swallowed(self):
        with self.assertRaises(ExecutionDeadlineExceeded):
            self.run_advice([{'advice': self.rows[:1]}, ExecutionDeadlineExceeded()])


class PolicyTests(SimpleTestCase):
    @override_settings(CAPABILITY_OUTPUT_TOKENS=8192, CAPABILITY_REQUEST_TIMEOUT_SECONDS=300,
        CAPABILITY_ASSESSMENT_OUTPUT_TOKENS=4096, CAPABILITY_RECOMMENDATION_OUTPUT_TOKENS=12288,
        CAPABILITY_ASSESSMENT_TIMEOUT_SECONDS=None, CAPABILITY_RECOMMENDATION_TIMEOUT_SECONDS=240)
    def test_stage_policies_freeze_independently(self):
        assessment, advice = policy(), policy('recommendation')
        self.assertEqual((assessment['output_tokens'], assessment['timeout_seconds']), (4096, 300))
        self.assertEqual((advice['output_tokens'], advice['timeout_seconds']), (12288, 240))
        with override_settings(CAPABILITY_ASSESSMENT_OUTPUT_TOKENS=6000):
            self.assertEqual(assessment['output_tokens'], 4096)
            self.assertEqual(policy()['output_tokens'], 6000)

    @override_settings(CAPABILITY_ASSESSMENT_OUTPUT_TOKENS=0)
    def test_zero_override_is_rejected(self):
        with self.assertRaises(AssessmentDisabled):
            policy()

    def meter(self):
        # Exercise SDK preflight without a database or actual client.
        meter = object.__new__(MeteredService)
        meter.policy = policy()
        meter.provider, meter.model = 'gemini', 'gemini-2.5-flash'
        meter.service = SimpleNamespace(base_url='https://generativelanguage.googleapis.com/v1beta/openai/')
        meter.remaining_time = Mock(return_value=10)
        meter.envelope = Mock(return_value=(10000, 0))
        meter.reserve = Mock(return_value=1)
        meter.record = Mock()
        return meter

    def test_oversized_request_is_rejected_before_http_or_reservation(self):
        meter, sender = self.meter(), Mock()
        meter.policy['input_token_bound_limit'] = 5000
        with self.assertRaises(InputBudgetExceeded):
            meter.send(sender, {'messages': []})
        sender.assert_not_called()
        meter.reserve.assert_not_called()
        self.assertEqual(meter.record.call_args.args[1]['kind'], 'request_rejected')

    def test_deadline_prevents_http(self):
        meter, sender = self.meter(), Mock()
        meter.remaining_time.side_effect = ExecutionDeadlineExceeded()
        with self.assertRaises(ExecutionDeadlineExceeded):
            meter.send(sender, {})
        sender.assert_not_called()

    @override_settings(AI_GEMINI_REASONING_EFFORT='high')
    def test_frozen_reasoning_timeout_and_usage_are_recorded(self):
        meter, sender = self.meter(), Mock()
        meter.policy['gemini_reasoning_effort'] = 'low'
        sender.return_value = SimpleNamespace(model='gemini-2.5-flash',
            choices=[SimpleNamespace(finish_reason='length')], usage=SimpleNamespace(
                prompt_tokens=100, completion_tokens=200, total_tokens=300,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=175), prompt_tokens_details=None))
        meter.send(sender, {'reasoning_effort': 'high', 'timeout': 1000})
        self.assertEqual(sender.call_args.kwargs['reasoning_effort'], 'low')
        self.assertEqual(sender.call_args.kwargs['timeout'], 10)
        recorded = meter.record.call_args.args[1]
        self.assertEqual(recorded['finish_reason'], 'length')
        self.assertEqual(recorded['tokens']['reasoning_tokens'], 175)

    @override_settings(AI_PRICING_JSON='{"gemini-3.8-flash":{"input":0,"output":0},"local-model":{"input":0,"output":0}}')
    def test_hosted_zero_prices_fail_before_http_but_local_zero_prices_are_valid(self):
        execution = SimpleNamespace(run_id='run', run=SimpleNamespace(inputs={'execution_policy': policy()}))
        client = Mock()
        hosted = OpenAIExtractionService(api_key='test', model='gemini-3.8-flash', client=client,
            base_url='https://generativelanguage.googleapis.com/v1beta/openai/')
        with self.assertRaises(UnpricedModel):
            MeteredService(hosted, execution)
        client.chat.completions.create.assert_not_called()
        local = OpenAIExtractionService(api_key='test', model='local-model', client=client, base_url='http://localhost:11434/v1')
        self.assertEqual(MeteredService(local, execution).rates['output'], 0)

    def test_gemini_missing_total_fails_closed_and_hidden_output_counts_against_cap(self):
        meter, sender = self.meter(), Mock()
        sender.return_value = SimpleNamespace(model='gemini-2.5-flash', choices=[],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10, completion_tokens_details=None))
        with self.assertRaises(UsageUnavailable):
            meter.send(sender, {})
        sender.return_value.usage.total_tokens = meter.policy['output_tokens'] + 101
        meter.send(sender, {})
        self.assertTrue(meter.limit_breach)


class GeminiUsageTests(SimpleTestCase):
    def usage(self, prompt=100, completion=20, total=270, reasoning=None):
        return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning) if reasoning is not None else None,
            prompt_tokens_details=None)

    def test_hidden_thinking_in_total_is_billed_as_output(self):
        counts, known = openai_token_counts(self.usage(), gemini=True)
        self.assertTrue(known)
        self.assertEqual((counts['completion_tokens'], counts['reasoning_tokens']), (170, 150))

    def test_explicit_thinking_details_are_never_added_twice(self):
        for usage in (self.usage(completion=170, reasoning=150), self.usage(reasoning=150)):
            counts, known = openai_token_counts(usage, gemini=True)
            self.assertTrue(known)
            self.assertEqual((counts['completion_tokens'], counts['reasoning_tokens']), (170, 150))
        generic, known = openai_token_counts(self.usage(completion=170, reasoning=150))
        self.assertTrue(known)
        self.assertEqual(generic['completion_tokens'], 170)

    def test_proxy_total_difference_is_not_assumed_to_be_google_thinking(self):
        counts, _ = openai_token_counts(self.usage(), gemini=False)
        self.assertEqual((counts['completion_tokens'], counts['reasoning_tokens']), (20, 0))

    @override_settings(AI_PRICING_JSON='{"gemini-test":{"input":1,"output":2}}')
    def test_usage_record_and_cost_include_hidden_thinking(self):
        with patch('apps.extraction.models.AIUsage.objects.create') as create, usage_scope(stage='fact_extraction'):
            record_openai_usage(SimpleNamespace(usage=self.usage()), provider='gemini', model='gemini-test')
        saved = create.call_args.kwargs
        self.assertEqual((saved['output_tokens'], saved['reasoning_tokens']), (170, 150))
        self.assertEqual(str(saved['cost_usd']), '0.000440')

    @override_settings(AI_PRICING_JSON='{"gemini-test":{"input":0,"output":0}}')
    def test_zero_hosted_rates_are_recorded_as_unpriced_not_free(self):
        with patch('apps.extraction.models.AIUsage.objects.create') as create, usage_scope(stage='fact_extraction'):
            record_openai_usage(SimpleNamespace(usage=self.usage()), provider='gemini', model='gemini-test')
        self.assertIsNone(create.call_args.kwargs['cost_usd'])


@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True,
    CAPABILITY_RETRIEVAL_MODE='bm25', CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_MAX_COST_USD='2',
    CAPABILITY_OUTPUT_TOKENS=3000, CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_RATE_LIMIT_ENABLED=False,
    AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
class PersistedRecoveryTests(APITestCase):
    setUp = api_fixtures.CapabilityAPITests.setUp
    start = api_fixtures.CapabilityAPITests.start
    execute = api_fixtures.CapabilityAPITests.execute
    response = api_fixtures.CapabilityAPITests.response

    def test_timeout_batch_does_not_discard_other_persisted_decisions(self):
        calls = 0
        def respond(**kwargs):
            nonlocal calls
            calls += 1
            if calls <= 2:  # initial HTTP attempt plus the metered transient retry
                raise APITimeoutError(request=httpx.Request('POST', 'https://provider.example'))
            return self.response(**kwargs)
        self.sdk.chat.completions.create.side_effect = respond
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'completed')
        result = execution.run.events.filter(state='completed', payload__result__isnull=False).last().payload
        records = result['records']
        self.assertTrue(any(row['state'] == 'met' for row in records))
        failed = [row for row in records if row['reason'].startswith('Model evaluation failed')]
        self.assertTrue(failed)
        self.assertTrue(all(row['state'] == 'unknown' and not row['citations'] for row in failed))
        self.assertEqual(calls, 37)

    def test_persistent_outage_stops_http_and_publishes_only_processing_unknowns(self):
        self.sdk.chat.completions.create.side_effect = APITimeoutError(
            request=httpx.Request('POST', 'https://provider.example'))
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'completed')
        result = execution.run.events.filter(state='completed', payload__result__isnull=False).last().payload
        self.assertEqual(len(result['records']), 216)
        self.assertTrue(all(row['state'] == 'unknown' for row in result['records']))
        self.assertEqual(self.sdk.chat.completions.create.call_count, 4)
