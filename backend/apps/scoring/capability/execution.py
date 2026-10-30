"""Explicit assessment start/dispatch, idempotency, cancellation and safe terminal states."""
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.scoring.models import CapabilityExecution, CapabilityRunEvent
from apps.sprints.models import Sprint
from .storage import create_run, digest, checkpoint


class AssessmentConflict(APIException):
    status_code = 409
    default_detail = 'An assessment is already active, or this idempotency key names a different request.'


class AssessmentDisabled(APIException):
    status_code = 503
    default_detail = 'Capability inference is not enabled. Ask the deployment administrator to configure it.'


class ExecutionStopped(Exception):
    pass


class BudgetExceeded(Exception):
    pass


def policy():
    from .evaluation import PROMPT_VERSION, SYSTEM_PROMPT, DECISION_SCHEMA
    calls = settings.CAPABILITY_MAX_HTTP_CALLS
    cost = Decimal(str(settings.CAPABILITY_MAX_COST_USD))
    output = settings.CAPABILITY_OUTPUT_TOKENS
    timeout = settings.CAPABILITY_REQUEST_TIMEOUT_SECONDS
    if (type(calls) is not int or not 1 <= calls <= 108 or not cost.is_finite() or not 0 < cost <= 100
            or type(output) is not int or not 256 <= output <= 16000
            or type(timeout) is not int or not 1 <= timeout <= 300):
        raise AssessmentDisabled('Assessment budget configuration is invalid.')
    return {'prompt_version': PROMPT_VERSION, 'prompt_hash': digest(SYSTEM_PROMPT),
            'schema_hash': digest(DECISION_SCHEMA), 'max_http_calls': calls, 'max_cost_usd': str(cost), 'output_tokens': output,
            'timeout_seconds': timeout, 'sdk_retries': 0, 'transient_retries_per_indicator': 1,
            'cost_policy': 'reserve_utf8_bytes_plus_4096_tokens_at_configured_max_rates'}


@transaction.atomic
def start(*, sprint, user, idempotency_key, population, reference_period):
    # Serializes competing keys as well as repeated requests for this sprint (PostgreSQL).
    Sprint.objects.select_for_update().get(pk=sprint.pk)
    signature = digest({'population': population, 'reference_period': reference_period})
    existing = CapabilityExecution.objects.filter(sprint=sprint, idempotency_key=idempotency_key).first()
    if existing:
        if existing.request_hash != signature:
            raise AssessmentConflict('This idempotency key was already used for different assessment inputs.')
        return existing, False
    if not settings.CAPABILITY_ASSESSMENT_ENABLED:
        raise AssessmentDisabled()
    if CapabilityExecution.objects.filter(sprint=sprint, status__in=['queued', 'running']).exists():
        raise AssessmentConflict()
    run = create_run(institution_id=sprint.institution_id, sprint_id=sprint.pk,
                     population=population, reference_period=reference_period, execution_policy=policy())
    execution = CapabilityExecution.objects.create(run=run, sprint=sprint, requested_by=user,
        idempotency_key=idempotency_key, request_hash=signature)
    # Never dispatch before the frozen evidence and idempotency record commit.
    transaction.on_commit(lambda: dispatch(str(run.pk), str(execution.task_id)))
    return execution, True


def dispatch(run_id, task_id):
    from apps.scoring.tasks import run_capability_assessment
    try:
        run_capability_assessment.apply_async(args=[run_id, task_id], task_id=task_id, retry=False)
    except Exception:
        # Broker timeout may have enqueued the task. A terminal ledger makes late delivery a no-op.
        finish(run_id, 'failed', 'dispatch_failed')


@transaction.atomic
def claim(run_id, task_id):
    execution = CapabilityExecution.objects.select_for_update(of=('self',)).select_related('run', 'sprint').get(run_id=run_id)
    if execution.status != 'queued' or str(execution.task_id) != str(task_id):
        return None
    if not settings.CAPABILITY_ASSESSMENT_ENABLED:
        finish(run_id, 'failed', 'inference_disabled')
        return None
    execution.status = 'running'
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['status', 'heartbeat_at'])
    checkpoint(institution_id=execution.sprint.institution_id, run_id=run_id, state='running')
    return execution


@transaction.atomic
def finish(run_id, state, error_code):
    execution = CapabilityExecution.objects.select_for_update().get(run_id=run_id)
    if execution.status not in {'queued', 'running'}:
        return False
    execution.status = state
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['status', 'heartbeat_at'])
    # Fixed internal codes only, never exceptions or provider response bodies.
    actions = {
        'dispatch_failed': 'Check the broker and worker configuration, then start a new assessment.',
        'inference_disabled': 'Enable configured capability inference before starting a new assessment.',
        'model_pricing_required': 'Configure valid input/output model prices, then start a new assessment.',
        'budget_exhausted': 'Review partial decisions and request/cost limits before starting a new assessment.',
        'usage_telemetry_missing': 'Configure the provider to report token usage before starting a new assessment.',
        'provider_quota_exhausted': 'Restore provider credit or quota before starting a new assessment.',
    }
    CapabilityRunEvent.objects.create(run_id=run_id, state=state, payload={
        'error_code': error_code, 'next_action': actions.get(error_code,
            'Start a new assessment with a new idempotency key.')})
    return True


@transaction.atomic
def progress(run_id, records, trace):
    execution = CapabilityExecution.objects.select_for_update().get(run_id=run_id)
    if execution.status != 'running':
        raise ExecutionStopped()
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['heartbeat_at'])
    CapabilityRunEvent.objects.create(run_id=run_id, state='partial', payload={
        'kind': 'indicator', 'indicator': trace['indicator'], 'records': records, 'trace': trace})
