"""Explicit, metered scenario lifecycle. Never writes actual assessment/advice events."""
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
from apps.scoring.models import (CapabilityRun, InstitutionalPlanVersion, PlanScenario,
                                  PlanScenarioEvent, PlanScenarioExecution)
from .engine import ENGINE_VERSION, assess, validate_release
from .evaluation import select_context
from .execution import policy, AssessmentConflict, AssessmentDisabled, BudgetExceeded, ExecutionStopped
from .provider import MeteredService, UnpricedModel, UsageUnavailable
from .plan_mapping import VERSION, PROMPTS, SCHEMAS, run_pipeline
from .scenarios import VERSION as SCENARIO_VERSION
from .storage import digest


def enabled():
    return settings.CAPABILITY_PLANS_ENABLED


def validate_baseline(run, event):
    inputs = run.inputs
    if (digest(inputs) != run.inputs_hash or event.run_id != run.pk
            or event.payload.get('inputs_hash') != run.inputs_hash
            or inputs.get('engine_version') != ENGINE_VERSION
            or inputs.get('rubric_snapshot_hash') != digest(inputs['rubric'])):
        raise AssessmentConflict('The saved baseline failed its identity or method check.')
    validate_release(inputs['rubric'])
    records = event.payload['records']
    decisions = {r['condition_id']: r['state'] for r in records}
    expected = {c['id'] for i in inputs['rubric']['indicators'] for c in i['conditions']}
    if len(records) != len(expected) or set(decisions) != expected or assess(decisions, inputs['rubric']) != event.payload['result']:
        raise AssessmentConflict('The saved baseline does not replay under its recorded method.')
    return decisions


@transaction.atomic
def start(*, run, user, key, plan_text):
    CapabilityRun.objects.select_for_update().get(pk=run.pk)
    signature = digest({'operation': 'evaluate_institutional_plan', 'run': str(run.pk), 'plan_text': plan_text})
    existing = PlanScenarioExecution.objects.filter(run=run, idempotency_key=key).first()
    if existing:
        if existing.request_hash != signature:
            raise AssessmentConflict('This key names a different plan evaluation.')
        return existing, False
    if not enabled():
        raise AssessmentDisabled('Institutional plan evaluation is not enabled.')
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    if event is None:
        raise ValidationError('A plan evaluation requires a completed assessment.')
    baseline = validate_baseline(run, event)
    if PlanScenarioExecution.objects.filter(run=run, status__in=['queued', 'running']).exists():
        raise AssessmentConflict('Plan evaluation is already active for this baseline.')
    budget = policy()
    budget.update(prompt_version=VERSION, prompt_hash=digest(PROMPTS), schema_hash=digest(SCHEMAS))
    plan = InstitutionalPlanVersion.objects.create(run=run, origin='submitted', text=plan_text, text_hash=digest(plan_text))
    # Bounded source context is explicit, frozen and labelled a subset; no facts are invented.
    asset_sources = select_context({'code': 'plan-assets', 'name': plan_text, 'conditions': []}, run.inputs['sources'])
    inputs = {'version': VERSION, 'scenario_version': SCENARIO_VERSION, 'plan_text': plan_text,
        'plan_hash': plan.text_hash, 'run_inputs_hash': run.inputs_hash, 'assessment_event_id': event.pk,
        'assessment_hash': digest(event.payload), 'baseline_decisions': baseline,
        'rubric': run.inputs['rubric'], 'rubric_snapshot_hash': digest(run.inputs['rubric']),
        'engine_version': run.inputs['engine_version'], 'scope': run.inputs.get('scope'),
        'population': run.inputs['population'], 'reference_period': run.inputs['reference_period'],
        'profile': run.inputs['profile'], 'asset_sources': asset_sources,
        'asset_context_is_subset': True, 'execution_policy': budget,
        'prompt_hash': digest(PROMPTS), 'schema_hash': digest(SCHEMAS)}
    scenario = PlanScenario.objects.create(plan=plan, run=run, assessment_event=event, inputs=inputs, inputs_hash=digest(inputs))
    execution = PlanScenarioExecution.objects.create(scenario=scenario, run=run, requested_by=user,
        idempotency_key=key, request_hash=signature)
    transaction.on_commit(lambda: dispatch(str(scenario.pk), str(execution.task_id)))
    return execution, True


