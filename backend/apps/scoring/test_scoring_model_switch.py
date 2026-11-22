"""The scoring-model switch (CAPABILITY_AI_*) and the Claude / OpenAI paths it opens.

Off, scoring uses the extraction model exactly as before. On, scoring calls go to the configured key, model and
base URL; Claude answers in JSON output mode (which works with its thinking) at the run's frozen effort, and OpenAI
reasoning models get max_completion_tokens and reasoning_effort. Prices with a long-context tier are reserved at the
higher rates when a prompt could cross the threshold. The whole product flow runs once with Claude as the stand-in.
"""
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.extraction.pricing import cost_usd
from apps.extraction.services.anthropic_client import AnthropicExtractionService, json_output_schema
from apps.extraction.services.openai_client import OpenAIExtractionService

from . import test_product_flow as flow
from .capability import execution, model_choice
from .capability.provider import MeteredService

ON = dict(CAPABILITY_AI_API_KEY='sk-ant-scoring', CAPABILITY_AI_MODEL='claude-haiku-5-5', CAPABILITY_AI_BASE_URL='',
          CAPABILITY_AI_EFFORT='max')
OFF = dict(CAPABILITY_AI_API_KEY='', CAPABILITY_AI_MODEL='', CAPABILITY_AI_BASE_URL='', CAPABILITY_AI_EFFORT=None)
SCHEMA = {'type': 'object', 'properties': {
    'items': {'type': 'array', 'items': {'type': 'string', 'maxLength': 40}, 'minItems': 2, 'maxItems': 5},
    'note': {'type': 'string', 'format': 'date'}, 'one': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0},
                                                         'minItems': 1}},
    'required': ['items', 'note', 'one']}


def claude_reply(body, *, thinking=True, stop='end_turn', input_tokens=400):
    content = ([SimpleNamespace(type='thinking', thinking='Checking each part.')] if thinking else []) + [
        SimpleNamespace(type='text', text=body if isinstance(body, str) else json.dumps(body))]
    return SimpleNamespace(model='claude-haiku-5-5', stop_reason=stop, content=content,
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=200, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0))


class SwitchTests(SimpleTestCase):
    @override_settings(**OFF, AI_MODEL='gemini-3.8-flash')
    def test_off_scoring_uses_the_extraction_model(self):
        with patch('apps.extraction.services.ai_service.get_ai_service', return_value='extraction') as get:
            self.assertEqual(model_choice.scoring_service(), 'extraction')
        get.assert_called_once_with()
        self.assertEqual(model_choice.scoring_model(), 'gemini-3.8-flash')
        self.assertIsNone(model_choice.effort())

    @override_settings(**ON, AI_MODEL='gemini-3.8-flash')
    def test_on_scoring_uses_its_own_key_model_and_json_output(self):
        service = AnthropicExtractionService(api_key='sk-ant-scoring', model='claude-haiku-5-5', client=MagicMock())
        with patch('apps.extraction.services.ai_service.get_ai_service', return_value=service) as get:
            self.assertIs(model_choice.scoring_service(), service)
        get.assert_called_once_with(api_key='sk-ant-scoring', model='claude-haiku-5-5', base_url=None)
        self.assertTrue(service.json_output)
        self.assertEqual((model_choice.scoring_model(), model_choice.effort()), ('claude-haiku-5-5', 'max'))

    @override_settings(**{**ON, 'CAPABILITY_AI_BASE_URL': 'https://api.deepinfra.com/v1/openai',
                          'CAPABILITY_AI_MODEL': 'deepseek-ai/DeepSeek-V4-Pro'})
    def test_a_base_url_sends_scoring_to_an_openai_compatible_host(self):
        with patch('apps.extraction.services.ai_service.get_ai_service', return_value='host') as get:
            model_choice.scoring_service()
        get.assert_called_once_with(api_key='sk-ant-scoring', model='deepseek-ai/DeepSeek-V4-Pro',
                                    base_url='https://api.deepinfra.com/v1/openai')

    @override_settings(**{**ON, 'CAPABILITY_AI_MODEL': ''})
    def test_a_key_without_a_model_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            model_choice.scoring_service()

    @override_settings(**{**ON, 'CAPABILITY_AI_EFFORT': 'extreme'})
    def test_an_unknown_effort_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            model_choice.effort()

    def test_the_effort_is_frozen_with_the_run_only_when_switched_on(self):
        with override_settings(**ON):
            self.assertEqual(execution.policy()['model_effort'], 'max')
        with override_settings(**OFF):
            self.assertNotIn('model_effort', execution.policy())


