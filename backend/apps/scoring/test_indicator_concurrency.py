"""Judging indicators concurrently changes wall-clock time only, never the decisions or their order."""
import json
import threading
import time
import unittest

from django.test import SimpleTestCase, override_settings

from apps.scoring.capability.evaluation import evaluate
from apps.scoring.capability.execution import AssessmentDisabled, policy

SOURCE = {'id': 'document-a:1', 'text': 'The institution approved an AI strategy for the current academic year.'}


class ContentKeyed:
    """Answers from the request content alone (order-independent), optionally slowly; records peak concurrency."""

    def __init__(self, delay=0.0, fail_on=None):
        self.delay, self.fail_on, self.lock = delay, fail_on, threading.Lock()
        self.active = self.peak = self.calls = 0

    def extract_structured_data(self, **kwargs):
        with self.lock:
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.delay)
            conditions = json.loads(kwargs['user_content'])['indicator']['conditions']
            if self.fail_on and any(c['id'].startswith(self.fail_on) for c in conditions):
                raise RuntimeError('provider failure')
            rows = {c['id']: {'state': 'unknown', 'reason': 'Not shown.', 'scope_supported': False,
                              'period_supported': False, 'citations': []} for c in conditions}
            first = conditions[0]['id']
            if first.endswith('.F1'):
                rows[first] = {'state': 'met', 'reason': 'Scoped current evidence supplied.', 'scope_supported': True,
                               'period_supported': True, 'citations': [{'source_id': SOURCE['id'], 'quote': SOURCE['text']}]}
            return {'conditions': rows}
        finally:
            with self.lock:
                self.active -= 1


def run(service, concurrency, **kwargs):
    return evaluate([SOURCE], service=service, population='All institution programmes', reference_period='2025-26',
                    concurrency=concurrency, **kwargs)


class ConcurrencyTests(unittest.TestCase):
    def test_results_and_order_are_identical_to_sequential(self):
        sequential, parallel = run(ContentKeyed(), 1), run(ContentKeyed(), 4)
        self.assertEqual(sequential['records'], parallel['records'])
        self.assertEqual(sequential['traces'], parallel['traces'])
        self.assertEqual((sequential['indicator_calls'], parallel['indicator_calls']), (36, 36))
        self.assertGreater(sum(s == 'met' for s in parallel['decisions'].values()), 30)

    def test_progress_callbacks_arrive_in_rubric_order(self):
        seen = []
        result = run(ContentKeyed(delay=0.01), 4, on_indicator=lambda rows, trace: seen.append(trace['indicator']))
        self.assertEqual(seen, [t['indicator'] for t in result['traces']])
        self.assertEqual(len(seen), 36)

    def test_concurrency_shortens_wall_clock_and_is_bounded(self):
        service = ContentKeyed(delay=0.05)
        started = time.monotonic()
        run(service, 4)
        elapsed = time.monotonic() - started
        self.assertLessEqual(service.peak, 4)
        self.assertGreater(service.peak, 1)
        self.assertLess(elapsed, 36 * 0.05 * 0.6)  # sequential would take at least 1.8 s

    def test_strict_provider_error_in_a_worker_stops_the_run(self):
        with self.assertRaises(RuntimeError):
            run(ContentKeyed(fail_on='AIQIF-C3.'), 4, strict_errors=True)

    def test_non_strict_failure_is_recorded_like_sequential(self):
        sequential = run(ContentKeyed(fail_on='AIQIF-C3.1'), 1)
        parallel = run(ContentKeyed(fail_on='AIQIF-C3.1'), 4)
        self.assertEqual(sequential['records'], parallel['records'])

    def test_rejects_invalid_concurrency(self):
        for value in (0, 9, '4'):
            with self.assertRaises(ValueError):
                run(ContentKeyed(), value)


class TimeLimitPolicyTests(SimpleTestCase):
    base = dict(CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_REQUEST_TIMEOUT_SECONDS=180, CAPABILITY_ASSESSMENT_TIMEOUT_SECONDS=None,
                CAPABILITY_ASSESSMENT_OUTPUT_TOKENS=None, CAPABILITY_OUTPUT_TOKENS=12000, CAPABILITY_MAX_DURATION_SECONDS=None,
                CAPABILITY_GEMINI_REASONING_EFFORT=None, AI_GEMINI_REASONING_EFFORT='low', CAPABILITY_AGREEMENT_PASSES=1,
                CAPABILITY_INDICATOR_CONCURRENCY=4)

    def frozen(self, **changes):
        with override_settings(**{**self.base, **changes}):
            return policy()

    def test_unset_deadline_is_sized_from_calls_concurrency_and_timeout(self):
        frozen = self.frozen()
        self.assertEqual(frozen['max_duration_seconds'], 18 * 180 + 600)
        self.assertEqual(frozen['indicator_concurrency'], 4)

    def test_high_effort_two_passes_gets_long_enough_limits(self):
        frozen = self.frozen(CAPABILITY_GEMINI_REASONING_EFFORT='high', CAPABILITY_AGREEMENT_PASSES=2,
                             CAPABILITY_MAX_HTTP_CALLS=90)
        self.assertEqual((frozen['timeout_seconds'], frozen['output_tokens']), (300, 48000))
        self.assertEqual(frozen['max_duration_seconds'], 23 * 300 + 600)

    def test_sequential_high_effort_deadline_is_capped_at_six_hours(self):
        frozen = self.frozen(CAPABILITY_GEMINI_REASONING_EFFORT='high', CAPABILITY_AGREEMENT_PASSES=2,
                             CAPABILITY_MAX_HTTP_CALLS=90, CAPABILITY_INDICATOR_CONCURRENCY=1)
        self.assertEqual(frozen['max_duration_seconds'], 21600)

    def test_explicit_settings_are_respected(self):
        frozen = self.frozen(CAPABILITY_GEMINI_REASONING_EFFORT='high', CAPABILITY_MAX_DURATION_SECONDS=1800,
                             CAPABILITY_ASSESSMENT_TIMEOUT_SECONDS=200, CAPABILITY_ASSESSMENT_OUTPUT_TOKENS=24000)
        self.assertEqual((frozen['max_duration_seconds'], frozen['timeout_seconds'], frozen['output_tokens']),
                         (1800, 200, 24000))

    def test_invalid_concurrency_disables_assessment(self):
        with self.assertRaises(AssessmentDisabled):
            self.frozen(CAPABILITY_INDICATOR_CONCURRENCY=12)