def validate_identity(scenario, completed=None):
    inputs = scenario.inputs
    validate_baseline(scenario.run, scenario.assessment_event)
    if (digest(inputs) != scenario.inputs_hash or scenario.plan.run_id != scenario.run_id
            or digest(scenario.plan.text) != scenario.plan.text_hash
            or inputs['plan_hash'] != scenario.plan.text_hash or inputs['plan_text'] != scenario.plan.text
            or inputs['run_inputs_hash'] != scenario.run.inputs_hash
            or inputs['assessment_event_id'] != scenario.assessment_event_id
            or inputs['assessment_hash'] != digest(scenario.assessment_event.payload)
            or inputs['rubric_snapshot_hash'] != digest(scenario.run.inputs['rubric'])
            or inputs['rubric'] != scenario.run.inputs['rubric']
            or inputs['scope'] != scenario.run.inputs.get('scope')
            or inputs['profile'] != scenario.run.inputs['profile']
            or inputs['population'] != scenario.run.inputs['population']
            or inputs['reference_period'] != scenario.run.inputs['reference_period']
            or inputs['baseline_decisions'] != {r['condition_id']: r['state'] for r in scenario.assessment_event.payload['records']}):
        raise AssessmentConflict('Saved plan and baseline identities do not match.')
    if completed and (completed.payload.get('inputs_hash') != scenario.inputs_hash
            or digest(completed.payload['comparison']) != completed.payload.get('comparison_hash')):
        raise AssessmentConflict('Saved scenario result failed its integrity check.')
    if completed:
        improved = InstitutionalPlanVersion.objects.filter(pk=completed.payload.get('improved_plan_id'),
            run=scenario.run, parent=scenario.plan, origin='suggested').first()
        projection = completed.payload['comparison']['improved']
        if (improved is None or improved.text != projection['text']
                or improved.text_hash != digest(improved.text) or projection['text_hash'] != improved.text_hash):
            raise AssessmentConflict('Saved improved plan does not match this scenario.')


def dispatch(scenario_id, task_id):
    try:
        evaluate_institutional_plan.apply_async(args=[scenario_id, task_id], task_id=task_id, retry=False)
    except Exception:
        finish(scenario_id, 'failed', 'dispatch_failed')


@transaction.atomic
def finish(scenario_id, status, error_code):
    execution = PlanScenarioExecution.objects.select_for_update().get(scenario_id=scenario_id)
    if execution.status not in {'queued', 'running'}:
        return False
    execution.status = status
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['status', 'heartbeat_at'])
    PlanScenarioEvent.objects.create(scenario_id=scenario_id, payload={'kind': 'terminal', 'status': status,
        'error_code': error_code, 'next_action': 'The actual assessment is unchanged. Check limits/configuration or revise the plan, then explicitly request a new evaluation.'})
    return True


@transaction.atomic
def claim(scenario_id, task_id):
    execution = PlanScenarioExecution.objects.select_for_update(of=('self',)).select_related(
        'scenario__run__sprint', 'scenario__plan', 'scenario__assessment_event').get(scenario_id=scenario_id)
    if execution.status != 'queued' or str(execution.task_id) != str(task_id):
        return None
    if not enabled():
        finish(scenario_id, 'failed', 'inference_disabled')
        return None
    execution.status = 'running'
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['status', 'heartbeat_at'])
    return execution


class ScenarioMeter(MeteredService):
    execution_model = PlanScenarioExecution
    execution_key = 'scenario_id'

    def __init__(self, service, execution):
        super().__init__(service, execution, execution_policy=execution.scenario.inputs['execution_policy'], ledger_id=execution.scenario_id)

    def enabled(self):
        return enabled()

    def event(self, state, payload):
        return PlanScenarioEvent.objects.create(scenario_id=self.run_id, payload={'ledger_status': state, **payload})

    def events(self):
        return PlanScenarioEvent.objects.filter(scenario_id=self.run_id)


