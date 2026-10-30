"""Independent bounded advice execution. Never writes assessment events."""
import json
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.extraction.exceptions import ProviderQuotaExhausted
from apps.extraction.services.ai_service import get_ai_service
from apps.extraction.services.router_pool import get_router_pool, use_lease
from apps.extraction.usage import usage_scope
from apps.scoring.models import CapabilityRun, RecommendationSnapshot, RecommendationExecution, RecommendationEvent
from .execution import policy, AssessmentConflict, AssessmentDisabled, BudgetExceeded, ExecutionStopped
from .provider import MeteredService, UnpricedModel, UsageUnavailable
from .recommendations import build_inputs, validate_advice, VERSION, PROMPT, SCHEMA
from .storage import digest


def enabled():
    return settings.CAPABILITY_RECOMMENDATIONS_ENABLED


@transaction.atomic
def start(*, run, user, key):
    CapabilityRun.objects.select_for_update().get(pk=run.pk)
    signature = digest({'run': str(run.pk), 'operation': 'tailor_recommendations'})
    existing = RecommendationExecution.objects.filter(run=run, idempotency_key=key).first()
    if existing:
        if existing.request_hash != signature:
            raise AssessmentConflict()
        return existing, False
    if not enabled():
        raise AssessmentDisabled('Recommendation inference is not enabled.')
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    if event is None:
        raise ValidationError('Recommendations require a completed assessment.')
    if RecommendationExecution.objects.filter(run=run, status__in=['queued', 'running']).exists():
        raise AssessmentConflict('Recommendation generation is already active for this assessment.')
    budget = policy()
    budget.update(prompt_version=VERSION, prompt_hash=digest(PROMPT), schema_hash=digest(SCHEMA))
    inputs = build_inputs(run, event, budget)
    snapshot = RecommendationSnapshot.objects.create(run=run, assessment_event=event, inputs=inputs, inputs_hash=digest(inputs))
    execution = RecommendationExecution.objects.create(snapshot=snapshot, run=run, requested_by=user,
                                                       idempotency_key=key, request_hash=signature)
    transaction.on_commit(lambda: dispatch(str(snapshot.pk), str(execution.task_id)))
    return execution, True


def dispatch(snapshot_id, task_id):
    try:
        generate_recommendations.apply_async(args=[snapshot_id, task_id], task_id=task_id, retry=False)
    except Exception:
        finish(snapshot_id, 'failed', 'dispatch_failed')


@transaction.atomic
def finish(snapshot_id, status, error_code):
    execution = RecommendationExecution.objects.select_for_update().get(snapshot_id=snapshot_id)
    if execution.status not in {'queued', 'running'}:
        return False
    execution.status = status
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['status', 'heartbeat_at'])
    RecommendationEvent.objects.create(snapshot_id=snapshot_id, payload={'kind': 'terminal', 'status': status,
        'error_code': error_code, 'next_action': 'Use the pinned deterministic plan. Review configuration, billing and limits before explicitly starting a new version.'})
    return True


@transaction.atomic
def claim(snapshot_id, task_id):
    execution = RecommendationExecution.objects.select_for_update(of=('self',)).select_related('snapshot__run__sprint', 'snapshot__assessment_event').get(snapshot_id=snapshot_id)
    if execution.status != 'queued' or str(execution.task_id) != str(task_id):
        return None
    if not enabled():
        finish(snapshot_id, 'failed', 'inference_disabled')
        return None
    execution.status = 'running'
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['status', 'heartbeat_at'])
    return execution


class RecommendationMeter(MeteredService):
    execution_model = RecommendationExecution
    execution_key = 'snapshot_id'

    def __init__(self, service, execution):
        super().__init__(service, execution, execution_policy=execution.snapshot.inputs['execution_policy'], ledger_id=execution.snapshot_id)

    def enabled(self):
        return enabled()

    def event(self, state, payload):
        return RecommendationEvent.objects.create(snapshot_id=self.run_id, payload={'ledger_status': state, **payload})

    def events(self):
        return RecommendationEvent.objects.filter(snapshot_id=self.run_id)


@transaction.atomic
def save_batch(snapshot_id, indicator, advice):
    execution = RecommendationExecution.objects.select_for_update().get(snapshot_id=snapshot_id)
    if execution.status != 'running' or not enabled():
        raise ExecutionStopped()
    RecommendationEvent.objects.create(snapshot_id=snapshot_id, payload={'kind': 'advice_batch', 'indicator': indicator, 'advice': advice})
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['heartbeat_at'])


