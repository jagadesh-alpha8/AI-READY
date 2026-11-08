"""End-to-end capability run with concurrent indicators on a committed database.

Worker threads use their own database connections, so this needs a transactional test case (data committed,
as in production) rather than the shared-transaction TestCase used by the other API tests.
"""
import contextlib

from django.test import override_settings
from rest_framework.test import APITransactionTestCase

from apps.extraction.models import AIUsage

from .test_capability_api import CapabilityAPITests

SETTINGS = dict(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True,
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