class ClaudeJsonOutputTests(SimpleTestCase):
    def service(self, reply):
        sdk = MagicMock()
        sdk.messages.create.return_value = reply
        service = AnthropicExtractionService(api_key='sk-ant-x', model='claude-haiku-5-5', client=sdk)
        return service, sdk

    @override_settings(AI_RATE_LIMIT_ENABLED=False, AI_TEMPERATURE=0)
    def test_json_output_sends_the_schema_and_effort_and_reads_the_text_after_thinking(self):
        service, sdk = self.service(claude_reply({'items': ['a', 'b'], 'note': 'n', 'one': [1]}))
        service.json_output, service.effort = True, 'xhigh'
        result = service.extract_structured_data(system_prompt='s', user_content='u', response_schema=SCHEMA,
                                                 schema_name='thing')
        self.assertEqual(result, {'items': ['a', 'b'], 'note': 'n', 'one': [1]})
        sent = sdk.messages.create.call_args.kwargs
        self.assertEqual(sent['output_config']['effort'], 'xhigh')
        self.assertEqual(sent['output_config']['format']['type'], 'json_schema')
        self.assertNotIn('tools', sent)
        self.assertNotIn('temperature', sent)   # thinking accepts only the default

    @override_settings(AI_RATE_LIMIT_ENABLED=False)
    def test_unparseable_text_is_a_response_error(self):
        from apps.extraction.services.anthropic_client import AnthropicResponseError
        service, _ = self.service(claude_reply('not json'))
        service.json_output = True
        with self.assertRaises(AnthropicResponseError):
            service.extract_structured_data(system_prompt='s', user_content='u', response_schema=SCHEMA)

    @override_settings(AI_RATE_LIMIT_ENABLED=False)
    def test_the_forced_tool_path_is_unchanged_when_json_output_is_off(self):
        tool = SimpleNamespace(model='m', stop_reason='tool_use', usage=None,
                               content=[SimpleNamespace(type='tool_use', name='thing', input={'ok': True})])
        service, sdk = self.service(tool)
        self.assertEqual(service.extract_structured_data(system_prompt='s', user_content='u', response_schema=SCHEMA,
                                                         schema_name='thing'), {'ok': True})
        self.assertIn('tools', sdk.messages.create.call_args.kwargs)

    def test_the_schema_is_cut_to_what_json_output_supports(self):
        cut = json_output_schema(SCHEMA)
        items = cut['properties']['items']
        self.assertNotIn('minItems', items)          # only 0 or 1 is supported
        self.assertNotIn('maxItems', items)
        self.assertNotIn('maxLength', items['items'])
        self.assertNotIn('format', cut['properties']['note'])
        self.assertEqual(cut['properties']['one']['minItems'], 1)
        self.assertNotIn('minimum', cut['properties']['one']['items'])
        self.assertIs(cut['additionalProperties'], False)
        self.assertEqual(SCHEMA['properties']['items']['minItems'], 2)   # the caller's schema is not changed


