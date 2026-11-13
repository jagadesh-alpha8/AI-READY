"""Background jobs for the second assessment layer, metered against the provisional run's second-layer budget.

Four operations, one active job per provisional run at a time (they read and write the same questions, responses
and credit):

    questions  plan the follow-up questions (depth_service.create_questions); one model call per credited condition tried
    checks     check waiting answers and additional evidence (layer2_service.check_pending, check_additional);
               one model call per depth answer with passages found
    depth      judge the depth of credited evidence from checked answers (depth_service.judge_run)
    rejudge    re-judge credit on the provisional packets plus the new passages and publish the final result as a run
               refining the provisional one (layer2_service.rejudge_credit, publish_final); options.publish=false
               only reports what would change

Every model call goes through SecondLayerMeter: it is reserved against the job (which must still be running) and
against the run's SecondLayerBudget, whose limits are frozen when the first job starts (SECOND_LAYER_MAX_HTTP_CALLS
and SECOND_LAYER_MAX_COST_USD, or, when unset, the limits the provisional run's own assessment had). The per-request
settings (output tokens, timeout, reasoning effort, input bound) are the assessment's. Jobs save nothing once
cancelled: each one writes its result in a single transaction that first checks the job is still running.

Checks start on their own: an answer or additional evidence submitted through the API requests a checks job, a checks
job that finds items submitted while it ran starts another, and the periodic sweep (sweep_second_layer_checks) starts
one when a waiting item's documents have finished extraction since the last checks job.

The management commands (depth_questions, layer2_check_pending, depth_judge, layer2_rejudge) still call the same
functions directly and unmetered, with a cap on calls, for consultants working on a frozen export.
"""
import logging
import uuid

from celery import shared_task
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.extraction.exceptions import ProviderQuotaExhausted
from apps.extraction.services.ai_service import get_ai_service
from apps.extraction.services.router_pool import get_router_pool, use_lease
from apps.extraction.usage import usage_scope
from apps.scoring.models import (AdditionalEvidence, CapabilityRun, DepthQuestion, DepthResponse, SecondLayerBudget,
                                 SecondLayerEvent, SecondLayerJob)

from .depth_service import DepthError
from .execution import (AssessmentConflict, AssessmentDisabled, BudgetExceeded, ExecutionDeadlineExceeded,
                        ExecutionStopped, policy)
from .layer2 import Layer2Error
from .provider import MeteredService, UnpricedModel, UsageUnavailable
from .request_recovery import recoverable_failure
from .storage import digest

logger = logging.getLogger(__name__)
ACTIVE = ('queued', 'running')
OPERATIONS = tuple(SecondLayerJob.Operation.values)
STALE_GRACE_SECONDS = 900   # beyond a job's own deadline, before a queued or running job is taken to have lost its worker


def enabled():
    return settings.SECOND_LAYER_JOBS_ENABLED


# ------------------------------------------------------------------ budget and policy


def budget_limits(run):
    """(max requests, max USD) for the run's second layer: the settings, else the run's own assessment limits, else
    (a run created outside the API, or before limits were frozen with runs) the deployment's assessment limits now."""
    from decimal import Decimal, InvalidOperation
    frozen = (run.inputs or {}).get('execution_policy') or {}
    calls = (settings.SECOND_LAYER_MAX_HTTP_CALLS or frozen.get('max_http_calls')
             or settings.CAPABILITY_MAX_HTTP_CALLS)
    cost = settings.SECOND_LAYER_MAX_COST_USD or frozen.get('max_cost_usd') or settings.CAPABILITY_MAX_COST_USD
    try:
        calls, cost = int(calls), Decimal(str(cost))
    except (TypeError, ValueError, InvalidOperation):
        raise AssessmentDisabled('The second-layer budget is not configured (SECOND_LAYER_MAX_HTTP_CALLS and '
                                 'SECOND_LAYER_MAX_COST_USD).')
    if not 1 <= calls <= 1000 or not cost.is_finite() or not 0 < cost <= 100:
        raise AssessmentDisabled('The second-layer budget configuration is invalid.')
    return calls, cost


def ensure_budget(run):
    calls, cost = budget_limits(run)
    budget, _ = SecondLayerBudget.objects.get_or_create(run=run, defaults={'max_http_calls': calls, 'max_cost_usd': cost})
    return budget


