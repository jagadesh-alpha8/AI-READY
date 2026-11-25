"""Fixes from the independent audit of 25 Nov (project doc claude/ai-ready-audit-23-24-nov.md, items 1, 2, 4, 5 and
the two map-mode warnings in 6). Each test fails on A2 at b2087bf. No model calls."""
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.institutions.models import Institution
from apps.scoring.capability.engine import release
from apps.scoring.capability.evaluation import select_context
from apps.scoring.capability.semantic_retrieval import SemanticRetrievalUnavailable, configured_policy
from apps.sprints.models import Sprint

from . import packet, spec, tagging
from .models import MapJob
from .status import current_version, status
from .tasks import tag_sprint

FILLER = 'The college library holds books on many subjects and is open to all students on working days. '
WEAK = 'Departments keep their own files.'
DECISIVE = ('The evidence repository and source register for every AI system are kept by a named custodian, and the '
            'IQAC audit trail gives traceability from each reported figure to its source record.')


def indicator(code='AIQIF-C9.2'):
    return next(i for i in release()['indicators'] if i['code'] == code)


def real_fill(ind):
    """Today's keyword selector, as map mode's builder calls it (evaluation._prepare)."""
    return lambda pages, max_chars: select_context(ind, pages, max_chars=max_chars)


class LongTaggedPageTests(SimpleTestCase):
    """Item 1: a long page tagged on a weak line was sent only as its window; the rest could never be reached."""

    def setUp(self):
        self.ind = indicator()
        self.long_text = WEAK + ' ' + FILLER * 40 + DECISIVE + ' ' + FILLER * 20
        self.long = {'id': 'long', 'document_id': 'ssr', 'page_number': 187, 'text': self.long_text}
        self.other = {'id': 'other', 'document_id': 'aqar', 'page_number': 3, 'text': 'Sports day. ' + FILLER * 5}
        self.sources = [self.long, self.other]
        self.frozen = {'pages': {spec.text_hash(self.long_text): {'page_type': 'report_narrative', 'tags': [
            {'indicator': self.ind['code'], 'requirements': [self.ind['conditions'][0]['id']],
             'strength': 'supporting', 'quote': WEAK, 'quote_found': True, 'reason': 'test'}]}}}

    def build(self, cap=12000):
        return packet.build(self.ind, self.sources, self.frozen, cap=cap, keyword_fill=real_fill(self.ind))

    def test_the_rest_of_a_tagged_long_page_stays_reachable(self):
        self.assertGreater(len(self.long_text), packet.WINDOW_CHARS * 2)
        self.assertGreater(self.long_text.index(DECISIVE), packet.WINDOW_CHARS)   # outside the tag's window
        context, trace = self.build()
        self.assertIn(DECISIVE, ' '.join(w['text'] for w in context if w['id'] == 'long'))
        steps = [r['step'] for w in trace['windows'] if w['id'] == 'long' for r in w['reasons']]
        self.assertEqual(steps[0], 'supporting')
        self.assertIn('keyword_fill', steps)

    def test_no_text_is_sent_twice_and_every_window_is_an_exact_span(self):
        context, _ = self.build()
        spans = sorted((w['text_offset'], w['text_offset'] + len(w['text'])) for w in context if w['id'] == 'long')
        for (a, b), (c, d) in zip(spans, spans[1:]):
            self.assertLessEqual(b, c)   # no overlap between the map window and the fill
        for w in context:
            source = self.long if w['id'] == 'long' else self.other
            self.assertEqual(source['text'][w['text_offset']:w['text_offset'] + len(w['text'])], w['text'])

    def test_the_cap_still_holds(self):
        for cap in (12000, 20000, 60000):
            context, _ = self.build(cap)
            self.assertLessEqual(sum(len(w['text']) for w in context), cap)

    def test_a_page_wholly_in_the_packet_is_not_offered_again(self):
        short = {'id': 's', 'document_id': 'd', 'page_number': 1, 'text': DECISIVE}
        frozen = {'pages': {spec.text_hash(DECISIVE): {'page_type': 'other', 'tags': [
            {'indicator': self.ind['code'], 'requirements': [], 'strength': 'direct', 'quote': DECISIVE,
             'quote_found': True, 'reason': 'test'}]}}}
        seen = []

        def fill(pages, max_chars):
            seen.extend(p['id'] for p in pages)
            return []
        packet.build(self.ind, [short, self.other], frozen, cap=12000, keyword_fill=fill)
        self.assertNotIn('s', seen)


MAP = dict(CAPABILITY_RETRIEVAL_MODE='map', CAPABILITY_FOLLOW_UP_SEARCH=False, CAPABILITY_PROMPT_TOKEN_CEILING=None,
           CAPABILITY_EVIDENCE_LANE=False)


