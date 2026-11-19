"""capability_settings_check: what differs between the settings a run was scored with and this deployment."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APITestCase

from .management.commands.capability_settings_check import check
from .models import CapabilityExecution, CapabilityRun, CapabilityRunEvent

SETTINGS = dict(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True, CAPABILITY_MAX_HTTP_CALLS=90, CAPABILITY_TIE_BREAK=True, CAPABILITY_GEMINI_REASONING_EFFORT='high',
                CAPABILITY_MAX_COST_USD='6', CAPABILITY_OUTPUT_TOKENS=12000, CAPABILITY_REQUEST_TIMEOUT_SECONDS=180,
                CAPABILITY_MAX_INPUT_TOKEN_BOUND=160000, CAPABILITY_JUDGMENT='parts', CAPABILITY_AGREEMENT_PASSES=2,
                CAPABILITY_RETRIEVAL_MODE='bm25', AI_MODEL='gemini-3.8-flash', FACT_VERIFICATION_MODE='enforce',
                AI_RATE_LIMIT_ENABLED=False, AI_PROCESSING_MODE='single', AI_BASE_URL='')


@override_settings(**SETTINGS)
class SettingsCheckTests(APITestCase):
    def setUp(self):
        from apps.accounts.models import User
        from apps.documents.models import Document
        from apps.extraction.models import DocumentPage
        from apps.institutions.models import Institution
        from apps.sprints.models import Sprint
        institution = Institution.objects.create(name='College')
        self.sprint = Sprint.objects.create(institution=institution)
        user = User.objects.create_user(username='coordinator', email='coord@example.com',
                                        role=User.Role.IQAC_COORDINATOR, institution=institution)
        self.client.force_authenticate(user)
        doc = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', status='processed')
        DocumentPage.objects.create(document=doc, page_number=1, text='Institutional evidence for 2025-26.')
        with patch('apps.scoring.capability.execution.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                started = self.client.post(f'/api/v1/sprints/{self.sprint.pk}/capability-runs',
                                           {'population': 'All', 'reference_period': '2025-26'}, format='json',
                                           HTTP_IDEMPOTENCY_KEY='run')
        self.assertEqual(started.status_code, 202, started.data)
        self.run = CapabilityRun.objects.get(pk=started.data['id'])
        CapabilityExecution.objects.filter(run=self.run).update(status='completed')
        CapabilityRunEvent.objects.create(run=self.run, state='completed', payload={
            'result': {'score': 1}, 'records': [], 'traces': [],
            'inference': {'provider': 'gemini', 'model': 'gemini-3.8-flash', 'calls': []}})

    def command(self):
        out = StringIO()
        try:
            call_command('capability_settings_check', str(self.run.pk), stdout=out)
            code = 0
        except SystemExit as exc:
            code = exc.code
        return code, out.getvalue()

    def kinds(self):
        return {(d['section'], d['setting']): d['kind'] for d in check(self.run)['differences']}

    def test_the_same_settings_show_no_difference(self):
        self.assertEqual(check(self.run)['differences'], [])
        code, out = self.command()
        self.assertEqual(code, 0, out)
        self.assertIn('Scoring: none', out)

    def test_retrieval_effort_and_model_differences_affect_scoring(self):
        # The three Jagadesh's comparison and the model decision were about: hybrid vs bm25, the input bound,
        # and a different model.
        with override_settings(CAPABILITY_MAX_INPUT_TOKEN_BOUND=131072, AI_MODEL='gemma4:31b',
                               CAPABILITY_GEMINI_REASONING_EFFORT='low'):
            kinds = self.kinds()
            code, out = self.command()
        self.assertEqual(kinds[('model', 'AI_MODEL')], 'scoring')
        self.assertEqual(kinds[('execution_policy', 'input_token_bound_limit')], 'scoring')
        self.assertEqual(kinds[('execution_policy', 'gemini_reasoning_effort')], 'scoring')
        self.assertIn('input_token_bound_limit', out)
        self.assertIn('[CAPABILITY_MAX_INPUT_TOKEN_BOUND]', out)   # says which setting to change
        self.assertEqual(code, 1)
        with override_settings(CAPABILITY_RETRIEVAL_MODE='hybrid', CAPABILITY_EMBEDDING_PATH='/nowhere'):
            result = check(self.run)
        # Hybrid without its embedding model cannot be built here: reported, never passed silently.
        self.assertTrue(any(e.startswith('retrieval_policy') for e in result['errors']), result)

    def test_budgets_and_timeouts_are_limits_only(self):
        with override_settings(CAPABILITY_MAX_COST_USD='2', CAPABILITY_ASSESSMENT_TIMEOUT_SECONDS=400):
            kinds = self.kinds()
            code, out = self.command()
        self.assertEqual(kinds[('execution_policy', 'max_cost_usd')], 'limits only')
        self.assertEqual(kinds[('execution_policy', 'timeout_seconds')], 'limits only')
        self.assertEqual(code, 0, out)

    def test_an_earlier_credit_rule_is_its_own_kind(self):
        # The run is frozen (immutable), so change today's rule instead: the same comparison seen from the other side.
        with patch('apps.scoring.capability.part_judgment.RELATED_CREDIT', 0.5):
            self.assertEqual(self.kinds(), {('execution_policy', 'related_credit'): 'credit rule'})
            self.assertEqual(self.command()[0], 0)

    def test_a_settings_file_on_the_code_defaults_is_not_the_run_that_used_two_passes(self):
        with override_settings(CAPABILITY_AGREEMENT_PASSES=1, CAPABILITY_TIE_BREAK=False, CAPABILITY_MAX_HTTP_CALLS=72):
            kinds = self.kinds()
        self.assertEqual((kinds[('execution_policy', 'agreement_passes')], kinds[('execution_policy', 'tie_break')]),
                         ('scoring', 'scoring'))

    def test_fact_verification_in_shadow_is_flagged(self):
        with override_settings(FACT_VERIFICATION_MODE='shadow'):
            code, out = self.command()
        self.assertIn('FACT_VERIFICATION_MODE is not enforce', out)