def job_policy(operation, budget):
    """The assessment's per-request settings, under this job's stage and the run's second-layer limits."""
    from .depth import PROMPT_VERSION as DEPTH_PROMPTS
    from .layer2 import VERSION as LAYER2_VERSION
    request = policy(stage='assessment')
    duration = settings.SECOND_LAYER_MAX_DURATION_SECONDS or request['max_duration_seconds']
    if type(duration) is not int or not 60 <= duration <= 21600:
        raise AssessmentDisabled('SECOND_LAYER_MAX_DURATION_SECONDS is invalid.')
    return {**request, 'stage': 'second_layer_' + operation, 'max_duration_seconds': duration,
            'max_http_calls': budget.max_http_calls, 'max_cost_usd': str(budget.max_cost_usd),
            'budget': 'shared by every second-layer job of the run', 'layer2_version': LAYER2_VERSION,
            'depth_prompt_version': DEPTH_PROMPTS}


def clean_options(operation, options):
    if operation not in OPERATIONS:
        raise ValidationError({'operation': f'One of: {", ".join(OPERATIONS)}.'})
    options = options or {}
    if not isinstance(options, dict):
        raise ValidationError({'options': 'Must be an object.'})
    allowed = {'questions': {'replace'}, 'rejudge': {'publish'}}.get(operation, set())
    unknown = set(options) - allowed
    if unknown:
        raise ValidationError({'options': f'Unknown for {operation}: {", ".join(sorted(unknown))}.'})
    out = {}
    for key, value in options.items():
        if not isinstance(value, bool):
            raise ValidationError({'options': f'{key} must be true or false.'})
        out[key] = value
    if operation == 'rejudge':
        out.setdefault('publish', True)
    if operation == 'questions':
        out.setdefault('replace', False)
    return out


def preflight(run, operation, options):
    """Cheap refusals before a job is queued (the job checks again when it saves)."""
    run_ref = str(run.pk)
    questions = DepthQuestion.objects.filter(run_ref=run_ref)
    if operation == 'questions':
        if questions.exists() and not options['replace']:
            raise ValidationError('This assessment already has follow-up questions; set options.replace to plan them '
                                  'again.')
        if options['replace'] and DepthResponse.objects.filter(question__run_ref=run_ref).exists():
            raise ValidationError('The institution has answered some questions; they can no longer be replaced.')
    elif operation == 'depth' and not questions.exists():
        raise ValidationError('This assessment has no follow-up questions yet.')
    elif operation == 'checks' and not waiting(run_ref):
        raise ValidationError('Nothing is waiting for a check.')


def waiting(run_ref):
    return (DepthResponse.objects.filter(question__run_ref=run_ref, status=DepthResponse.Status.PENDING).exists()
            or AdditionalEvidence.objects.filter(run_ref=run_ref, status=AdditionalEvidence.Status.PENDING).exists())


# ------------------------------------------------------------------ lifecycle


def _expire_stale(run):
    now = timezone.now()
    for job in SecondLayerJob.objects.select_for_update().filter(run=run, status__in=ACTIVE):
        # A running job's own deadline counts from its start (the meter enforces it); a queued one's from its creation.
        limit = (job.policy or {}).get('max_duration_seconds', 21600) + STALE_GRACE_SECONDS
        if (now - (job.started_at or job.created_at)).total_seconds() > limit:
            _terminal(job, 'failed', 'worker_lost', 'The job outlived its deadline; its worker was lost.')


@transaction.atomic
def start(*, run, operation, user, key, options=None):
    """Queue one job. The same key returns the same job (a different request under it is a conflict)."""
    run = CapabilityRun.objects.select_for_update().get(pk=run.pk)
    options = clean_options(operation, options)
    signature = digest({'run': str(run.pk), 'operation': operation, 'options': options})
    existing = SecondLayerJob.objects.filter(run=run, idempotency_key=key).first()
    if existing:
        if existing.request_hash != signature:
            raise AssessmentConflict('This idempotency key names a different second-layer job.')
        return existing, False
    if not enabled():
        raise AssessmentDisabled('Second-layer jobs are not enabled.')
    from .layer2_service import is_final
    if is_final(run):
        raise ValidationError('This run is a second-layer final result; use its provisional run.')
    if not run.events.filter(state='completed', payload__result__isnull=False).exists():
        raise ValidationError('The second layer needs a completed assessment.')
    _expire_stale(run)
    if SecondLayerJob.objects.filter(run=run, status__in=ACTIVE).exists():
        raise AssessmentConflict('A second-layer job is already active for this assessment.')
    preflight(run, operation, options)
    budget = ensure_budget(run)
    try:
        with transaction.atomic():
            job = SecondLayerJob.objects.create(run=run, operation=operation, options=options, idempotency_key=key,
                                                request_hash=signature, policy=job_policy(operation, budget),
                                                requested_by=user)
    except IntegrityError:   # the run lock serializes starts; this is a last guard
        raise AssessmentConflict('A second-layer job is already active for this assessment.')
    transaction.on_commit(lambda: dispatch(str(job.pk), str(job.task_id)))
    return job, True