class FallbackTests(SimpleTestCase):
    """Item 2: the fallback for a sprint with no map is the wide budget, and its input bound is checked up front."""

    @override_settings(**MAP, CAPABILITY_MAX_INPUT_TOKEN_BOUND=300000)
    def test_map_mode_refuses_a_bound_too_small_for_its_fallback(self):
        # 300,000 holds twice the 60,000 cap but not twice the 200,000 fallback.
        with self.assertRaisesMessage(SemanticRetrievalUnavailable, '400,000'):
            configured_policy()

    @override_settings(**MAP, CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000)
    def test_a_bound_of_twice_the_fallback_is_accepted(self):
        self.assertEqual(configured_policy()['mode'], 'map')

    @override_settings(**MAP, CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000, CAPABILITY_ASSESSMENT_TIMEOUT_SECONDS=None,
                       CAPABILITY_ASSESSMENT_OUTPUT_TOKENS=None, CAPABILITY_GEMINI_REASONING_EFFORT='high')
    def test_map_mode_gets_the_wide_packets_time_and_output_allowance(self):
        from apps.scoring.capability.execution import policy
        frozen = policy()
        self.assertGreaterEqual(frozen['timeout_seconds'], 600)
        self.assertGreaterEqual(frozen['output_tokens'], 64000)


class CoverageTests(TestCase):
    """Item 4: the tagged share is measured on distinct page texts, not on every page."""

    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))

    def job(self, **counts):
        return MapJob.objects.create(sprint=self.sprint, map_version=current_version(), model='m', shape='one',
                                     status=MapJob.Status.COMPLETED, spend_cap_usd=5, **counts)

    def test_duplicates_do_not_count_as_tagged(self):
        # 10,000 readable pages, 7,000 distinct, 5,000 of those tagged: 71%, not the 80% the old formula gave.
        self.job(pages_total=10000, pages_unique=7000, pages_done_before=0, pages_to_tag=7000, pages_tagged=5000)
        out = status(self.sprint)
        self.assertAlmostEqual(out['tagged_share'], 5000 / 7000, places=3)
        self.assertEqual(out['warning'], 'map_incomplete')

    def test_a_resumed_pass_counts_what_was_tagged_before(self):
        self.job(pages_total=10000, pages_unique=7000, pages_done_before=6800, pages_to_tag=200, pages_tagged=200)
        out = status(self.sprint)
        self.assertEqual(out['tagged_share'], 1.0)
        self.assertIsNone(out['warning'])


class StartTests(TestCase):
    """Item 5: two tagging passes queued together must not both start."""

    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))

    def test_a_pass_is_claimed_before_it_reads_anything(self):
        calls = []

        def fake_run(sprint, *, shape, concurrency, job=None):
            calls.append(job)
            # A second task arriving while the first is planning (before the old code created its job row).
            self.assertIsNone(tag_sprint(str(sprint.pk)))
            return job
        with patch('apps.evidence_map.tagging.run', side_effect=fake_run):
            tag_sprint(str(self.sprint.pk))
        self.assertEqual(len(calls), 1)
        self.assertEqual(MapJob.objects.filter(sprint=self.sprint).count(), 1)

    def test_a_claimed_pass_that_cannot_plan_is_marked_failed(self):
        job = tagging.start_job(self.sprint)
        with patch('apps.evidence_map.tagging.plan', side_effect=RuntimeError('database')):
            with self.assertRaises(RuntimeError):
                tagging.run(self.sprint, service=object(), concurrency=1, job=job)
        job.refresh_from_db()
        self.assertEqual(job.status, MapJob.Status.FAILED)
        self.assertIn('database', job.error)


class WarningTests(TestCase):
    """Item 6: the settings check warns about two map-mode traps (warnings only, never a failure)."""

    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))

    @override_settings(**MAP, CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000, EVIDENCE_MAP_AI_MODEL='',
                       CAPABILITY_DEDUPLICATE_PAGES=True, CAPABILITY_REPEAT_SKIP=False)
    def test_two_maps_and_a_wide_fallback_without_repeat_skipping(self):
        from apps.scoring.management.commands.capability_settings_check import deployment_warnings
        for model in ('claude-haiku-5-5', 'gpt-6-luna'):
            MapJob.objects.create(sprint=self.sprint, map_version=current_version(), model=model, shape='one',
                                  status=MapJob.Status.COMPLETED, spend_cap_usd=5)
        warnings = deployment_warnings(self.sprint.pk)
        self.assertTrue(any('CAPABILITY_REPEAT_SKIP' in w for w in warnings))
        self.assertTrue(any('EVIDENCE_MAP_AI_MODEL' in w for w in warnings))
        with override_settings(EVIDENCE_MAP_AI_MODEL='gpt-6-luna', CAPABILITY_REPEAT_SKIP=True):
            self.assertEqual(deployment_warnings(self.sprint.pk), [])
