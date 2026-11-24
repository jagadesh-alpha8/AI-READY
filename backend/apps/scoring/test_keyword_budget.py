"""Keyword mode's own wide packet (CAPABILITY_KEYWORD_CHARS, retrieval_policy.keyword_chars).

Test 13's 200,000-character lane was the keyword search (select_balanced_context) with an embedding tail of 6,000
characters; keyword mode was held at 18,000 because the wide lanes were refused without hybrid. These tests pin that
the default changes nothing, that a frozen size reaches every path that rebuilds a run's packets, and that the prompt
ceiling can shrink it.
"""
import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .capability import prompt_ceiling
from .capability.engine import release
from .capability.evaluation import KeywordLane, _prepare, evaluate, select_context
from .capability.execution import policy as execution_policy
from .capability.semantic_retrieval import KEYWORD_CHARS, SemanticRetrievalUnavailable, configured_policy

DOC = '11111111-1111-4111-8111-111111111111'
BASE = dict(CAPABILITY_RETRIEVAL_ALLOCATION='', CAPABILITY_DEDUPLICATE_PAGES=False, CAPABILITY_STRUCTURE_ROUTING=False,
            CAPABILITY_REPEAT_SKIP=False, CAPABILITY_FOLLOW_UP_SEARCH=False, CAPABILITY_PROMPT_TOKEN_CEILING=None)


def corpus(pages=120):
    """Pages of a strategic plan, every seventh naming an AI priority: far more keyword matches than 18,000 holds."""
    filler = ' '.join(['The institution maintains its strategic plan and reviews digital priorities each year.'] * 25)
    return [{'id': f'{n:08d}-0000-4000-8000-000000000000', 'document_id': DOC, 'page_number': n,
             'text': (f'Page {n}. The approved strategic plan names artificial intelligence as a priority. '
                      if n % 7 == 0 else f'Page {n}. ') + filler, 'text_source': 'text'}
            for n in range(1, pages + 1)]


def chars(context):
    return sum(len(s['text']) for s in context)


class PolicyTests(SimpleTestCase):
    def policy(self, **changes):
        with override_settings(**{**BASE, **changes}):
            return configured_policy('bm25')

    def test_the_default_freezes_nothing_new(self):
        self.assertNotIn('keyword_chars', self.policy())
        self.assertNotIn('keyword_chars', self.policy(CAPABILITY_KEYWORD_CHARS=KEYWORD_CHARS))

    def test_a_wider_packet_is_frozen_with_the_run(self):
        frozen = self.policy(CAPABILITY_KEYWORD_CHARS=150000, CAPABILITY_MAX_INPUT_TOKEN_BOUND=300000)
        self.assertEqual((frozen['mode'], frozen['keyword_chars']), ('bm25', 150000))

    def test_the_request_bound_must_allow_it(self):
        with self.assertRaisesMessage(SemanticRetrievalUnavailable, '300,000'):
            self.policy(CAPABILITY_KEYWORD_CHARS=150000, CAPABILITY_MAX_INPUT_TOKEN_BOUND=131072)

    def test_sizes_outside_the_range_are_refused(self):
        for value in (5000, 250000):
            with self.assertRaises(SemanticRetrievalUnavailable):
                self.policy(CAPABILITY_KEYWORD_CHARS=value, CAPABILITY_MAX_INPUT_TOKEN_BOUND=1000000)

    def test_hybrid_mode_refuses_it(self):
        """Hybrid sizes its keyword lane with the allocation; two settings for one thing would disagree silently."""
        with override_settings(**BASE, CAPABILITY_KEYWORD_CHARS=150000, CAPABILITY_MAX_INPUT_TOKEN_BOUND=300000):
            with self.assertRaisesMessage(SemanticRetrievalUnavailable, 'keyword mode only'):
                configured_policy('hybrid')

    def test_the_wide_allocations_point_keyword_mode_to_its_own_setting(self):
        with self.assertRaisesMessage(SemanticRetrievalUnavailable, 'CAPABILITY_KEYWORD_CHARS'):
            self.policy(CAPABILITY_RETRIEVAL_ALLOCATION='protected-baseline-then-discovery-xwide-v1')

    def test_high_effort_limits_treat_it_as_a_wide_packet(self):
        limits = dict(CAPABILITY_MAX_HTTP_CALLS=90, CAPABILITY_REQUEST_TIMEOUT_SECONDS=180,
                      CAPABILITY_ASSESSMENT_TIMEOUT_SECONDS=None, CAPABILITY_ASSESSMENT_OUTPUT_TOKENS=None,
                      CAPABILITY_OUTPUT_TOKENS=12000, CAPABILITY_MAX_DURATION_SECONDS=None,
                      CAPABILITY_GEMINI_REASONING_EFFORT='high', CAPABILITY_AGREEMENT_PASSES=2,
                      CAPABILITY_INDICATOR_CONCURRENCY=4, CAPABILITY_RETRIEVAL_ALLOCATION='')
        with override_settings(**limits, CAPABILITY_KEYWORD_CHARS=150000):
            wide = execution_policy('assessment')
        with override_settings(**limits, CAPABILITY_KEYWORD_CHARS=KEYWORD_CHARS):
            default = execution_policy('assessment')
        self.assertEqual((wide['timeout_seconds'], wide['output_tokens']), (600, 64000))
        self.assertEqual((default['timeout_seconds'], default['output_tokens']), (300, 48000))

    def test_the_settings_check_names_the_setting(self):
        from .management.commands.capability_settings_check import _compare
        rows = _compare('retrieval_policy', {'mode': 'bm25'}, {'mode': 'bm25', 'keyword_chars': 150000})
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['kind'], rows[0]['run']), ('scoring', '(not set)'))
        self.assertIn('CAPABILITY_KEYWORD_CHARS', rows[0]['set_with'])