def request_checks(run, user, key):
    """Ask for a checks job after a submission; quietly does nothing when one cannot start now (another job is
    active, jobs are off): the running job's follow-on or the sweep picks the item up."""
    try:
        return start(run=run, operation='checks', user=user, key=key)[0]
    except AssessmentConflict:
        return None   # another job is active: its follow-on or the sweep covers this item
    except (AssessmentDisabled, ValidationError) as exc:
        if enabled():   # with jobs on, a refusal leaves answers unchecked: say so in the logs
            logger.warning('Second-layer checks could not start for run %s: %s', run.pk, getattr(exc, 'detail', exc))
        return None


def dispatch(job_id, task_id):
    try:
        run_second_layer_job.apply_async(args=[job_id, task_id], task_id=task_id, retry=False)
    except Exception:
        finish(job_id, 'failed', 'dispatch_failed')


def _terminal(job, status, error_code, detail=''):
    job.status = status
    job.error_code = error_code
    job.detail = detail[:2000]
    job.finished_at = job.heartbeat_at = timezone.now()
    job.save(update_fields=['status', 'error_code', 'detail', 'finished_at', 'heartbeat_at'])
    SecondLayerEvent.objects.create(job=job, payload={'kind': 'terminal', 'status': status, 'error_code': error_code})


@transaction.atomic
def finish(job_id, status, error_code, detail=''):
    """End an active job (failed or cancelled). False when it had already ended."""
    job = SecondLayerJob.objects.select_for_update().get(pk=job_id)
    if job.status not in ACTIVE:
        return False
    _terminal(job, status, error_code, detail)
    return True


@transaction.atomic
def claim(job_id, task_id):
    job = SecondLayerJob.objects.select_for_update(of=('self',)).select_related('run__sprint').get(pk=job_id)
    if job.status != 'queued' or str(job.task_id) != str(task_id):
        return None
    if not enabled():
        _terminal(job, 'failed', 'inference_disabled')
        return None
    job.status = 'running'
    job.started_at = job.heartbeat_at = timezone.now()
    job.save(update_fields=['status', 'started_at', 'heartbeat_at'])
    return job


def commit_point(job_id, *, lock_run=False):
    """Inside the transaction that saves a job's result: refuse unless the job is still running, and mark it completed
    in the same transaction, so a cancellation either wins before anything is saved or arrives after the job ended.
    lock_run: lock the provisional run first, as start() does, when the transaction goes on to lock it anyway
    (publishing) or to queue another job; the same lock order keeps the two from deadlocking."""
    if lock_run:
        run_id = SecondLayerJob.objects.values_list('run_id', flat=True).get(pk=job_id)
        CapabilityRun.objects.select_for_update().get(pk=run_id)
    job = SecondLayerJob.objects.select_for_update().get(pk=job_id)
    if job.status != 'running' or not enabled():
        raise ExecutionStopped()
    job.status = 'completed'
    job.finished_at = job.heartbeat_at = timezone.now()
    job.save(update_fields=['status', 'finished_at', 'heartbeat_at'])
    SecondLayerEvent.objects.create(job=job, payload={'kind': 'terminal', 'status': 'completed', 'error_code': ''})
    return job


def record_result(job_id, result, final_run=None):
    fields = {'result': result}
    if final_run is not None:
        fields['final_run'] = final_run
    SecondLayerJob.objects.filter(pk=job_id).update(**fields)


class SecondLayerMeter(MeteredService):
    """Reserves each request against the job (its status and deadline) and the run's shared second-layer budget."""
    execution_model = SecondLayerJob
    execution_key = 'pk'

    def __init__(self, service, job):
        super().__init__(service, job, execution_policy=job.policy, ledger_id=job.pk)

    def enabled(self):
        return enabled()

    def budget(self, execution):
        return SecondLayerBudget.objects.select_for_update().get(run_id=execution.run_id)

    def limits(self, budget):
        return budget.max_http_calls, budget.max_cost_usd

    def event(self, state, payload):
        return SecondLayerEvent.objects.create(job_id=self.run_id, payload={'ledger_status': state, **payload})

    def events(self):
        return SecondLayerEvent.objects.filter(job_id=self.run_id)


