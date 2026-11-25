"""The scoring switch and the tagger keep their own endpoint: with extraction on an OpenAI-compatible endpoint
(AI_BASE_URL, e.g. Google's Gemini endpoint, as on the live server until 25 Nov), a Claude key given to scoring
(CAPABILITY_AI_*) or to the tagger (EVIDENCE_MAP_AI_*) must reach Anthropic, not that endpoint."""
from django.test import SimpleTestCase, override_settings

from apps.extraction.services.anthropic_client import AnthropicExtractionService
from apps.extraction.services.openai_client import OpenAIExtractionService

GEMINI = dict(AI_API_KEY='gemini-key', AI_MODEL='gemini-3.8-flash',
              AI_BASE_URL='https://generativelanguage.googleapis.com/v1beta/openai/', AI_PROCESSING_MODE='single')


@override_settings(**GEMINI)
class OwnEndpointTests(SimpleTestCase):
    @override_settings(CAPABILITY_AI_API_KEY='sk-ant-scoring', CAPABILITY_AI_MODEL='claude-haiku-5-5',
                       CAPABILITY_AI_BASE_URL='')
    def test_scoring_switch_reaches_anthropic_while_extraction_uses_a_base_url(self):
        from apps.scoring.capability.model_choice import scoring_service
        from apps.extraction.services.ai_service import get_ai_service
        service = scoring_service()
        self.assertIsInstance(service, AnthropicExtractionService)
        self.assertEqual((service.model, service.api_key), ('claude-haiku-5-5', 'sk-ant-scoring'))
        extraction = get_ai_service()   # extraction itself is unchanged
        self.assertIsInstance(extraction, OpenAIExtractionService)
        self.assertEqual(extraction.model, 'gemini-3.8-flash')

    @override_settings(CAPABILITY_AI_API_KEY='sk-scoring', CAPABILITY_AI_MODEL='qwen', 
                       CAPABILITY_AI_BASE_URL='https://api.deepinfra.com/v1/openai')
    def test_scoring_switch_with_its_own_base_url_still_uses_it(self):
        from apps.scoring.capability.model_choice import scoring_service
        service = scoring_service()
        self.assertIsInstance(service, OpenAIExtractionService)
        self.assertIn('deepinfra', str(service.base_url))

    @override_settings(CAPABILITY_AI_API_KEY='', EVIDENCE_MAP_AI_API_KEY='sk-ant-tagger',
                       EVIDENCE_MAP_AI_MODEL='claude-haiku-5-5', EVIDENCE_MAP_AI_BASE_URL='')
    def test_tagger_key_reaches_anthropic(self):
        from apps.evidence_map.tagging import tagger_service
        service = tagger_service()
        self.assertIsInstance(service, AnthropicExtractionService)
        self.assertTrue(service.cache_system)
