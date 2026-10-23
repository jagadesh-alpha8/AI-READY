import logging
import time

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.documents.models import Document

from .exceptions import (
    AllRoutersExhausted, ExtractionCancelled, PermanentExtractionError, ProviderQuotaExhausted,
    RecoverableExtractionError,
)
from .services import ExtractionPipeline
from .services.router_pool import get_router_pool, use_lease

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=settings.EXTRACTION_MAX_RETRIES, acks_late=True)
def run_extraction_job(self, job_id):
    """Run one document through the extraction pipeline.

    Recoverable failures (`RecoverableExtractionError`) are retried with
    exponential backoff up to `EXTRACTION_MAX_RETRIES` times, then the job
    is failed. Permanent failures (`PermanentExtractionError`) and any
    error the pipeline doesn't recognize fail the job immediately --
    retrying blindly on an unrecognized error risks masking a real bug
    behind a retry loop instead of surfacing it.
    """
    from .models import ExtractionJob

    try:
        job = ExtractionJob.objects.select_related('sprint', 'document').get(id=job_id)
    except ExtractionJob.DoesNotExist:
        logger.error('extraction.task.missing_job job_id=%s', job_id)
        return None

    # Only a queued, retrying or interrupted job starts. Stopped while still
    # queued: never start it (a Celery revoke alone isn't enough -- a worker
    # restart forgets revoked task ids). Already completed/failed: this is a
    # duplicate delivery of the same message (acks_late), so don't redo it.
    # A job that was stopped and processed again was given a new task id; an
    # older message for it still in the queue must not run it a second time.
    # (A Celery retry keeps the same id.)
    if job.celery_task_id and self.request.id and job.celery_task_id != self.request.id:
        logger.info('extraction.task.skipped_stale job_id=%s task_id=%s', job.id, self.request.id)
        return None
    if not _claim(job):
        logger.info('extraction.task.skipped job_id=%s status=%s', job.id, job.status)
        return None
    started = time.monotonic()
    worker = self.request.hostname or 'local'
    logger.info(
        'extraction.task.running job_id=%s attempt=%d mode=%s worker=%s',
        job.id, self.request.retries + 1, settings.AI_PROCESSING_MODE, worker,
    )

    # multi_router mode: run this job's AI calls on whichever router has a
    # free slot. single mode: pool is None and AI_BASE_URL is used.
    pool = None
    lease = None
    try:
        pool = get_router_pool()  # inside the try: a config error fails the job, not the worker
        if pool is None:
            _start_attempt(job, '')
            with use_lease(None):
                ExtractionPipeline().run(job)
        else:
            # Failover cycle: a router whose provider is out of quota/credit is taken out of rotation and the
            # document starts again on the next one -- each router at most once in this cycle, so it is
            # bounded by the number of routers. Saved results are idempotent (facts by field_key, reviewed
            # ones never overwritten), so a restart on another router never duplicates anything.
            tried = set()
            while True:
                lease = pool.acquire(avoid=job.ai_router, exclude=tried)
                _set_status(job, ExtractionJob.Status.RUNNING, ai_router=lease.router.label)
                _start_attempt(job, lease.router.label)
                logger.info('extraction.task.router job_id=%s router=%s worker=%s', job.id, lease.router.label, worker)
                try:
                    with use_lease(lease):
                        ExtractionPipeline().run(job)
                    break
                except ProviderQuotaExhausted as exc:
                    pool.mark_exhausted(lease.router, exc.reason)
                    tried.add(lease.router.label)
                    _end_attempt(job, 'out_of_credit', f'{exc} Moving the document to the next router.')
                    logger.warning('extraction.task.failover job_id=%s from=%s reason=%s', job.id,
                                   lease.router.label, exc.reason)
                    pool.release(lease)
                    lease = None
    except ExtractionCancelled:
        _end_attempt(job, 'stopped')
        logger.info('extraction.task.stopped job_id=%s step=%s', job.id, job.current_step)
        _advance_sprint_if_all_jobs_done(job.sprint)
        return None
    except AllRoutersExhausted as exc:
        return _handle_all_exhausted(self, job, exc)
    except ProviderQuotaExhausted as exc:
        # Single mode: the one AI account is out of credit -- retrying cannot help until it is topped up.
        _end_attempt(job, 'failed', exc.reason)
        logger.error('extraction.task.quota_exhausted job_id=%s reason=%s', job.id, exc.reason)
        _fail(job, f'{exc} Add credit to the AI account, then press Process to run this document again.')
        return None
    except PermanentExtractionError as exc:
        _end_attempt(job, 'failed', str(exc))
        logger.error('extraction.task.failed_permanent job_id=%s error=%s', job.id, exc)
        _fail(job, str(exc))
        return None
    except RecoverableExtractionError as exc:
        _end_attempt(job, 'retrying', str(exc))
        if lease is not None:
            # Rate limit / timeout / unreachable / 5xx: send the retry elsewhere.
            pool.mark_unhealthy(lease.router)
        return _handle_recoverable(self, job, exc)
    except Exception as exc:
        _end_attempt(job, 'failed', f'Unexpected error: {exc}')
        logger.exception('extraction.task.failed_unexpected job_id=%s', job.id)
        _fail(job, f'Unexpected error: {exc}')
        return None
    finally:
        if lease is not None:
            pool.release(lease)
    _end_attempt(job, 'completed')

    if not _set_status(job, ExtractionJob.Status.COMPLETED, completed_at=timezone.now()):
        # Stopped in the last instant, after its facts were saved: keep the
        # facts, and keep the "cancelled" status the user chose.
        logger.info('extraction.task.stopped_after_finish job_id=%s', job.id)
        _advance_sprint_if_all_jobs_done(job.sprint)
        return None
    try:
        from apps.gaps.evidence_upload import record_processing
        job.refresh_from_db()
        record_processing(job, ok=True)
    except Exception:
        logger.exception('extraction.task.gap_evidence_audit_failed job_id=%s', job.id)
    logger.info(
        'extraction.task.completed job_id=%s mode=%s router=%s worker=%s duration_s=%.1f',
        job.id, settings.AI_PROCESSING_MODE, lease.router.label if lease else 'single', worker,
        time.monotonic() - started,
    )

    _queue_vector_indexing(job.document)
    _advance_sprint_if_all_jobs_done(job.sprint)
    return str(job.id)