def metered_model(meter):
    """The depth and check code's model interface (system prompt, content, schema, name) over the meter."""
    def call(system_prompt, user_content, response_schema, schema_name):
        return meter.extract_structured_data(system_prompt=system_prompt, user_content=user_content,
                                             response_schema=response_schema, schema_name=schema_name)
    call.model_name = meter.model
    return call


# ------------------------------------------------------------------ operations


def run_questions(job, meter):
    from .depth_service import create_questions
    from .layer2_service import export_for_run
    plan = create_questions(export_for_run(job.run_id), metered_model(meter), commit=True,
                            replace=job.options.get('replace', False), guard=lambda: commit_point(job.pk))
    record_result(job.pk, {'questions': len(plan['questions']), 'notes': plan['notes']})


def run_checks(job, meter):
    from .layer2_service import check_additional, check_pending
    run_ref = str(job.run_id)
    scan_started = timezone.now()
    counts = check_pending(run_ref, metered_model(meter), skip_error=lambda exc: (
        recoverable_failure(exc) and not isinstance(exc, ProviderQuotaExhausted)))
    rubric = job.run.inputs['rubric']
    additional = 0
    for item in AdditionalEvidence.objects.filter(run_ref=run_ref, status=AdditionalEvidence.Status.PENDING):
        check_additional(item, rubric)
        additional += item.status == AdditionalEvidence.Status.CHECKED
    with transaction.atomic():
        commit_point(job.pk, lock_run=True)
        # Submitted while this job ran (its own request for a check met this active job): check them next.
        late = (DepthResponse.objects.filter(question__run_ref=run_ref, status=DepthResponse.Status.PENDING,
                                             created_at__gte=scan_started).exists()
                or AdditionalEvidence.objects.filter(run_ref=run_ref, status=AdditionalEvidence.Status.PENDING,
                                                     created_at__gte=scan_started).exists())
        follow_on = None
        if late and enabled():
            follow_on = SecondLayerJob.objects.create(
                run=job.run, operation='checks', options={}, idempotency_key=f'follow-on-{job.pk}',
                request_hash=digest({'run': run_ref, 'operation': 'checks', 'options': {}}), policy=job.policy,
                requested_by=job.requested_by)
            transaction.on_commit(lambda: dispatch(str(follow_on.pk), str(follow_on.task_id)))
        record_result(job.pk, {**counts, 'additional_checked': additional,
                               'follow_on_job_id': str(follow_on.pk) if follow_on else None})


def run_depth(job, meter):
    from .depth_service import judge_run
    from .layer2_service import export_for_run
    result = judge_run(export_for_run(job.run_id), metered_model(meter), commit=True,
                       guard=lambda: commit_point(job.pk))
    record_result(job.pk, {'judged': [{k: row[k] for k in ('condition_id', 'level', 'final_level', 'final_credit')}
                                      for row in result['judged']],
                           **{k: result[k] for k in ('unanswered', 'answers_without_documents', 'awaiting_check',
                                                     'awaiting_reassessment', 'policy')}})


def run_rejudge(job, meter):
    from .layer2_service import export_for_run, publish_final, rejudge_credit
    result = rejudge_credit(export_for_run(job.run_id), meter, evaluate_options={
        'strict_errors': True, 'recover_provider_errors': True,
        'concurrency': job.policy.get('indicator_concurrency', 1)})
    summary = {k: result.get(k) for k in ('provisional_score', 'final_score', 'targets', 'merge', 'contradictions',
                                          'routes', 'note')}
    final = None
    with transaction.atomic():
        commit_point(job.pk, lock_run=True)
        if job.options.get('publish', True) and result.get('targets'):
            try:
                final = publish_final(result, service=meter, user=job.requested_by)
            except ValueError as exc:   # storage.publish's own refusals (a citation or excerpt that does not match)
                raise Layer2Error(f'The final result could not be published: {exc}')
            summary['note'] = 'Published as the final result.'
        elif result.get('targets'):
            summary['note'] = 'Not published (options.publish was false).'
        record_result(job.pk, {**summary, 'final_run_id': str(final.pk) if final else None}, final_run=final)


RUNNERS = {'questions': run_questions, 'checks': run_checks, 'depth': run_depth, 'rejudge': run_rejudge}


