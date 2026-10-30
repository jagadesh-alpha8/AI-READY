"""Capability worker: one claimed execution, no whole-run retries or GET-triggered inference."""
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.extraction.exceptions import ProviderQuotaExhausted
from apps.extraction.services.ai_service import get_ai_service
from apps.extraction.services.router_pool import get_router_pool, use_lease
from apps.extraction.usage import usage_scope
from .capability.evaluation import evaluate, SYSTEM_PROMPT, DECISION_SCHEMA
from .capability.engine import ENGINE_VERSION
from .capability.execution import BudgetExceeded, ExecutionStopped, claim, finish, progress
from .capability.provider import MeteredService, UnpricedModel, UsageUnavailable
from .capability.storage import publish, digest
from .models import CapabilityExecution


@shared_task(acks_late=True, max_retries=0, reject_on_worker_lost=False)
def run_capability_assessment(run_id, task_id):
    try:
        execution = claim(run_id, task_id)
    except CapabilityExecution.DoesNotExist:
        return
    if execution is None:
        return
    pool = lease = None
    try:
        inputs = execution.run.inputs
        policy = inputs['execution_policy']
        if (digest(inputs) != execution.run.inputs_hash or inputs['engine_version'] != ENGINE_VERSION
                or policy['prompt_hash'] != digest(SYSTEM_PROMPT) or policy['schema_hash'] != digest(DECISION_SCHEMA)):
            finish(run_id, 'failed', 'snapshot_or_methodology_mismatch')
            return
        has_sources = bool(inputs['sources'])
        if has_sources:
            pool = get_router_pool()
            if pool is not None:
                lease = pool.acquire()
        with use_lease(lease):
            service = MeteredService(get_ai_service(), execution) if has_sources else None
            with usage_scope(sprint=execution.sprint, stage='evidence_assessment', capability_run=execution.run):
                evaluation = evaluate(execution.run.inputs['sources'], service=service,
                    population=execution.run.inputs['population'], reference_period=execution.run.inputs['reference_period'],
                    rubric=execution.run.inputs['rubric'], strict_errors=True,
                    on_indicator=lambda rows, trace: progress(run_id, rows, trace))
            # Same lock order as cancellation; completion and ledger become visible atomically.
            with transaction.atomic():
                locked = CapabilityExecution.objects.select_for_update().get(run_id=run_id)
                if locked.status != 'running':
                    return
                publish(institution_id=execution.sprint.institution_id, run_id=run_id,
                        evaluation=evaluation, inference=service.metadata() if service else {
                            'provider': 'none', 'model': 'none', 'settings': execution.run.inputs['execution_policy'], 'calls': []})
                locked.status = 'completed'
                locked.heartbeat_at = timezone.now()
                locked.save(update_fields=['status', 'heartbeat_at'])
    except ExecutionStopped:
        finish(run_id, 'cancelled', 'inference_stopped')
    except BudgetExceeded:
        finish(run_id, 'failed', 'budget_exhausted')
    except UnpricedModel:
        finish(run_id, 'failed', 'model_pricing_required')
    except UsageUnavailable:
        finish(run_id, 'failed', 'usage_telemetry_missing')
    except ProviderQuotaExhausted:
        if pool is not None and lease is not None:
            pool.mark_exhausted(lease.router, 'Capability provider quota exhausted')
        finish(run_id, 'failed', 'provider_quota_exhausted')
    except Exception:
        # Never log/store exception strings: SDK errors can contain document text or keys.
        finish(run_id, 'failed', 'evaluation_failed')
    finally:
        if pool is not None and lease is not None:
            pool.release(lease)

# Import registers the independent advice task during Celery app discovery.
from .capability.recommendation_execution import generate_recommendations  # noqa: F401,E402