@override_settings(AI_RATE_LIMIT_ENABLED=False, AI_PRICING_JSON='')
class MeterTests(SimpleTestCase):
    def policy(self, **extra):
        return {'max_duration_seconds': 600, 'output_tokens': 1000, 'timeout_seconds': 60, 'stage': 'assessment',
                'input_token_bound_limit': 1000000, 'gemini_reasoning_effort': 'high', **extra}

    def meter(self, service, policy):
        execution = SimpleNamespace(run_id='r', run=SimpleNamespace(inputs={'execution_policy': policy}))
        meter = MeteredService(service, execution, execution_policy=policy, ledger_id='r')
        meter.reserve = lambda kwargs: 1
        meter.record = lambda event_id, data: None
        return meter

    def test_claude_gets_json_output_at_the_runs_effort(self):
        sdk = MagicMock()
        sdk.with_options.return_value = sdk
        sdk.messages.create.return_value = claude_reply({'items': [], 'note': '', 'one': [1]})
        service = AnthropicExtractionService(api_key='sk-ant-x', model='claude-haiku-5-5', client=sdk)
        meter = self.meter(service, self.policy(model_effort='max'))
        meter.extract_structured_data(system_prompt='s', user_content='u', response_schema=SCHEMA, schema_name='t')
        sent = sdk.messages.create.call_args.kwargs
        self.assertEqual((sent['output_config']['effort'], sent['max_tokens']), ('max', 1000))

    def test_openai_reasoning_models_get_completion_tokens_and_effort(self):
        sdk = MagicMock()
        sdk.with_options.return_value = sdk
        sdk.chat.completions.create.return_value = SimpleNamespace(
            model='gpt-6-luna', usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                                                       prompt_tokens_details=None, completion_tokens_details=None),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{"ok": true}', refusal=None))])
        service = OpenAIExtractionService(api_key='sk-x', model='gpt-6-luna', client=sdk)
        with override_settings(AI_TEMPERATURE=0, AI_SEED=42):
            meter = self.meter(service, self.policy(model_effort='max'))
            meter.extract_structured_data(system_prompt='s', user_content='u', response_schema={'type': 'object'},
                                          schema_name='t')
        sent = sdk.chat.completions.create.call_args.kwargs
        self.assertEqual((sent['max_completion_tokens'], sent['reasoning_effort']), (1000, 'max'))
        for gone in ('max_tokens', 'temperature', 'seed'):
            self.assertNotIn(gone, sent)

    def test_a_long_prompt_is_reserved_at_the_long_context_rates(self):
        service = AnthropicExtractionService(api_key='sk-ant-x', model='claude-haiku-5-5', client=MagicMock())
        meter = self.meter(service, self.policy())
        short_bound, short = meter.envelope({'messages': 'x' * 50000})
        long_bound, long = meter.envelope({'messages': 'x' * 150000})
        self.assertLess(short_bound, 100000)
        self.assertGreater(long_bound, 100000)
        # Short: the dearest input rate is the cache write ($0.125); long: $0.625, and output $2.50 not $0.50.
        self.assertEqual(short, (Decimal(short_bound) * Decimal('0.125') + 1000 * Decimal('0.50')) / 1000000)
        self.assertEqual(long, ((Decimal(long_bound) * Decimal('0.625') + 1000 * Decimal('2.50')) / 1000000
                                ).quantize(Decimal('.000001'), rounding='ROUND_UP'))
        self.assertEqual(meter.configured_prices()['long_context']['threshold'], 100000)

    def test_the_cost_of_a_call_uses_the_tier_its_prompt_falls_in(self):
        self.assertEqual(cost_usd('claude-haiku-5-5', input_tokens=90000, output_tokens=10000), Decimal('0.014000'))
        self.assertEqual(cost_usd('claude-haiku-5-5', input_tokens=90000, cache_read_tokens=20000,
                                  output_tokens=10000), Decimal('0.071000'))


@override_settings(**ON, AI_MODEL='gemini-3.8-flash')
class SettingsCheckTests(SimpleTestCase):
    databases = '__all__'
    def test_a_run_on_another_model_shows_the_switch(self):
        from apps.scoring.management.commands import capability_settings_check as check
        run = SimpleNamespace(pk='r', inputs={})
        with patch.object(check, 'run_model', return_value=('gemini', 'gemini-3.8-flash')), \
                patch.object(check, '_compare', return_value=[]):
            result = check.check(run)
        model = [d for d in result['differences'] if d['section'] == 'model']
        self.assertEqual((model[0]['setting'], model[0]['run'], model[0]['now']),
                         ('CAPABILITY_AI_MODEL', 'gemini-3.8-flash', 'claude-haiku-5-5'))
        self.assertEqual(check.SETTING[('execution_policy', 'model_effort')], 'CAPABILITY_AI_EFFORT')


@override_settings(**flow.SETTINGS, **{**ON, 'CAPABILITY_AI_EFFORT': 'high'})
class ClaudeProductFlowTests(flow.ProductFlowTests):
    """The whole product flow with Claude answering in JSON output mode."""
    SHAPES = {frozenset(['conditions']): 'capability_parts', frozenset(['area', 'indicators', 'requirements']):
              'score_explanations', frozenset(['answered', 'missing_items', 'questions']): 'depth_question_plan',
              frozenset(['groups']): 'depth_question_links', frozenset(['dimensions', 'follow_up']): 'answer_check',
              frozenset(['contradicts_evidence', 'dimension_findings', 'level', 'reason', 'relies_on_unsupported']):
              'depth_judgment', frozenset(['advice']): 'capability_advice'}

    def setUp(self):
        super().setUp()
        self.sdk.messages.create.side_effect = self.claude

    def service(self):
        return AnthropicExtractionService(api_key='sk-ant-test', model='claude-haiku-5-5', client=self.sdk)

    def claude(self, **kwargs):
        config = kwargs['output_config']
        self.assertEqual(config['effort'], 'high')
        self.assertNotIn('tools', kwargs)
        name = self.SHAPES[frozenset(config['format']['schema']['properties'])]
        self.schemas.append(name)
        body = getattr(self, 'reply_' + name)(json.loads(kwargs['messages'][0]['content']))
        return claude_reply(body)


for _name in [n for n in vars(flow.ProductFlowTests) if n.startswith('test_')]:
    if _name != 'test_the_whole_flow':   # one whole flow with Claude is enough here
        setattr(ClaudeProductFlowTests, _name, None)
