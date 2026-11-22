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
from .models import CapabilityRun

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


# ---------------------------------------------------------------------------------------------- the prompt ceiling

from .capability import prompt_ceiling  # noqa: E402

PAGE_A, PAGE_B, DOC, CLAIM = ('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222',
                              '33333333-3333-4333-8333-333333333333', '44444444-4444-4444-8444-444444444444')


class ShortIdTests(SimpleTestCase):
    def payload(self):
        return json.dumps({'sources': [{'id': PAGE_A, 'document_id': DOC, 'text': 'alpha'},
                                       {'id': PAGE_B, 'document_id': DOC, 'text': 'beta'},
                                       {'id': PAGE_A, 'document_id': DOC, 'text': 'second window, same page'}],
                           'reviewed_evidence': {'claims': [{'id': CLAIM, 'source': {
                               'document_id': DOC, 'passages': [{'source_id': PAGE_B}]}}]}})

    def test_long_ids_go_out_short_and_come_back_long(self):
        schema = {'type': 'object', 'properties': {'source_id': {'type': 'string', 'enum': [PAGE_A, PAGE_B]}}}
        content, sent_schema, back = prompt_ceiling.shorten(self.payload(), schema)
        data = json.loads(content)
        self.assertEqual([s['id'] for s in data['sources']], ['S1', 'S2', 'S1'])   # packet pages first, in order
        self.assertEqual(data['sources'][0]['document_id'], 'R1')
        self.assertEqual(data['reviewed_evidence']['claims'][0]['source']['passages'][0]['source_id'], 'S2')
        self.assertEqual(sent_schema['properties']['source_id']['enum'], ['S1', 'S2'])
        self.assertNotIn(PAGE_A, content)
        self.assertEqual(back['S2'], PAGE_B)

    def test_the_client_wrapper_maps_the_answer_back(self):
        inner = MagicMock()
        inner.extract_structured_data.return_value = {'conditions': {'X': {'citations': [
            {'source_id': 'S2', 'quote': 'beta'}], 'reason': 'S2 shows it'}}}
        inner.model = 'claude-haiku-5-5'
        wrapped = prompt_ceiling.ShortIds(inner)
        result = wrapped.extract_structured_data(system_prompt='p', user_content=self.payload(),
                                                 response_schema={'type': 'object'}, schema_name='capability_parts')
        self.assertEqual(result['conditions']['X']['citations'][0]['source_id'], PAGE_B)
        self.assertEqual(result['conditions']['X']['reason'], 'S2 shows it')   # only whole IDs are mapped
        self.assertEqual(wrapped.model, 'claude-haiku-5-5')
        self.assertIn('"S1"', inner.extract_structured_data.call_args.kwargs['user_content'])

    def test_a_request_without_long_ids_passes_through(self):
        inner = MagicMock()
        prompt_ceiling.ShortIds(inner).extract_structured_data(user_content='{"a": 1}', response_schema={})
        self.assertEqual(inner.extract_structured_data.call_args.kwargs['user_content'], '{"a": 1}')


class FitTests(SimpleTestCase):
    POLICY = {'version': prompt_ceiling.VERSION, 'tokens': 1000, 'bytes_per_token': 2.0, 'short_ids': None}

    def ranker(self, keyword=10000):
        return SimpleNamespace(baseline_chars=keyword, context_chars=keyword + 600)

    def build(self, ranker):
        # One passage per 1,000 keyword characters, plus a discovery passage that is always kept.
        n = ranker.baseline_chars // 1000
        return ([{'id': f'k{i}', 'text_offset': 0, 'text': 'x' * 1000} for i in range(n)]
                + [{'id': 'discovery', 'text_offset': 0, 'text': 'd' * 600}]), None

    def measure(self, context, _):
        return sum(len(e['text']) for e in context) // 2 + 100

    def test_under_the_ceiling_nothing_changes(self):
        context, _, audit = prompt_ceiling.fit({**self.POLICY, 'tokens': 100000}, self.ranker(), self.build,
                                               self.measure)
        self.assertEqual((len(context), audit['rebuilds']), (11, 0))

    def test_over_the_ceiling_the_keyword_lane_shrinks_and_discovery_stays(self):
        context, _, audit = prompt_ceiling.fit({**self.POLICY, 'tokens': 4000}, self.ranker(), self.build,
                                               self.measure)
        self.assertLessEqual(audit['estimated_tokens'], 4000)
        self.assertGreater(audit['estimated_tokens_before'], 4000)
        self.assertIn('discovery', [e['id'] for e in context])
        self.assertLess(audit['keyword_chars'], audit['keyword_chars_before'])
        self.assertEqual(audit['dropped_passages'] if 'dropped_passages' in audit else len(audit['dropped']),
                         len(audit['dropped']))
        self.assertFalse(audit['over_ceiling'])

    def test_the_keyword_lane_never_goes_below_its_floor(self):
        context, _, audit = prompt_ceiling.fit({**self.POLICY, 'tokens': 500}, self.ranker(), self.build,
                                               self.measure)
        self.assertEqual(audit['keyword_chars'], 4000)   # 40% of 10,000
        self.assertTrue(audit['over_ceiling'])

    def test_fixed_packets_are_estimated_not_trimmed(self):
        context, _, audit = prompt_ceiling.fit({**self.POLICY, 'tokens': 500}, None,
                                               lambda r: self.build(self.ranker()), self.measure)
        self.assertEqual((len(context), audit['rebuilds']), (11, 0))

    def test_the_ceiling_is_frozen_only_when_set(self):
        with override_settings(CAPABILITY_PROMPT_TOKEN_CEILING=None):
            self.assertIsNone(prompt_ceiling.configured())
        with override_settings(CAPABILITY_PROMPT_TOKEN_CEILING=95000, CAPABILITY_PROMPT_BYTES_PER_TOKEN=2.6):
            self.assertEqual(prompt_ceiling.configured()['tokens'], 95000)
        from .capability.semantic_retrieval import SemanticRetrievalUnavailable
        with override_settings(CAPABILITY_PROMPT_TOKEN_CEILING=5, CAPABILITY_PROMPT_BYTES_PER_TOKEN=2.6):
            with self.assertRaises(SemanticRetrievalUnavailable):
                prompt_ceiling.configured()