def _queue_vector_indexing(document):
    """Hand the finished document to the vector-indexing layer.

    Deliberately a *separate Celery task*, not an eighth pipeline stage: the
    seven stages in `ExtractionJob.Step` are a fixed contract the monitor UI
    renders against, and semantic indexing has its own retry budget and its own
    failure meaning. Splitting them means a Pinecone outage cannot fail an
    extraction job that otherwise succeeded.

    Everything is swallowed. Indexing is an addition to the document workflow
    and must never be able to break it — a failure is recorded on
    `VectorDocumentIndex` and surfaces through the status endpoint instead. When
    the feature is unconfigured this is a no-op that logs nothing.
    """
    try:
        from apps.vector_store.services import indexer

        indexer.queue_document(document)
    except Exception as exc:
        logger.error(
            'extraction.task.vector_queue_failed document_id=%s error=%s', document.id, exc,
        )


def _attempt_log(job):
    from .models import ExtractionJob
    return list(ExtractionJob.objects.filter(id=job.id).values_list('attempts', flat=True).first() or [])


def _save_attempts(job, log):
    from .models import ExtractionJob
    ExtractionJob.objects.filter(id=job.id).update(attempts=log[-50:])
    job.attempts = log[-50:]


def _start_attempt(job, router):
    log = _attempt_log(job)
    log.append({'at': timezone.now().isoformat(), 'router': router, 'outcome': 'running', 'detail': ''})
    _save_attempts(job, log)


def _end_attempt(job, outcome, detail=''):
    """Set the outcome of the current (last, running) attempt; add one when no attempt is running."""
    log = _attempt_log(job)
    if log and log[-1].get('outcome') == 'running':
        log[-1].update(outcome=outcome, detail=str(detail)[:500], ended=timezone.now().isoformat())
    else:
        log.append({'at': timezone.now().isoformat(), 'router': '', 'outcome': outcome, 'detail': str(detail)[:500]})
    _save_attempts(job, log)


def _since_reset(job, outcome):
    """How many attempts of this run (since the job was last processed again) ended with `outcome`."""
    count = 0
    for entry in _attempt_log(job):
        if entry.get('outcome') == 'reset':
            count = 0
        elif entry.get('outcome') == outcome:
            count += 1
    return count


def _handle_all_exhausted(task, job, exc):
    """No router is left (all out of quota/credit, or all tried for this document): wait -- status "retrying"
    with the reason -- and check again later, at most AI_ROUTER_EXHAUSTED_MAX_WAITS times, then fail with the
    reason. Never an endless loop, and never counted against the normal retry budget."""
    from .models import ExtractionJob

    waits = _since_reset(job, 'waiting')
    limit = settings.AI_ROUTER_EXHAUSTED_MAX_WAITS
    if waits >= limit:
        _end_attempt(job, 'failed', str(exc))
        logger.error('extraction.task.routers_exhausted_gave_up job_id=%s waits=%d', job.id, waits)
        _fail(job, f'{exc} Gave up after waiting {waits} time(s). Reactivate a router, then press Process.')
        return None
    _end_attempt(job, 'waiting', str(exc))
    message = (f'Waiting for an AI router ({waits + 1}/{limit}): {exc} Checking again in '
               f'{max(1, settings.AI_ROUTER_EXHAUSTED_RETRY_SECONDS // 60)} min.')
    if not _set_status(job, ExtractionJob.Status.RETRYING, error_message=message):
        return None  # stopped by the user
    logger.warning('extraction.task.routers_exhausted_waiting job_id=%s wait=%d/%d', job.id, waits + 1, limit)
    raise task.retry(exc=exc, countdown=settings.AI_ROUTER_EXHAUSTED_RETRY_SECONDS,
                     max_retries=task.request.retries + 1)


