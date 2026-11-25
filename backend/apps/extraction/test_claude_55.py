"""Extraction on Claude 5-generation models (Claude Haiku 5.5): no sampling settings, the forced tool call, images.

Haiku 5.5 rejects temperature / top_p / top_k with a 400 ("omit temperature, top_p and top_k", migration guide); the
extraction call sent AI_TEMPERATURE (default 0) to every Claude model. The fake client below refuses what Haiku 5.5
refuses, so a regression fails here rather than on a paid call.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
from anthropic import BadRequestError
from django.test import SimpleTestCase, override_settings

from .services import anthropic_client
from .services.anthropic_client import AnthropicExtractionService, accepts_sampling
from .services.vision_fallback import model_supports_vision

SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['facts'],
          'properties': {'facts': {'type': 'array', 'items': {'type': 'string'}}}}


def _bad_request(message):
    return BadRequestError(message, response=httpx.Response(400, request=httpx.Request('POST', 'https://x')), body=None)


def _answer(name='extracted_facts'):
    return SimpleNamespace(stop_reason='tool_use', model='claude-haiku-5-5',
                           content=[SimpleNamespace(type='tool_use', name=name, input={'facts': ['ok']})],
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0))


class HaikuRules:
    """messages.create as Claude Haiku 5.5 answers it: a 400 for sampling settings or a thinking budget."""

    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        for key in ('temperature', 'top_p', 'top_k'):
            if key in kwargs:
                raise _bad_request(f'{key}: not supported for this model')
        if (kwargs.get('thinking') or {}).get('type') == 'enabled':
            raise _bad_request('thinking.type.enabled is not supported')
        return _answer(kwargs['tools'][0]['name'] if kwargs.get('tools') else 'x')


@override_settings(AI_TEMPERATURE=0.0, AI_RATE_LIMIT_ENABLED=False)
class ClaudeFiveExtractionTests(SimpleTestCase):
    def setUp(self):
        anthropic_client._NO_SAMPLING.clear()

    def service(self, model='claude-haiku-5-5'):
        rules = HaikuRules()
        client = MagicMock()
        client.messages.create.side_effect = rules.create
        return AnthropicExtractionService(api_key='sk-ant-x', model=model, client=client), rules

    def test_haiku_55_extraction_sends_no_sampling_settings_and_keeps_the_forced_tool_call(self):
        service, rules = self.service()
        result = service.extract_structured_data(system_prompt='s', user_content='page', response_schema=SCHEMA,
                                                 schema_name='extracted_facts')
        self.assertEqual(result, {'facts': ['ok']})
        self.assertEqual(len(rules.calls), 1)
        call = rules.calls[0]
        self.assertNotIn('temperature', call)
        self.assertEqual(call['tool_choice']['type'], 'tool')   # Haiku 5.5 takes it (without thinking)
        self.assertNotIn('thinking', call)

    def test_an_image_page_goes_the_same_way(self):
        service, rules = self.service()
        service.extract_structured_data(system_prompt='s', user_content='page', response_schema=SCHEMA,
                                        schema_name='page_vision_extraction', image_b64='aGk=')
        self.assertNotIn('temperature', rules.calls[0])
        self.assertTrue(model_supports_vision('claude-haiku-5-5', provider='anthropic'))

    def test_older_claude_models_keep_the_temperature(self):
        service, rules = self.service(model='claude-haiku-4-5')
        client = MagicMock()
        client.messages.create.return_value = _answer()
        service._client = client
        service.extract_structured_data(system_prompt='s', user_content='p', response_schema=SCHEMA,
                                        schema_name='extracted_facts')
        self.assertEqual(client.messages.create.call_args.kwargs['temperature'], 0.0)

    def test_an_unknown_model_that_rejects_the_temperature_is_asked_again_without_it(self):
        service, rules = self.service(model='claude-new-preview')
        self.assertTrue(accepts_sampling('claude-new-preview'))
        result = service.extract_structured_data(system_prompt='s', user_content='p', response_schema=SCHEMA,
                                                 schema_name='extracted_facts')
        self.assertEqual(result, {'facts': ['ok']})
        self.assertEqual(['temperature' in c for c in rules.calls], [True, False])
        self.assertFalse(accepts_sampling('claude-new-preview'))   # remembered for the rest of the process
        service.extract_structured_data(system_prompt='s', user_content='p', response_schema=SCHEMA,
                                        schema_name='extracted_facts')
        self.assertEqual(len(rules.calls), 3)

    def test_scoring_json_output_never_sent_it(self):
        service, rules = self.service()
        service.json_output = True
        client = MagicMock()
        client.messages.create.return_value = SimpleNamespace(
            stop_reason='end_turn', model='claude-haiku-5-5', content=[SimpleNamespace(type='text', text='{"facts": []}')],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0))
        service._client = client
        service.extract_structured_data(system_prompt='s', user_content='p', response_schema=SCHEMA, schema_name='x')
        self.assertNotIn('temperature', client.messages.create.call_args.kwargs)

    def test_which_models_take_sampling(self):
        for model in ('claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5', 'claude-fable-5-2',
                      'claude-opus-5', 'anthropic/claude-haiku-5-5'):
            self.assertFalse(accepts_sampling(model), model)
        for model in ('claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-3-5-haiku-20241022'):
            self.assertTrue(accepts_sampling(model), model)