class EffortTierTests(SimpleTestCase):
    def test_writing_calls_use_the_writing_effort_and_judging_calls_the_judging_one(self):
        sdk = MagicMock()
        sdk.with_options.return_value = sdk
        sdk.messages.create.return_value = claude_reply({'ok': True})
        service = AnthropicExtractionService(api_key='sk-ant-x', model='claude-haiku-5-5', client=sdk)
        policy = MeterTests.policy(None, model_effort='max', writing_effort='medium')
        meter = MeterTests.meter(None, service, policy)
        with override_settings(AI_RATE_LIMIT_ENABLED=False):
            for name, expected in (('capability_parts', 'max'), ('score_explanations', 'medium'),
                                   ('answer_check', 'medium'), ('depth_judgment', 'max')):
                meter.extract_structured_data(system_prompt='s', user_content='u', response_schema={'type': 'object'},
                                              schema_name=name)
                self.assertEqual(sdk.messages.create.call_args.kwargs['output_config']['effort'], expected, name)

    def test_gemini_writing_calls_get_the_nearest_gemini_level(self):
        from .capability.model_choice import GEMINI_EFFORT, tier
        self.assertEqual((GEMINI_EFFORT['max'], GEMINI_EFFORT['none']), ('high', 'minimal'))
        self.assertEqual((tier('capability_parts'), tier('depth_question_plan'), tier('institution_plan_review')),
                         ('judging', 'writing', 'judging'))

    def test_the_writing_effort_is_frozen_when_set(self):
        with override_settings(**ON, CAPABILITY_AI_WRITING_EFFORT='low'):
            self.assertEqual(execution.policy()['writing_effort'], 'low')
        with override_settings(**ON, CAPABILITY_AI_WRITING_EFFORT=None):
            self.assertNotIn('writing_effort', execution.policy())


@override_settings(**flow.SETTINGS, **{**ON, 'CAPABILITY_AI_EFFORT': 'high'}, CAPABILITY_PROMPT_TOKEN_CEILING=95000,
                   CAPABILITY_PROMPT_BYTES_PER_TOKEN=2.6)
class ClaudeShortIdFlowTests(ClaudeProductFlowTests):
    """The whole flow again with the prompt ceiling on: the stand-in sees only short IDs and cites them; the citations
    come back as page IDs and survive publication."""

    def claude(self, **kwargs):
        content = kwargs['messages'][0]['content']
        if '"sources"' in content and kwargs['output_config']['format']['schema'].get('properties', {}).get('conditions'):
            self.assertNotRegex(content, r'"id": "[0-9a-f]{8}-')
            self.short_id_requests = getattr(self, 'short_id_requests', 0) + 1
        return super().claude(**kwargs)

    def test_the_whole_flow(self):
        super().test_the_whole_flow()
        self.assertGreater(self.short_id_requests, 0)
        from .management.commands.capability_prompt_ceiling_check import check
        run = CapabilityRun.objects.order_by('created_at').first()   # the provisional run
        result = check(run, ceiling_tokens=95000, bytes_per_token=2.6)
        self.assertEqual(result['summary']['credited_quotations_lost'], 0)   # keyword retrieval: nothing trimmed
        self.assertEqual(result['summary']['indicators'], 36)
