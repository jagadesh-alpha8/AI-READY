"""End-to-end capability run with concurrent indicators on a committed database.

Worker threads use their own database connections, so this needs a transactional test case (data committed,
as in production) rather than the shared-transaction TestCase used by the other API tests.
"""
import contextlib

from django.test import override_settings
from rest_framework.test import APITransactionTestCase

from apps.extraction.models import AIUsage

from .test_capability_api import CapabilityAPITests

SETTINGS = dict(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True, CAPABILITY_JUDGMENT='conditions',
                CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000,
                CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_RATE_LIMIT_ENABLED=False,
                AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
                AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')


class ConcurrentRunTests(APITransactionTestCase):
    setUp = CapabilityAPITests.setUp
    response = CapabilityAPITests.response
    start = CapabilityAPITests.start
    execute = CapabilityAPITests.execute

    @contextlib.contextmanager
    def captureOnCommitCallbacks(self, execute=False):
        yield []  # autocommit: on_commit callbacks already ran when the transaction committed

    def run_with(self, concurrency, key):
        with override_settings(**SETTINGS, CAPABILITY_INDICATOR_CONCURRENCY=concurrency):
            execution = self.execute(self.start(key))
        return execution, self.client.get(f'{self.url}/{execution.run_id}').data['assessment']

    def test_concurrent_run_completes_with_the_same_decisions_billing_and_attribution(self):
        execution, assessment = self.run_with(4, 'concurrent-1')
        self.assertEqual(execution.status, 'completed')
        self.assertEqual(execution.requests_reserved, 36)
        # Usage attribution is a ContextVar: every request must still be attributed to this run.
        self.assertEqual(AIUsage.objects.filter(capability_run=execution.run).count(), 36)
        self.assertEqual(len(assessment['records']), 216)
        self.assertEqual([r['condition_id'] for r in assessment['records'] if r['state'] == 'unknown'],
                         ['AIQIF-C3.1.F1'])
        self.assertEqual(len(assessment['inference']['calls']), 72)  # one reservation and one outcome per request
        self.assertEqual(len({c['request_number'] for c in assessment['inference']['calls'] if 'request_number' in c}), 36)
        self.assertEqual(assessment['inference']['settings']['indicator_concurrency'], 4)


class PartJudgmentRunTests(APITransactionTestCase):
    """The part-judgment path end to end: two passes, four workers, publication, documented readiness."""
    setUp = CapabilityAPITests.setUp
    start = CapabilityAPITests.start
    execute = CapabilityAPITests.execute
    captureOnCommitCallbacks = ConcurrentRunTests.captureOnCommitCallbacks

    def response(self, **kwargs):
        import json
        from types import SimpleNamespace
        payload = json.loads(kwargs['messages'][1]['content'])
        quote = payload['sources'][0]
        rows = {c['id']: {'reason': 'Every part shown.', 'scope_supported': True, 'period_supported': True,
                          'findings': [{'part_id': p['id'], 'finding': 'full',
                                        'citations': [{'source_id': quote['id'], 'quote': quote['text']}]}
                                       for p in c['parts']]}
                for c in payload['indicator']['conditions']}
        return SimpleNamespace(model='actual-test-model',
            usage=SimpleNamespace(prompt_tokens=200, completion_tokens=150, prompt_tokens_details=None,
                                  completion_tokens_details=None, total_tokens=350),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
                content=json.dumps({'conditions': rows}), refusal=None))])

    def test_part_run_publishes_credits_and_documented_readiness(self):
        with override_settings(**{**SETTINGS, 'CAPABILITY_MAX_HTTP_CALLS': 90, 'CAPABILITY_JUDGMENT': 'parts'},
                               CAPABILITY_INDICATOR_CONCURRENCY=4, CAPABILITY_AGREEMENT_PASSES=2):
            execution = self.execute(self.start('parts-1'))
        self.assertEqual(execution.status, 'completed')
        self.assertEqual(execution.requests_reserved, 72)
        assessment = self.client.get(f'{self.url}/{execution.run_id}').data['assessment']
        records = {r['condition_id']: r for r in assessment['records']}
        self.assertEqual(len(records), 216)
        self.assertEqual(assessment['inference']['settings']['judgment'], 'parts')
        # The strict syllabus-approval regex does not apply under the reviewer standard: every part is evidenced.
        self.assertEqual(records['AIQIF-C3.1.F1']['state'], 'met')
        self.assertTrue(all(r['credit'] == 1.0 for r in records.values()))
        self.assertEqual(assessment['result']['score'], assessment['result']['documented']['overall'])
        result = assessment['result']
        self.assertEqual(result['documented_with_digital'], result['documented'])  # no digital-only findings
        self.assertGreaterEqual(result['documented']['overall'], result['lower'])
        self.assertLessEqual(result['documented']['overall'], result['upper'])