def _handle_recoverable(task, job, exc):
    max_retries = settings.EXTRACTION_MAX_RETRIES
    # Waiting for an exhausted router is not a failed attempt: it does not use up this budget.
    attempt = task.request.retries - _since_reset(job, 'waiting') + 1

    if attempt > max_retries:
        logger.error('extraction.task.retries_exhausted job_id=%s attempts=%d', job.id, attempt)
        _fail(job, f'Failed after {max_retries} retries: {exc}')
        return None

    from .models import ExtractionJob

    if not _set_status(job, ExtractionJob.Status.RETRYING, retry_count=attempt, error_message=str(exc)):
        return None  # stopped by the user -- don't schedule a retry
    logger.warning('extraction.task.retrying job_id=%s attempt=%d error=%s', job.id, attempt, exc)

    countdown = settings.EXTRACTION_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
    raise task.retry(exc=exc, countdown=countdown, max_retries=task.request.retries + 1)


def _fail(job, message):
    from .models import ExtractionJob

    if not _set_status(job, ExtractionJob.Status.FAILED, error_message=message, completed_at=timezone.now()):
        return  # stopped by the user; a stop is not a failure

    if job.document.status != Document.Status.PROCESSED:
        job.document.status = Document.Status.FAILED
        job.document.save(update_fields=['status', 'updated_at'])
    try:
        from apps.facts.evidence_analysis import fail_pending_document_submissions
        fail_pending_document_submissions(job.document, message)
    except Exception:
        logger.exception('extraction.task.evidence_failure_audit_failed document_id=%s', job.document_id)
    try:
        from apps.gaps.evidence_upload import record_processing
        record_processing(job, ok=False, message=message)
    except Exception:
        logger.exception('extraction.task.gap_evidence_audit_failed job_id=%s', job.id)


def _advance_sprint_if_all_jobs_done(sprint):
    from apps.gaps.services import generate_gaps_for_sprint
    from apps.sprints.models import Sprint

    from .models import ExtractionJob

    if sprint.status != Sprint.Status.PROCESSING:
        return
    still_active = sprint.extraction_jobs.filter(
        status__in=[ExtractionJob.Status.PENDING, ExtractionJob.Status.RUNNING, ExtractionJob.Status.RETRYING],
    ).exists()
    if not still_active:
        sprint.status = Sprint.Status.REVIEWING
        sprint.save(update_fields=['status', 'updated_at'])
        created_gaps = generate_gaps_for_sprint(sprint)
        logger.info(
            'extraction.task.gaps_generated sprint_id=%s gaps_created=%d', sprint.id, len(created_gaps),
        )


def _claim(job):
    """Move the job to running if it's pending, retrying, or running (a
    worker that died mid-job, redelivered). Returns False for a cancelled,
    completed or failed job -- a reprocess resets it to pending first, so a
    finished job reaching here is a duplicate message."""
    from .models import ExtractionJob

    started_at = job.started_at or timezone.now()
    updated = ExtractionJob.objects.filter(
        id=job.id,
        status__in=[ExtractionJob.Status.PENDING, ExtractionJob.Status.RETRYING, ExtractionJob.Status.RUNNING],
    ).update(status=ExtractionJob.Status.RUNNING, started_at=started_at, error_message='', updated_at=timezone.now())
    if not updated:
        job.refresh_from_db(fields=['status'])
        return False
    job.status = ExtractionJob.Status.RUNNING
    job.started_at = started_at
    job.error_message = ''
    Document.objects.filter(id=job.document_id).exclude(status=Document.Status.REJECTED).update(
        status=Document.Status.PROCESSING, updated_at=timezone.now(),
    )
    return True


def _set_status(job, status, **fields):
    """Move the job to `status` unless the user has stopped it.

    A conditional UPDATE rather than `job.save()`, so a Stop pressed while this
    worker is mid-document can never be overwritten back to running,
    completed or failed. Returns False if the job was cancelled.
    """
    from .models import ExtractionJob

    updated = ExtractionJob.objects.filter(id=job.id).exclude(
        status=ExtractionJob.Status.CANCELLED,
    ).update(status=status, updated_at=timezone.now(), **fields)
    if not updated:
        job.status = ExtractionJob.Status.CANCELLED
        return False
    job.status = status
    for name, value in fields.items():
        setattr(job, name, value)
    return True