@override_settings(CAPABILITY_EVIDENCE_LANE=False)
class PacketTests(SimpleTestCase):
    def setUp(self):
        self.indicator = next(i for i in release()['indicators'] if i['code'] == 'AIQIF-C1.1')
        self.sources = corpus()

    def prepare(self, **extra):
        return _prepare(self.indicator, sources=self.sources, semantic_ranker=None, gemini=True, reviewed_evidence=None,
                        population='All faculty', reference_period='2024-25', scope=None, judgment='parts', **extra)

    def test_without_it_the_packet_is_unchanged(self):
        self.assertEqual(self.prepare()['context'], select_context(self.indicator, self.sources))
        self.assertLessEqual(chars(self.prepare()['context']), KEYWORD_CHARS)

    def test_the_frozen_size_is_the_keyword_selector_at_that_size(self):
        wide = self.prepare(keyword_chars=60000)['context']
        self.assertEqual(wide, select_context(self.indicator, self.sources, max_chars=60000))
        self.assertGreater(chars(wide), 3 * KEYWORD_CHARS)
        self.assertLessEqual(chars(wide), 60000)
        # The default packet is where the wider one starts (the requirements' first picks), not a different packet.
        default = {(s['id'], s['text_offset']) for s in self.prepare()['context']}
        self.assertTrue(default & {(s['id'], s['text_offset']) for s in wide})

    def test_the_window_cache_changes_nothing(self):
        cache = {'windows': {}, 'pages': {}}
        first = self.prepare(keyword_chars=60000, window_cache=cache)['context']
        self.assertTrue(cache['windows'])
        self.assertEqual(first, self.prepare(keyword_chars=60000, window_cache=cache)['context'])
        self.assertEqual(first, self.prepare(keyword_chars=60000)['context'])

    def test_the_prompt_ceiling_shrinks_the_keyword_packet(self):
        ceiling = {'version': prompt_ceiling.VERSION, 'tokens': 15000, 'bytes_per_token': 2.6,
                   'short_ids': prompt_ceiling.SHORT_IDS_VERSION}
        whole = self.prepare(keyword_chars=60000)
        trimmed = self.prepare(keyword_chars=60000, ceiling=ceiling)
        audit = trimmed['prompt_ceiling']
        self.assertEqual(audit['keyword_chars_before'], 60000)
        self.assertLess(audit['keyword_chars'], 60000)
        self.assertGreaterEqual(audit['keyword_chars'], 24000)    # never below 40%
        self.assertLess(chars(trimmed['context']), chars(whole['context']))
        self.assertTrue(audit['dropped'])
        # The default 18,000 packet is still never trimmed (as before this setting existed).
        self.assertEqual(self.prepare(ceiling={**ceiling, 'tokens': 500})['prompt_ceiling']['rebuilds'], 0)

    def test_the_lane_shrinks_like_a_ranker_and_is_not_changed_by_it(self):
        lane = KeywordLane(60000)
        self.assertEqual((lane.baseline_chars, lane.context_chars), (60000, 60000))
        trimmed = prompt_ceiling.smaller(lane, 30000)
        self.assertEqual((trimmed.baseline_chars, trimmed.context_chars, lane.baseline_chars), (30000, 30000, 60000))


@override_settings(CAPABILITY_EVIDENCE_LANE=False, AI_RATE_LIMIT_ENABLED=False)
class EvaluateTests(SimpleTestCase):
    def test_a_runs_frozen_size_reaches_the_judge(self):
        indicator = next(i for i in release()['indicators'] if i['code'] == 'AIQIF-C1.1')
        rubric = {**release(), 'indicators': [indicator]}
        sources = corpus()
        sent = []

        class Judge:
            provider, model, base_url = 'anthropic', 'claude-haiku-5-5', None

            def extract_structured_data(self, **kwargs):
                payload = json.loads(kwargs['user_content'])
                sent.append(payload)
                return {'conditions': {c['id']: {'reason': 'Stand-in.', 'scope_supported': False,
                                                 'period_supported': False,
                                                 'findings': [{'part_id': p['id'], 'finding': 'not_found',
                                                               'citations': []} for p in c['parts']]}
                                       for c in payload['indicator']['conditions']}}

        def packet(retrieval_policy):
            sent.clear()
            evaluate(sources, service=Judge(), population='All faculty', reference_period='2024-25', rubric=rubric,
                     max_calls=1, judgment='parts', retrieval_policy=retrieval_policy, strict_errors=True)
            return chars(sent[0]['sources'])

        self.assertGreater(packet({'mode': 'bm25', 'keyword_chars': 60000}), 3 * KEYWORD_CHARS)
        self.assertLessEqual(packet({'mode': 'bm25'}), KEYWORD_CHARS)
        self.assertLessEqual(packet(None), KEYWORD_CHARS)

    def test_tools_that_rebuild_a_runs_packets_pass_the_frozen_size(self):
        """page_use, capability_packet_changes and capability_prompt_ceiling_check rebuild packets through _prepare;
        each must hand it the run's keyword_chars, or a wide keyword run would not reproduce."""
        from pathlib import Path
        root = Path(__file__).resolve().parent
        for path in ('capability/page_use.py', 'management/commands/capability_packet_changes.py',
                     'management/commands/capability_prompt_ceiling_check.py'):
            self.assertIn("keyword_chars=policy.get('keyword_chars')", (root / path).read_text(), path)
        with patch('apps.scoring.capability.evaluation._prepare', wraps=_prepare) as spy:
            self.test_a_runs_frozen_size_reaches_the_judge()
        self.assertTrue(any(call.kwargs.get('keyword_chars') == 60000 for call in spy.call_args_list))
