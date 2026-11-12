import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, override_settings
from django.core.management.base import CommandError
from apps.extraction.services.openai_client import OpenAIExtractionService
from .management.commands.readiness_smoke_test import Command


@override_settings(AI_RATE_LIMIT_ENABLED=False, AI_PROCESSING_MODE='single', AI_BASE_URL='',
    CAPABILITY_MAX_HTTP_CALLS=36, CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000,
    CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_TEMPERATURE=0, AI_SEED=42,
    AI_PRICING_JSON='{"probe-model":{"input":0.1,"output":0.2}}')
class ProviderProbeTests(SimpleTestCase):
    def test_default_is_free_and_does_not_construct_a_provider(self):
        out = StringIO()
        with patch('apps.scoring.management.commands.readiness_smoke_test.get_ai_service') as service:
            Command(stdout=out).handle(live_provider=False)
        service.assert_not_called()
        self.assertFalse(json.loads(out.getvalue())['live_provider_called'])

    def test_live_probe_exercises_actual_sdk_boundary_without_assessment_writes(self):
        sdk = MagicMock();sdk.with_options.return_value = sdk
        def respond(**kwargs):
            payload = json.loads(kwargs['messages'][1]['content'])
            source = payload['sources'][0]
            positive = 'Learners and researchers at Synthetic Institute have access to institutional computers during 2024-25.'
            negative = 'A technical suitability review for 2024-25 confirmed that none of the available resources supports any introductory AI workload.'
            rows = []
            for c in payload['indicator']['conditions']:
                state = 'met' if c['id'].endswith('.F1') else 'not_met' if c['id'].endswith('.F2') else 'unknown'
                quote = positive if state == 'met' else negative
                rows.append(dict(condition_id=c['id'], state=state, reason='Synthetic scoped record.',
                    scope_supported=state != 'unknown', period_supported=state != 'unknown',
                    citations=[{'source_id': source['id'], 'quote': quote}] if state != 'unknown' else []))
            return SimpleNamespace(model='actual-probe-model', usage=SimpleNamespace(prompt_tokens=200, completion_tokens=300),
                choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps({'conditions': rows}), refusal=None))])
        sdk.chat.completions.create.side_effect = respond
        service = OpenAIExtractionService(api_key='sk-test', model='probe-model', client=sdk)
        out = StringIO()
        with patch('apps.scoring.management.commands.readiness_smoke_test.get_ai_service', return_value=service), patch(
                'apps.scoring.management.commands.readiness_smoke_test.get_router_pool', return_value=None):
            Command(stdout=out).handle(live_provider=True)
        result = json.loads(out.getvalue())
        self.assertTrue(result['passed']);self.assertEqual(result['requests'], 1)
        self.assertFalse(result['assessment_written'])
        self.assertEqual(result['indicator_bounds'], {'lower': 16.67, 'upper': 83.33})
        self.assertEqual(result['actual_models'], ['actual-probe-model'])
        sdk.with_options.assert_called_once_with(max_retries=0, timeout=60)

    def test_configuration_failures_never_echo_provider_secrets(self):
        with patch('apps.scoring.management.commands.readiness_smoke_test.get_router_pool', return_value=None), patch(
                'apps.scoring.management.commands.readiness_smoke_test.get_ai_service', side_effect=ValueError('SECRET-provider-key')):
            with self.assertRaises(CommandError) as error:
                Command(stdout=StringIO()).handle(live_provider=True)
        self.assertNotIn('SECRET', str(error.exception))
