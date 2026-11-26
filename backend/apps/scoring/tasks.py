"""Capability worker: one claimed execution, no whole-run retries or GET-triggered inference."""
import logging
import traceback

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.extraction.exceptions import ProviderQuotaExhausted
from apps.scoring.capability.model_choice import scoring_service as get_ai_service
from apps.extraction.services.router_pool import get_router_pool, use_lease
from apps.extraction.usage import usage_scope
from .capability.evaluation import evaluate, SYSTEM_PROMPT, DECISION_SCHEMA, RETRIEVAL_VERSION
from .capability.engine import ENGINE_VERSION
from .capability.execution import BudgetExceeded, ExecutionDeadlineExceeded, ExecutionStopped, claim, finish, progress
from .capability.provider import MeteredService, UnpricedModel, UsageUnavailable
from .capability.storage import publish, digest
from .models import CapabilityExecution


logger = logging.getLogger(__name__)


def failure_outline(exc):
    """What broke, without any message text: the exception classes down the chain, an HTTP status, and the last place
    in our code it passed through. e.g. "PermanentExtractionError <- BadRequestError (status 400) at
    apps/extraction/services/anthropic_client.py:190"."""
    chain, seen, current = [], set(), exc
    while current is not None and id(current) not in seen and len(chain) < 4:
        seen.add(id(current))
        status = getattr(current, 'status_code', None)
        chain.append(type(current).__name__ + (f' (status {status})' if isinstance(status, int) else ''))
        current = current.__cause__ or current.__context__
    where = ''
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if '/apps/' in frame.filename.replace('\\', '/'):
            where = ' at apps/' + frame.filename.replace('\\', '/').split('/apps/', 1)[1] + f':{frame.lineno}'
            break
    return ' <- '.join(chain) + where


def locked_progress(run_id, rows, trace):
    from apps.extraction.usage import DB_WRITE_LOCK
    with DB_WRITE_LOCK:  # workers may be writing their request ledger at the same moment
        return progress(run_id, rows, trace)


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
                or inputs.get('assessment_protocol', {}).get('retrieval_version') != RETRIEVAL_VERSION
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
                    rubric=execution.run.inputs['rubric'], strict_errors=True, recover_provider_errors=True, scope=inputs.get('scope'),
                    reviewed_evidence=inputs.get('reviewed_evidence'), retrieval_policy=inputs.get('retrieval_policy'),
                    agreement_passes=policy.get('agreement_passes', 1),
                    concurrency=policy.get('indicator_concurrency', 1),
                    judgment=policy.get('judgment', 'conditions'),
                    tie_break=policy.get('tie_break') in ('majority-of-three-v1', 'median-credit-of-three-v1'),
                    quote_repair=policy.get('part_quote_repair') == 'quote-repair-v1',
                    evidence_map=inputs.get('evidence_map'),
                    on_indicator=lambda rows, trace: locked_progress(run_id, rows, trace))
            if evaluation.get('circuit_skipped_indicators'):
                # The provider stopped answering partway (23 Nov: Gemini's 503s left test run 80952be2 "completed" with
                # all 36 key indicators unknown, and the screens showed it as the latest result). Such a run is not a
                # result: it fails, so the screens keep the last real one, and a new assessment can be started.
                finish(run_id, 'failed', 'model_unavailable')
                return
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
            # A Stage 1 result: write its report text and publish it once that passes the draft gate (never raises).
            from .capability.publication import keep_going
            keep_going(execution.run)
            from apps.evidence_map.tasks import queue_learning
            queue_learning(execution.run)
    except ExecutionStopped:
        finish(run_id, 'cancelled', 'inference_stopped')
    except ExecutionDeadlineExceeded:
        finish(run_id, 'failed', 'execution_deadline_exceeded')
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
    except Exception as exc:
        # Never log/store exception strings: SDK errors can contain document text or keys. The exception's class, where
        # it was raised and an HTTP status are safe and say what broke (25 Nov audit, finding 9: no reason anywhere).
        logger.error('Capability run %s failed: %s', run_id, failure_outline(exc))
        finish(run_id, 'failed', 'evaluation_failed')
    finally:
        if pool is not None and lease is not None:
            pool.release(lease)

# Import registers the independent advice task during Celery app discovery.
from .capability.recommendation_execution import generate_recommendations  # noqa: F401,E402
from .capability.plan_execution import evaluate_institutional_plan  # noqa: F401,E402
from .capability.second_layer_jobs import run_second_layer_job, sweep_second_layer_checks  # noqa: F401,E402