@transaction.atomic
def stage(scenario_id, label, value):
    execution = PlanScenarioExecution.objects.select_for_update().get(scenario_id=scenario_id)
    if execution.status != 'running' or not enabled():
        raise ExecutionStopped()
    PlanScenarioEvent.objects.create(scenario_id=scenario_id, payload={'kind': 'stage', 'stage': label, 'value': value, 'value_hash': digest(value)})
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['heartbeat_at'])


@shared_task(acks_late=True, max_retries=0, reject_on_worker_lost=False)
def evaluate_institutional_plan(scenario_id, task_id):
    try:
        execution = claim(scenario_id, task_id)
    except PlanScenarioExecution.DoesNotExist:
        return
    if execution is None:
        return
    pool = lease = None
    try:
        scenario = execution.scenario
        validate_identity(scenario)
        inputs = scenario.inputs
        if (inputs['version'] != VERSION or inputs['scenario_version'] != SCENARIO_VERSION
                or inputs['prompt_hash'] != digest(PROMPTS) or inputs['schema_hash'] != digest(SCHEMAS)):
            raise ValueError('Scenario protocol changed.')
        pool = get_router_pool()
        if pool is not None:
            lease = pool.acquire()
        with use_lease(lease):
            service = ScenarioMeter(get_ai_service(), execution)
            with usage_scope(sprint=scenario.run.sprint, stage='institutional_plan_evaluation', capability_run=scenario.run, plan_scenario=scenario):
                comparison = run_pipeline(inputs, service, lambda label, value: stage(scenario_id, label, value))
            with transaction.atomic():
                locked = PlanScenarioExecution.objects.select_for_update().get(scenario_id=scenario_id)
                if locked.status != 'running' or not enabled():
                    if locked.status == 'running':
                        finish(scenario_id, 'failed', 'inference_disabled')
                    return
                validate_identity(scenario)
                improved = comparison['improved']
                version = InstitutionalPlanVersion.objects.create(run=scenario.run, parent=scenario.plan,
                    origin='suggested', text=improved['text'], text_hash=improved['text_hash'])
                PlanScenarioEvent.objects.create(scenario=scenario, payload={'kind': 'completed',
                    'comparison': comparison, 'comparison_hash': digest(comparison),
                    'improved_plan_id': str(version.pk), 'inputs_hash': scenario.inputs_hash,
                    'inference': service.metadata()})
                locked.status = 'completed'
                locked.heartbeat_at = timezone.now()
                locked.save(update_fields=['status', 'heartbeat_at'])
    except ExecutionStopped:
        finish(scenario_id, 'cancelled', 'inference_stopped')
    except BudgetExceeded:
        finish(scenario_id, 'failed', 'budget_exhausted')
    except UnpricedModel:
        finish(scenario_id, 'failed', 'model_pricing_required')
    except UsageUnavailable:
        finish(scenario_id, 'failed', 'usage_telemetry_missing')
    except ProviderQuotaExhausted:
        if pool is not None and lease is not None:
            pool.mark_exhausted(lease.router, 'Plan provider quota exhausted')
        finish(scenario_id, 'failed', 'provider_quota_exhausted')
    except Exception:
        finish(scenario_id, 'failed', 'plan_validation_or_generation_failed')
    finally:
        if pool is not None and lease is not None:
            pool.release(lease)


def summary(execution):
    return {'id': str(execution.scenario_id), 'run_id': str(execution.run_id), 'status': execution.status,
        'requests_reserved': execution.requests_reserved, 'reserved_cost_usd': str(execution.usd_reserved),
        'created_at': execution.created_at, 'heartbeat_at': execution.heartbeat_at,
        'stalled': execution.status in {'queued', 'running'} and execution.heartbeat_at < timezone.now() - timedelta(seconds=settings.CAPABILITY_STALE_SECONDS)}