@shared_task(acks_late=True, max_retries=0, reject_on_worker_lost=False)
def run_second_layer_job(job_id, task_id):
    try:
        job = claim(job_id, task_id)
    except SecondLayerJob.DoesNotExist:
        return
    if job is None:
        return
    pool = lease = None
    try:
        pool = get_router_pool()
        if pool is not None:
            lease = pool.acquire()
        with use_lease(lease):
            meter = SecondLayerMeter(get_ai_service(), job)
            with usage_scope(sprint=job.run.sprint, stage='capability_second_layer', capability_run=job.run):
                RUNNERS[job.operation](job, meter)
    except ExecutionStopped:
        finish(job_id, 'cancelled', 'inference_stopped')
    except ExecutionDeadlineExceeded:
        finish(job_id, 'failed', 'execution_deadline_exceeded')
    except BudgetExceeded:
        finish(job_id, 'failed', 'budget_exhausted', 'The run\'s second-layer budget is spent; a consultant can raise '
                                                     'it with the layer2_budget command.')
    except UnpricedModel:
        finish(job_id, 'failed', 'model_pricing_required')
    except UsageUnavailable:
        finish(job_id, 'failed', 'usage_telemetry_missing')
    except ProviderQuotaExhausted:
        if pool is not None and lease is not None:
            pool.mark_exhausted(lease.router, 'Second-layer provider quota exhausted')
        finish(job_id, 'failed', 'provider_quota_exhausted')
    except (Layer2Error, DepthError) as exc:
        finish(job_id, 'failed', 'not_ready', str(exc))   # our own refusals, safe to show
    except Exception:
        # Never store exception strings: SDK errors can contain document text or keys.
        finish(job_id, 'failed', 'job_failed')
    finally:
        if pool is not None and lease is not None:
            pool.release(lease)


# ------------------------------------------------------------------ periodic sweep


def _documents_settled(document_ids):
    """(all extracted or given up on, latest change) for a waiting item's documents."""
    from apps.documents.models import Document
    if not document_ids:
        return True, None
    rows = Document.objects.filter(pk__in=document_ids)
    busy = rows.filter(status__in=[Document.Status.PENDING, Document.Status.UPLOADED, Document.Status.PROCESSING])
    return not busy.exists(), rows.aggregate(latest=Max('updated_at'))['latest']


def due_for_checks(run_ref):
    """True when a waiting item became checkable after the run's last checks job was created: it was submitted, or
    its documents finished extraction, since then. An item a checks job already tried (and left waiting) is not
    retried until something about it changes."""
    last = SecondLayerJob.objects.filter(run_id=run_ref, operation='checks').aggregate(latest=Max('created_at'))['latest']
    items = list(DepthResponse.objects.filter(question__run_ref=run_ref, status=DepthResponse.Status.PENDING)
                 .values_list('created_at', 'document_ids'))
    items += list(AdditionalEvidence.objects.filter(run_ref=run_ref, status=AdditionalEvidence.Status.PENDING)
                  .values_list('created_at', 'document_ids'))
    for created, documents in items:
        settled, changed = _documents_settled(documents)
        if not settled:
            continue
        became_ready = max(t for t in (created, changed) if t is not None)
        if last is None or became_ready > last:
            return True
    return False


@shared_task
def sweep_second_layer_checks():
    """Start a checks job for every run with an item that became checkable since its last checks job."""
    if not enabled():
        return 0
    refs = set(DepthResponse.objects.filter(status=DepthResponse.Status.PENDING)
               .values_list('question__run_ref', flat=True))
    refs |= set(AdditionalEvidence.objects.filter(status=AdditionalEvidence.Status.PENDING)
                .values_list('run_ref', flat=True))
    started = 0
    for ref in sorted(refs):
        run = CapabilityRun.objects.filter(pk=ref).first() if _is_uuid(ref) else None
        if run is None or not due_for_checks(run.pk):
            continue
        if request_checks(run, None, f'sweep-{uuid.uuid4().hex}') is not None:
            started += 1
    return started


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


# ------------------------------------------------------------------ reading


def summary(job):
    return {'id': str(job.pk), 'run_id': str(job.run_id), 'operation': job.operation, 'options': job.options,
            'status': job.status, 'error_code': job.error_code or None, 'detail': job.detail or None,
            'result': job.result or None, 'final_run_id': str(job.final_run_id) if job.final_run_id else None,
            'requests_reserved': job.requests_reserved, 'usd_reserved': str(job.usd_reserved),
            'created_at': job.created_at, 'started_at': job.started_at, 'finished_at': job.finished_at}


def budget_summary(run):
    budget = SecondLayerBudget.objects.filter(run=run).first()
    if budget is None:
        return None
    return {'max_http_calls': budget.max_http_calls, 'max_cost_usd': str(budget.max_cost_usd),
            'requests_reserved': budget.requests_reserved, 'usd_reserved': str(budget.usd_reserved)}
