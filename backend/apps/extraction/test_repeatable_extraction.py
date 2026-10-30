"""The same document gives the same facts: every AI call pins temperature and seed (settings.AI_TEMPERATURE /
AI_SEED), and PyMuPDF is pinned so the PDF reads into the same text everywhere.

Reproduction: one VELS SSR (same file, same model) gave 297 facts in one local sprint and 324 in the next, with the
text sent to the AI identical page for page -- the model was sampling at the provider's default temperature."""
from pathlib import Path
from unittest.mock import MagicMock

import httpx
from django.test import SimpleTestCase, override_settings
from openai import APIStatusError

from .services import openai_client
from .services.anthropic_client import AnthropicExtractionService
from .services.openai_client import OpenAIExtractionService


def _ok():
    message = MagicMock(content='{"answer": "yes"}')
    return MagicMock(choices=[MagicMock(finish_reason='stop', message=message)], usage=None)


def _call(service):
    return service.extract_structured_data(system_prompt='s', user_content='u', response_schema={'type': 'object'})


class SamplingTests(SimpleTestCase):
    def setUp(self):
        openai_client._NO_SAMPLING.clear()
        self.addCleanup(openai_client._NO_SAMPLING.clear)

    def _service(self, client, base_url='http://ollama.test/v1'):
        return OpenAIExtractionService(api_key='k', model='gemma4:31b', base_url=base_url, client=client)

    def test_every_request_is_sent_at_temperature_0_with_a_fixed_seed(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _ok()
        _call(self._service(client))
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual((kwargs['temperature'], kwargs['seed']), (0.0, 42))

    @override_settings(AI_TEMPERATURE=None, AI_SEED=None)
    def test_unset_leaves_the_provider_default(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _ok()
        _call(self._service(client))
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertNotIn('temperature', kwargs)
        self.assertNotIn('seed', kwargs)

    def test_an_endpoint_that_rejects_the_seed_is_resent_without_it_and_remembered(self):
        request = httpx.Request('POST', 'http://gateway.test/v1/chat/completions')
        rejection = APIStatusError("Unrecognized request argument supplied: seed",
                                   response=httpx.Response(400, request=request), body=None)
        client = MagicMock()
        client.chat.completions.create.side_effect = [rejection, _ok(), _ok()]
        service = self._service(client, base_url='http://gateway.test/v1')
        self.assertEqual(_call(service), {'answer': 'yes'})
        _call(service)
        calls = client.chat.completions.create.call_args_list
        self.assertIn('seed', calls[0].kwargs)
        self.assertNotIn('seed', calls[1].kwargs)
        self.assertNotIn('seed', calls[2].kwargs)
        self.assertIn('response_format', calls[1].kwargs)  # only the sampling parameters are dropped


class AnthropicSamplingTests(SimpleTestCase):
    def test_temperature_0_and_no_seed(self):
        client = MagicMock()
        service = AnthropicExtractionService(api_key='k', model='claude-test', client=client)
        try:
            _call(service)
        except Exception:
            pass  # the MagicMock response does not parse; only the request matters here
        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(kwargs['temperature'], 0.0)
        self.assertNotIn('seed', kwargs)


class PdfLibraryPinTests(SimpleTestCase):
    def test_pymupdf_is_pinned_to_one_version(self):
        requirements = (Path(__file__).resolve().parents[2] / 'requirements' / 'base.txt').read_text()
        pins = [line.strip() for line in requirements.splitlines() if line.strip().lower().startswith('pymupdf')]
        self.assertEqual(len(pins), 1)
        self.assertRegex(pins[0], r'^pymupdf==\d+\.\d+\.\d+$')
