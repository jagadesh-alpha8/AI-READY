import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.extraction.models import AIUsage
from apps.extraction.services.openai_client import OpenAIExtractionService
from . import test_capability_api as fixtures
from .capability.storage import create_run, checkpoint, publish
from .capability.evaluation import evaluate
from .capability.recommendations import validate_advice, threshold_plan
from .capability.recommendation_execution import generate_recommendations, finish, dispatch
from .models import RecommendationExecution, RecommendationSnapshot


@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_RECOMMENDATIONS_ENABLED=True,
    CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000,
    CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_RATE_LIMIT_ENABLED=False, AI_PROCESSING_MODE='single',
    AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
class RecommendationTests(APITestCase):
    def setUp(self):
        fixtures.CapabilityAPITests.setUp(self)
        self.prepare_run()
        self.sdk.chat.completions.create.side_effect = self.response

    def prepare_run(self):
        self.run = create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk,
                              population='All faculty and students', reference_period='2025-26')
        checkpoint(institution_id=self.institution.pk, run_id=self.run.pk, state='running')
        evaluation = evaluate([], service=None, population='All', reference_period='2025-26')
        if self.page.status != 'unreadable':
            for row in evaluation['records']:
                row.update(state='not_met', reason='Scoped documented shortfall', scope_supported=True,
                           period_supported=True, citations=[{'source_id': str(self.page.pk), 'quote': self.page.text}])
        publish(institution_id=self.institution.pk, run_id=self.run.pk,
            evaluation=evaluation,
            inference={'provider': 'none', 'model': 'none', 'settings': {}, 'calls': []})
        self.original_events = list(self.run.events.values_list('id', 'payload'))
        self.url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{self.run.pk}/recommendations'

    def rows(self, actions):
        return [{'condition_id': a['id'], 'operation': a['operation'],
                 'steps': ['Request scoped records for ' + a['requirement']],
                 'suggested_role': 'Evidence coordinator (suggested)', 'effort': 'unknown',
                 'dependencies': [], 'completion_evidence': 'Verify ' + str(a['completion_evidence']),
                 'basis': a['citations']} for a in actions]

    def response(self, **kwargs):
        payload = json.loads(kwargs['messages'][1]['content'])
        return SimpleNamespace(model='actual-test-model',
            usage=SimpleNamespace(prompt_tokens=200, completion_tokens=150, prompt_tokens_details=None,
                                  completion_tokens_details=None, total_tokens=350),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
                content=json.dumps({'advice': self.rows(payload['actions'])}), refusal=None))])

    def start(self, key='advice-1'):
        with patch('apps.scoring.capability.recommendation_execution.dispatch') as send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, {}, format='json', HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(response.status_code, 202, response.data)
            send.assert_called_once()
        return RecommendationExecution.objects.get(snapshot_id=response.data['id'])

    def execute(self, execution, base_url=None):
        service = OpenAIExtractionService(api_key='sk-test', model='test-model', client=self.sdk, base_url=base_url)
        with patch('apps.scoring.capability.recommendation_execution.get_ai_service', return_value=service), patch(
                'apps.scoring.capability.recommendation_execution.get_router_pool', return_value=None):
            generate_recommendations.run(str(execution.snapshot_id), str(execution.task_id))
        execution.refresh_from_db()
        return execution

    def detail(self, execution):
        return self.client.get(f'{self.url}/{execution.snapshot_id}').data

    def unchanged(self):
        self.assertEqual(list(self.run.events.values_list('id', 'payload')), self.original_events)

    def test_full_framework_tailoring_and_immutable_history(self):
        ex = self.execute(self.start())
        self.assertEqual(ex.status, 'completed')
        data = self.detail(ex)
        self.assertFalse(data['fallback'])
        self.assertEqual(len(data['plan']['current_standing']['indicators']), 36)
        self.assertEqual(len({a['indicator'] for a in data['plan']['actions']}), 36)
        self.assertEqual({a['condition_id'] for a in data['tailoring']['advice']}, {a['id'] for a in data['plan']['actions']})
        self.assertEqual([p['target'] for p in data['plan']['pathways']], ['Silver', 'Gold', 'Platinum'])
        self.assertEqual(data['plan']['current_standing']['exact_score'], 0)
        self.assertEqual(data['plan']['next_overall']['target'], 10)
        self.assertEqual(ex.requests_reserved, 36)
        self.assertEqual(AIUsage.objects.filter(recommendation_snapshot=ex.snapshot, capability_run=self.run).count(), 36)
        self.unchanged()
        with self.assertRaises(ValueError):
            RecommendationSnapshot.objects.filter(pk=ex.snapshot_id).update(inputs={})
        with self.assertRaises(ValueError):
            ex.snapshot.events.last().save()
        with self.assertRaises(ValueError):
            ex.snapshot.save()
        self.execute(ex)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 36)

    def test_reads_replays_and_new_versions(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(RecommendationSnapshot.objects.count(), 0)
        ex = self.start()
        with patch('apps.scoring.capability.recommendation_execution.dispatch') as send:
            with self.captureOnCommitCallbacks(execute=True):
                result = self.client.post(self.url, {}, format='json', HTTP_IDEMPOTENCY_KEY='advice-1')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data['id'], str(ex.snapshot_id))
            self.detail(ex)
            self.assertFalse(send.called)
        self.assertEqual(self.client.post(self.url, {}, format='json', HTTP_IDEMPOTENCY_KEY='advice-2').status_code, 409)
        finish(ex.snapshot_id, 'cancelled', 'cancelled_by_user')
        self.assertNotEqual(self.start('advice-2').snapshot_id, ex.snapshot_id)
        self.assertEqual(self.client.post(self.url, {'budget': 'new'}, format='json', HTTP_IDEMPOTENCY_KEY='advice-1').status_code, 400)
        self.unchanged()

    def test_tenant_and_unauthenticated_boundaries(self):
        ex = self.start()
        aid = ex.snapshot.inputs['actions'][0]['id']
        self.assertEqual(self.client.get(self.url.replace(str(self.sprint.pk), str(self.other_sprint.pk))).status_code, 403)
        self.user.institution = self.other
        self.user.save()
        for path in [self.url, f'{self.url}/{ex.snapshot_id}']:
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}, format='json', HTTP_IDEMPOTENCY_KEY='x').status_code, 403)
        self.assertEqual(self.client.post(f'{self.url}/{ex.snapshot_id}/cancel').status_code, 403)
        self.assertEqual(self.client.patch(f'{self.url}/{ex.snapshot_id}/actions/{aid}', {'status': 'completed'}).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_workflow_completion_never_changes_advice_or_scores(self):
        ex = self.start()
        aid = ex.snapshot.inputs['actions'][0]['id']
        url = f'{self.url}/{ex.snapshot_id}/actions/{aid}'
        response = self.client.patch(url, {'owner': 'Coordinator', 'feasibility': 'feasible', 'status': 'completed'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.patch(url, {'status': 'in_progress'}, format='json').status_code, 200)
        self.assertEqual(self.detail(ex)['action_states'][0]['owner'], 'Coordinator')
        for payload in ({'score': 100}, {'status': 'arbitrary'}):
            self.assertEqual(self.client.patch(url, payload, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url.replace(aid, 'foreign-condition'), {'status': 'completed'}).status_code, 400)
        self.unchanged()

    def test_cancel_queued_and_inflight(self):
        ex = self.start()
        generate_recommendations.run(str(ex.snapshot_id), 'wrong-task')
        self.client.post(f'{self.url}/{ex.snapshot_id}/cancel')
        self.execute(ex)
        self.assertEqual(ex.status, 'cancelled')
        self.assertFalse(self.sdk.chat.completions.create.called)
        second = self.start('advice-2')
        def cancel(**kwargs):
            finish(second.snapshot_id, 'cancelled', 'cancelled_by_user')
            return self.response(**kwargs)
        self.sdk.chat.completions.create.side_effect = cancel
        self.execute(second)
        self.assertEqual(second.status, 'cancelled')
        self.assertEqual(second.requests_reserved, 1)
        self.assertEqual(AIUsage.objects.filter(recommendation_snapshot=second.snapshot).count(), 1)
        self.assertIsNone(self.detail(second)['tailoring'])
        self.assertTrue(self.detail(second)['fallback'])
        self.unchanged()

    @override_settings(CAPABILITY_MAX_HTTP_CALLS=1)
    def test_call_budget_keeps_fallback_without_partial_publication(self):
        ex = self.execute(self.start())
        self.assertEqual(ex.status, 'failed')
        self.assertEqual(ex.requests_reserved, 1)
        self.assertEqual(self.detail(ex)['error']['error_code'], 'budget_exhausted')
        self.assertIsNone(self.detail(ex)['tailoring'])
        self.assertTrue(self.detail(ex)['plan']['actions'])
        self.assertEqual(ex.snapshot.events.filter(payload__kind='advice_batch').count(), 1)

    @override_settings(CAPABILITY_MAX_COST_USD='0.000001')
    def test_cost_budget_prevents_first_call(self):
        ex = self.execute(self.start())
        self.assertEqual(ex.status, 'failed')
        self.assertFalse(self.sdk.chat.completions.create.called)
        self.assertEqual(ex.requests_reserved, 0)

    @override_settings(AI_PRICING_JSON='')
    def test_unpriced_model_prevents_spending(self):
        ex = self.execute(self.start())
        self.assertEqual(self.detail(ex)['error']['error_code'], 'model_pricing_required')
        self.assertFalse(self.sdk.chat.completions.create.called)

    def test_missing_usage_retains_reservation(self):
        def response(**kw):
            result = self.response(**kw)
            result.usage = None
            return result
        self.sdk.chat.completions.create.side_effect = response
        ex = self.execute(self.start())
        self.assertEqual(ex.requests_reserved, 1)
        self.assertEqual(self.detail(ex)['error']['error_code'], 'usage_telemetry_missing')

    def test_provider_and_broker_failures_are_safe(self):
        ex = self.start()
        self.sdk.chat.completions.create.side_effect = RuntimeError('SECRET')
        self.execute(ex)
        self.assertEqual(ex.status, 'failed')
        self.assertNotIn('SECRET', str(list(ex.snapshot.events.values_list('payload', flat=True))))
        second = self.start('advice-2')
        with patch('apps.scoring.capability.recommendation_execution.generate_recommendations.apply_async', side_effect=RuntimeError('SECRET')):
            dispatch(str(second.snapshot_id), str(second.task_id))
        self.execute(second)
        self.assertEqual(self.detail(second)['error']['error_code'], 'dispatch_failed')
        self.assertEqual(self.sdk.chat.completions.create.call_count, 1)

    @override_settings(CAPABILITY_MAX_HTTP_CALLS=2)
    def test_correction_calls_are_metered(self):
        count = [0]
        def malformed(**kwargs):
            response = self.response(**kwargs)
            count[0] += 1
            if count[0] == 1:
                response.choices[0].message.content = 'not json'
            return response
        self.sdk.chat.completions.create.side_effect = malformed
        ex = self.execute(self.start(), base_url='https://example.invalid/v1')
        self.assertEqual(ex.requests_reserved, 2)
        self.assertEqual(ex.status, 'failed')
        self.assertEqual(AIUsage.objects.filter(recommendation_snapshot=ex.snapshot).count(), 2)

    def test_empty_evidence_uses_deterministic_requests_without_provider(self):
        self.page.status = 'unreadable'
        self.page.save()
        self.prepare_run()
        ex = self.start()
        with patch('apps.scoring.capability.recommendation_execution.get_ai_service') as factory, patch(
                'apps.scoring.capability.recommendation_execution.get_router_pool') as pool:
            generate_recommendations.run(str(ex.snapshot_id), str(ex.task_id))
        ex.refresh_from_db()
        self.assertEqual(ex.status, 'completed')
        self.assertEqual(ex.requests_reserved, 0)
        self.assertFalse(factory.called)
        self.assertFalse(pool.called)
        self.assertTrue(self.detail(ex)['fallback'])

    def test_router_lease_released(self):
        ex = self.start()
        pool, lease = MagicMock(), MagicMock()
        pool.acquire.return_value = lease
        service = OpenAIExtractionService(api_key='sk-test', model='test-model', client=self.sdk)
        with patch('apps.scoring.capability.recommendation_execution.get_router_pool', return_value=pool), patch(
                'apps.scoring.capability.recommendation_execution.get_ai_service', return_value=service), patch(
                'apps.scoring.capability.recommendation_execution.use_lease') as use:
            generate_recommendations.run(str(ex.snapshot_id), str(ex.task_id))
        use.assert_called_once_with(lease)
        pool.release.assert_called_once_with(lease)
        ex.refresh_from_db()
        self.assertEqual(ex.status, 'completed')

    def test_grounding_action_kind_duplicate_and_dependency_validation(self):
        ex = self.start()
        def fabricate(**kwargs):
            response = self.response(**kwargs)
            data = json.loads(response.choices[0].message.content)
            data['advice'][0]['basis'] = [{'source_id': 'foreign', 'quote': 'invented'}]
            response.choices[0].message.content = json.dumps(data)
            return response
        self.sdk.chat.completions.create.side_effect = fabricate
        self.execute(ex)
        self.assertEqual(ex.status, 'failed')
        self.assertTrue(self.detail(ex)['fallback'])
        actions = ex.snapshot.inputs['actions'][:2]
        rows = self.rows(actions)
        validate_advice({'advice': rows}, actions)
        for mode in ('kind', 'duplicate', 'cycle', 'foreign'):
            bad = deepcopy(rows)
            if mode == 'kind':
                bad[0]['operation'] = 'gather_evidence'
            elif mode == 'duplicate':
                bad[1] = bad[0]
            elif mode == 'cycle':
                bad[0]['dependencies'] = [bad[1]['condition_id']]
                bad[1]['dependencies'] = [bad[0]['condition_id']]
            else:
                bad[0]['dependencies'] = ['foreign']
            with self.assertRaises(ValueError):
                validate_advice({'advice': bad}, actions)

    def test_disabled_and_noncompleted_inputs(self):
        with override_settings(CAPABILITY_RECOMMENDATIONS_ENABLED=False):
            self.assertEqual(self.client.post(self.url, {}, format='json', HTTP_IDEMPOTENCY_KEY='x').status_code, 503)
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 400)
        run = create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk, population='All', reference_period='2025-26')
        self.assertEqual(self.client.post(self.url.replace(str(self.run.pk), str(run.pk)), {}, format='json', HTTP_IDEMPOTENCY_KEY='x').status_code, 400)

    def test_versioned_threshold_policy(self):
        from .capability.engine import assess
        rubric = self.run.inputs['rubric']
        all_met = {c['id']: 'met' for i in rubric['indicators'] for c in i['conditions']}
        policy = {'version': 'custom', 'thresholds': [25, 50, 100]}
        self.assertIsNone(threshold_plan(assess(all_met, rubric), rubric, policy)['target'])
        path = threshold_plan(assess({}, rubric), rubric, policy)
        self.assertEqual(path['target'], 25)
        self.assertTrue(path['scenario_sufficient'])

    def test_missing_evidence_never_goes_to_model_and_bounds_remain_uncertain(self):
        # New assessment leaves one entire indicator unknown, with documented shortfalls elsewhere.
        self.run = create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk, population='All', reference_period='2025-26')
        checkpoint(institution_id=self.institution.pk, run_id=self.run.pk, state='running')
        evaluation = evaluate([], service=None, population='All', reference_period='2025-26')
        unknown = {c['id'] for c in self.run.inputs['rubric']['indicators'][0]['conditions']}
        for row in evaluation['records']:
            if row['condition_id'] not in unknown:
                row.update(state='not_met', reason='Scoped shortfall', scope_supported=True, period_supported=True,
                           citations=[{'source_id': str(self.page.pk), 'quote': self.page.text}])
        publish(institution_id=self.institution.pk, run_id=self.run.pk, evaluation=evaluation,
                inference={'provider': 'none', 'model': 'none', 'settings': {}, 'calls': []})
        self.url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{self.run.pk}/recommendations'
        ex = self.execute(self.start())
        self.assertEqual(ex.status, 'completed')
        data = self.detail(ex)
        self.assertIsNone(data['plan']['current_standing']['exact_score'])
        self.assertGreater(data['plan']['current_standing']['upper'], 0)
        requests = [json.loads(c.kwargs['messages'][1]['content']) for c in self.sdk.chat.completions.create.call_args_list]
        self.assertFalse(any(a['state'] == 'unknown' for req in requests for a in req['actions']))
        evidence_advice = [a for a in data['tailoring']['advice'] if a['condition_id'] in unknown]
        self.assertTrue(evidence_advice)
        self.assertTrue(all(a['origin'] == 'deterministic_evidence_request' for a in evidence_advice))

    def test_contradictions_cannot_drop_an_inconvenient_source(self):
        actions = [{'id': 'C1', 'operation': 'reconcile_sources', 'type': 'resolve_contradiction',
                    'requirement': 'Resolve this disagreement', 'completion_evidence': 'Reconciled sources', 'citations': [
                        {'source_id': 'a', 'quote': 'Contradiction from source one'},
                        {'source_id': 'b', 'quote': 'Contradiction from source two'}]}]
        rows = self.rows(actions)
        validate_advice({'advice': rows}, actions)
        rows[0]['basis'] = rows[0]['basis'][:1]
        with self.assertRaises(ValueError):
            validate_advice({'advice': rows}, actions)

    def test_anthropic_uses_independent_usage_and_ledger(self):
        from apps.extraction.services.anthropic_client import AnthropicExtractionService
        ex = self.start()
        def response(**kwargs):
            actions = json.loads(kwargs['messages'][0]['content'])['actions']
            return SimpleNamespace(model='actual-test-model', stop_reason='tool_use',
                usage=SimpleNamespace(input_tokens=200, output_tokens=150, cache_read_input_tokens=0, cache_creation_input_tokens=0),
                content=[SimpleNamespace(type='tool_use', name='capability_advice', input={'advice': self.rows(actions)})])
        self.sdk.messages.create.side_effect = response
        service = AnthropicExtractionService(api_key='sk-ant-test', model='test-model', client=self.sdk)
        with patch('apps.scoring.capability.recommendation_execution.get_ai_service', return_value=service), patch(
                'apps.scoring.capability.recommendation_execution.get_router_pool', return_value=None):
            generate_recommendations.run(str(ex.snapshot_id), str(ex.task_id))
        ex.refresh_from_db()
        self.assertEqual(ex.status, 'completed')
        self.assertEqual(ex.requests_reserved, 36)
        self.assertEqual(AIUsage.objects.filter(recommendation_snapshot=ex.snapshot).count(), 36)
        self.unchanged()

    def test_snapshot_mismatch_and_disabled_worker_spend_nothing(self):
        ex = self.start()
        with override_settings(CAPABILITY_RECOMMENDATIONS_ENABLED=False):
            self.execute(ex)
        self.assertEqual(ex.status, 'failed')
        self.assertFalse(self.sdk.chat.completions.create.called)
        second = self.start('advice-2')
        with patch('apps.scoring.capability.recommendation_execution.VERSION', 'unsupported'):
            self.execute(second)
        self.assertEqual(second.status, 'failed')
        self.assertFalse(self.sdk.chat.completions.create.called)
        self.assertEqual(self.detail(second)['error']['error_code'], 'snapshot_or_methodology_mismatch')