@shared_task(acks_late=True, max_retries=0, reject_on_worker_lost=False)
def generate_recommendations(snapshot_id, task_id):
    try:
        execution = claim(snapshot_id, task_id)
    except RecommendationExecution.DoesNotExist:
        return
    if execution is None:
        return
    pool = lease = service = None
    try:
        snapshot = execution.snapshot
        inputs = snapshot.inputs
        if (digest(inputs) != snapshot.inputs_hash or inputs['version'] != VERSION
                or inputs['prompt_hash'] != digest(PROMPT) or inputs['schema_hash'] != digest(SCHEMA)
                or digest(snapshot.assessment_event.payload) != inputs['assessment_hash']):
            finish(snapshot_id, 'failed', 'snapshot_or_methodology_mismatch')
            return
        # With no source grounding there is nothing to tailor safely; deterministic evidence requests suffice.
        model_actions = [a for a in inputs['actions'] if a['state'] != 'unknown']
        needs_model = bool(model_actions and snapshot.run.inputs['sources'])
        if needs_model:
            pool = get_router_pool()
            if pool is not None:
                lease = pool.acquire()
        # Missing evidence never authorizes a model-generated intervention. Render scoped
        # requests from frozen requirements; preserve development advice for proven shortfalls.
        advice = [{'condition_id': a['id'], 'operation': a['operation'],
                   'steps': [f"Request evidence for {a['requirement']} covering {inputs['population']} in {inputs['reference_period']}."],
                   'suggested_role': 'Evidence coordinator (suggested)', 'effort': 'unknown',
                   'dependencies': [], 'completion_evidence': a['completion_evidence'],
                   'basis': a['citations'], 'origin': 'deterministic_evidence_request'}
                  for a in inputs['actions'] if a['state'] == 'unknown']
        with use_lease(lease):
            service = RecommendationMeter(get_ai_service(), execution) if needs_model else None
            with usage_scope(sprint=snapshot.run.sprint, stage='capability_recommendations',
                             capability_run=snapshot.run, recommendation_snapshot=snapshot):
                if service:
                    for indicator in dict.fromkeys(a['indicator'] for a in model_actions):
                        actions = [a for a in model_actions if a['indicator'] == indicator]
                        payload = {k: inputs[k] for k in ('profile', 'population', 'reference_period')}
                        payload['actions'] = actions
                        response = service.extract_structured_data(system_prompt=PROMPT, user_content=json.dumps(payload),
                            response_schema=SCHEMA, schema_name='capability_advice')
                        batch = validate_advice(response, actions)
                        save_batch(snapshot_id, indicator, batch)
                        advice.extend(batch)
            with transaction.atomic():
                locked = RecommendationExecution.objects.select_for_update().get(snapshot_id=snapshot_id)
                if locked.status != 'running' or not enabled():
                    if locked.status == 'running':
                        finish(snapshot_id, 'failed', 'inference_disabled')
                    return
                RecommendationEvent.objects.create(snapshot=snapshot, payload={'kind': 'completed',
                    'advice': advice, 'inputs_hash': snapshot.inputs_hash,
                    'mode': 'tailored' if service else 'deterministic',
                    'inference': service.metadata() if service else {'provider': 'none', 'model': 'none', 'calls': []}})
                locked.status = 'completed'
                locked.heartbeat_at = timezone.now()
                locked.save(update_fields=['status', 'heartbeat_at'])
    except ExecutionStopped:
        finish(snapshot_id, 'cancelled', 'inference_stopped')
    except BudgetExceeded:
        finish(snapshot_id, 'failed', 'budget_exhausted')
    except UnpricedModel:
        finish(snapshot_id, 'failed', 'model_pricing_required')
    except UsageUnavailable:
        finish(snapshot_id, 'failed', 'usage_telemetry_missing')
    except ProviderQuotaExhausted:
        if pool is not None and lease is not None:
            pool.mark_exhausted(lease.router, 'Recommendation provider quota exhausted')
        finish(snapshot_id, 'failed', 'provider_quota_exhausted')
    except Exception:
        finish(snapshot_id, 'failed', 'tailoring_failed')
    finally:
        if pool is not None and lease is not None:
            pool.release(lease)


def summary(execution):
    return {'id': str(execution.snapshot_id), 'run_id': str(execution.run_id), 'status': execution.status,
            'requests_reserved': execution.requests_reserved, 'reserved_cost_usd': str(execution.usd_reserved),
            'created_at': execution.created_at, 'heartbeat_at': execution.heartbeat_at,
            'stalled': execution.status in {'queued', 'running'} and execution.heartbeat_at < timezone.now() - timedelta(seconds=settings.CAPABILITY_STALE_SECONDS)}
