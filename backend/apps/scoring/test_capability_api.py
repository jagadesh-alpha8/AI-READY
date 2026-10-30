import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.models import Document
from apps.extraction.models import AIUsage, DocumentPage
from apps.extraction.services.openai_client import OpenAIExtractionService
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .capability.execution import claim, dispatch, finish
from .models import CapabilityExecution, CapabilityRun, CapabilityRunEvent
from .tasks import run_capability_assessment


@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True,
    CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000,
    CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_RATE_LIMIT_ENABLED=False,
    AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
class CapabilityAPITests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='College')
        self.sprint = Sprint.objects.create(institution=self.institution)
        self.other = Institution.objects.create(name='Other')
        self.other_sprint = Sprint.objects.create(institution=self.other)
        self.user = User.objects.create_user(username='coordinator', email='coord@example.com',
            role=User.Role.IQAC_COORDINATOR, institution=self.institution)
        self.client.force_authenticate(self.user)
        doc = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        self.page = DocumentPage.objects.create(document=doc, page_number=1,
            text='Current institutional evidence for every faculty and student in 2025-26.')
        self.url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs'
        self.body = {'population': 'All faculty and students', 'reference_period': '2025-26'}
        self.sdk = MagicMock()
        self.sdk.with_options.return_value = self.sdk
        self.sdk.chat.completions.create.side_effect = self.response

    def response(self, **kwargs):
        payload = json.loads(kwargs['messages'][1]['content'])
        rows = [{'condition_id': c['id'], 'state': 'met', 'reason': 'Current scoped passage',
                 'scope_supported': True, 'period_supported': True,
                 'citations': [{'source_id': s['id'], 'quote': s['text']} for s in payload['sources'][:1]]}
                for c in payload['indicator']['conditions']]
        return SimpleNamespace(model='actual-test-model',
            usage=SimpleNamespace(prompt_tokens=200, completion_tokens=150, prompt_tokens_details=None,
                                  completion_tokens_details=None, total_tokens=350),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
                content=json.dumps({'conditions': rows}), refusal=None))])

    def start(self, key='request-1'):
        with patch('apps.scoring.capability.execution.dispatch') as send:
            with self.captureOnCommitCallbacks(execute=True):
                result = self.client.post(self.url, self.body, format='json', HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(result.status_code, 202, result.data)
            self.assertEqual(send.call_count, 1)
        return CapabilityExecution.objects.get(run_id=result.data['id'])

    def execute(self, execution, *, base_url=None):
        service = OpenAIExtractionService(api_key='sk-test', model='test-model', client=self.sdk, base_url=base_url)
        with patch('apps.scoring.tasks.get_ai_service', return_value=service), patch(
                'apps.scoring.tasks.get_router_pool', return_value=None):
            run_capability_assessment.run(str(execution.run_id), str(execution.task_id))
        execution.refresh_from_db()
        return execution

    def test_read_only_get_and_authorization(self):
        with patch('apps.scoring.capability.execution.dispatch') as send:
            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.assertFalse(send.called)
        self.assertEqual(CapabilityRun.objects.count(), 0)
        foreign = self.url.replace(str(self.sprint.pk), str(self.other_sprint.pk))
        self.assertEqual(self.client.post(foreign, self.body, format='json',
                                         HTTP_IDEMPOTENCY_KEY='foreign').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_idempotent_start_and_conflicting_inputs_and_active_run(self):
        execution = self.start()
        with patch('apps.scoring.capability.execution.dispatch') as send:
            with self.captureOnCommitCallbacks(execute=True):
                replay = self.client.post(self.url, self.body, format='json', HTTP_IDEMPOTENCY_KEY='request-1')
            self.assertEqual(replay.status_code, 200)
            self.assertTrue(replay.data['reused'])
            self.assertFalse(send.called)
        changed = dict(self.body, reference_period='2024-25')
        self.assertEqual(self.client.post(self.url, changed, format='json',
            HTTP_IDEMPOTENCY_KEY='request-1').status_code, 409)
        self.assertEqual(self.client.post(self.url, self.body, format='json',
            HTTP_IDEMPOTENCY_KEY='request-2').status_code, 409)
        self.assertEqual(CapabilityRun.objects.count(), 1)
        self.assertIsNone(claim(execution.run_id, 'wrong-task-id'))

    @override_settings(CAPABILITY_ASSESSMENT_ENABLED=False)
    def test_inference_disabled_by_default_and_key_required(self):
        self.assertEqual(self.client.post(self.url, self.body, format='json',
            HTTP_IDEMPOTENCY_KEY='request-1').status_code, 503)
        self.assertEqual(self.client.post(self.url, self.body, format='json').status_code, 400)
        self.assertFalse(CapabilityRun.objects.exists())

    def test_full_framework_mock_execution_billing_and_duplicate_delivery(self):
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'completed')
        self.assertEqual(execution.requests_reserved, 36)
        self.assertEqual(AIUsage.objects.filter(capability_run=execution.run).count(), 36)
        response = self.client.get(f'{self.url}/{execution.run_id}')
        self.assertEqual(response.status_code, 200)
        assessment = response.data['assessment']
        self.assertEqual(assessment['result']['exact_score'], 100)
        self.assertEqual(len(assessment['records']), 216)
        self.assertEqual(len(assessment['pathways']), 3)
        calls = assessment['inference']['calls']
        self.assertEqual(len(calls), 72)
        self.assertEqual(calls[1]['actual_model'], 'actual-test-model')
        self.sdk.with_options.assert_called_once_with(max_retries=0, timeout=60)
        self.assertEqual(self.sdk.chat.completions.create.call_args.kwargs['max_tokens'], 3000)
        self.execute(execution)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 36)
        evidence = self.client.get(f'{self.url}/{execution.run_id}/evidence')
        self.assertEqual(len(evidence.data['records']), 216)
        self.assertEqual(evidence.data['sources'][0]['id'], str(self.page.pk))
        self.user.institution = self.other
        self.user.save()
        self.assertEqual(self.client.get(f'{self.url}/{execution.run_id}').status_code, 403)
        self.assertEqual(self.client.get(f'{self.url}/{execution.run_id}/evidence').status_code, 403)
        self.assertEqual(self.client.post(f'{self.url}/{execution.run_id}/cancel').status_code, 403)

    def test_queued_cancellation_and_inflight_cancellation(self):
        execution = self.start()
        self.assertEqual(self.client.post(f'{self.url}/{execution.run_id}/cancel').status_code, 200)
        self.execute(execution)
        self.assertEqual(execution.status, 'cancelled')
        self.assertFalse(self.sdk.chat.completions.create.called)
        second = self.start('request-2')
        def cancel_during_call(**kwargs):
            finish(second.run_id, 'cancelled', 'cancelled_by_user')
            return self.response(**kwargs)
        self.sdk.chat.completions.create.side_effect = cancel_during_call
        self.execute(second)
        self.assertEqual(second.status, 'cancelled')
        self.assertEqual(self.sdk.chat.completions.create.call_count, 1)
        self.assertEqual(AIUsage.objects.filter(capability_run=second.run).count(), 1)
        self.assertFalse(second.run.events.filter(state='completed').exists())
        detail = self.client.get(f'{self.url}/{second.run_id}')
        self.assertEqual(detail.data['error']['error_code'], 'cancelled_by_user')

    @override_settings(CAPABILITY_MAX_HTTP_CALLS=1)
    def test_request_budget_retains_partial_evidence_without_headline(self):
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(self.sdk.chat.completions.create.call_count, 1)
        response = self.client.get(f'{self.url}/{execution.run_id}')
        self.assertIsNone(response.data['assessment'])
        self.assertEqual(len(response.data['partial_decisions']), 6)
        self.assertEqual(response.data['error']['error_code'], 'budget_exhausted')

    @override_settings(CAPABILITY_MAX_COST_USD='0.000001')
    def test_cost_reservation_prevents_first_request(self):
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'failed')
        self.assertFalse(self.sdk.chat.completions.create.called)
        self.assertEqual(execution.requests_reserved, 0)

    @override_settings(AI_PRICING_JSON='')
    def test_unknown_price_fails_before_spending(self):
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(execution.run.events.last().payload['error_code'], 'model_pricing_required')
        self.assertFalse(self.sdk.chat.completions.create.called)

    def test_provider_error_is_sanitized_and_broker_error_is_terminal(self):
        execution = self.start()
        self.sdk.chat.completions.create.side_effect = RuntimeError('SECRET provider error')
        self.execute(execution)
        self.assertEqual(execution.status, 'failed')
        self.assertNotIn('SECRET', str(list(execution.run.events.values_list('payload', flat=True))))
        second = self.start('request-2')
        with patch('apps.scoring.tasks.run_capability_assessment.apply_async', side_effect=RuntimeError('SECRET')):
            dispatch(str(second.run_id), str(second.task_id))
        self.execute(second)
        self.assertEqual(second.status, 'failed')
        self.assertEqual(second.run.events.last().payload['error_code'], 'dispatch_failed')

    def test_missing_usage_stops_and_preserves_request_reservation(self):
        execution = self.start()
        def no_usage(**kwargs):
            response = self.response(**kwargs)
            response.usage = None
            return response
        self.sdk.chat.completions.create.side_effect = no_usage
        self.execute(execution)
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(execution.requests_reserved, 1)
        self.assertGreater(execution.usd_reserved, 0)
        self.assertEqual(execution.run.events.last().payload['error_code'], 'usage_telemetry_missing')

    @override_settings(CAPABILITY_MAX_HTTP_CALLS=2)
    def test_compatible_json_correction_counts_as_another_request(self):
        execution = self.start()
        counter = [0]
        def malformed_once(**kwargs):
            response = self.response(**kwargs)
            counter[0] += 1
            if counter[0] == 1:
                response.choices[0].message.content = 'not json'
            return response
        self.sdk.chat.completions.create.side_effect = malformed_once
        self.execute(execution, base_url='https://example.invalid/v1')
        self.assertEqual(execution.requests_reserved, 2)
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(AIUsage.objects.filter(capability_run=execution.run).count(), 2)
        self.assertEqual(execution.run.events.filter(payload__kind='indicator').count(), 1)

    def test_router_lease_is_used_and_released(self):
        execution = self.start()
        pool, lease = MagicMock(), MagicMock()
        pool.acquire.return_value = lease
        service = OpenAIExtractionService(api_key='sk-test', model='test-model', client=self.sdk)
        with patch('apps.scoring.tasks.get_router_pool', return_value=pool), patch(
                'apps.scoring.tasks.get_ai_service', return_value=service), patch(
                'apps.scoring.tasks.use_lease') as use:
            run_capability_assessment.run(str(execution.run_id), str(execution.task_id))
        use.assert_called_once_with(lease)
        pool.release.assert_called_once_with(lease)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'completed')

    def test_empty_corpus_completes_unknown_without_provider(self):
        self.page.status = 'unreadable'
        self.page.save()
        execution = self.start()
        with patch('apps.scoring.tasks.get_ai_service') as factory, patch(
                'apps.scoring.tasks.get_router_pool') as pool:
            run_capability_assessment.run(str(execution.run_id), str(execution.task_id))
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'completed')
        self.assertFalse(factory.called)
        self.assertFalse(pool.called)
        response = self.client.get(f'{self.url}/{execution.run_id}')
        self.assertEqual(response.data['assessment']['result']['upper'], 100)
        self.assertEqual(response.data['assessment']['result']['assessment_coverage'], 0)

    @override_settings(CAPABILITY_MAX_HTTP_CALLS=2)
    def test_transient_request_retry_counts_and_is_bounded(self):
        from openai import APIConnectionError
        import httpx
        execution = self.start()
        counter = [0]
        def transient_once(**kwargs):
            counter[0] += 1
            if counter[0] == 1:
                raise APIConnectionError(request=httpx.Request('POST', 'https://example.invalid'))
            return self.response(**kwargs)
        self.sdk.chat.completions.create.side_effect = transient_once
        with patch('apps.scoring.capability.provider.time.sleep'):
            self.execute(execution)
        self.assertEqual(execution.status, 'failed')
        self.assertEqual(execution.requests_reserved, 2)
        self.assertEqual(execution.run.events.filter(payload__kind='request_outcome').count(), 2)
        self.assertEqual(AIUsage.objects.filter(capability_run=execution.run).count(), 1)

    def test_anthropic_provider_uses_same_budget_and_billing_contract(self):
        from apps.extraction.services.anthropic_client import AnthropicExtractionService
        execution = self.start()
        def response(**kwargs):
            data = json.loads(kwargs['messages'][0]['content'])
            rows = [{'condition_id': c['id'], 'state': 'unknown', 'reason': 'Not established',
                     'scope_supported': False, 'period_supported': False, 'citations': []}
                    for c in data['indicator']['conditions']]
            return SimpleNamespace(model='test-model', stop_reason='tool_use',
                usage=SimpleNamespace(input_tokens=200, output_tokens=150, cache_read_input_tokens=0,
                                      cache_creation_input_tokens=0),
                content=[SimpleNamespace(type='tool_use', name='capability_conditions', input={'conditions': rows})])
        self.sdk.messages.create.side_effect = response
        service = AnthropicExtractionService(api_key='sk-ant-test', model='test-model', client=self.sdk)
        with patch('apps.scoring.tasks.get_ai_service', return_value=service), patch(
                'apps.scoring.tasks.get_router_pool', return_value=None):
            run_capability_assessment.run(str(execution.run_id), str(execution.task_id))
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'completed')
        self.assertEqual(execution.requests_reserved, 36)
        self.assertEqual(AIUsage.objects.filter(capability_run=execution.run).count(), 36)
        self.assertEqual(self.sdk.messages.create.call_args.kwargs['max_tokens'], 3000)
