import logging
import random
import time
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.documents.models import Document

from .exceptions import (
    AllRoutersExhausted, ExtractionCancelled, ExtractionContinues, ExtractionSuperseded, PermanentExtractionError,
    ProviderQuotaExhausted, RecoverableExtractionError,
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
    worker = self.request.hostname or 'local'
    if not _claim(job, worker):
        logger.info('extraction.task.skipped job_id=%s status=%s', job.id, job.status)
        return None
    # Checked at every checkpoint (pipeline._is_cancelled): if the job is handed to another worker meanwhile,
    # this one abandons it instead of both carrying on.
    job.task_token = job.celery_task_id or self.request.id or ''
    started = time.monotonic()
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
    except ExtractionSuperseded:
        # Recovered and handed to another worker while this one was quiet: leave the job to its new owner.
        logger.warning('extraction.task.superseded job_id=%s worker=%s', job.id, worker)
        return None
    except ExtractionContinues as exc:
        return _handle_continue(self, job, exc)
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


def _handle_continue(task, job, exc):
    """A large document: this attempt read its share of chunks and saved them; carry on in the next attempt
    right away. Not a retry (no budget used) -- bounded by EXTRACTION_MAX_CONTINUATIONS."""
    from .models import ExtractionJob

    from django.db.models import F

    ExtractionJob.objects.filter(id=job.id).update(continuations=F('continuations') + 1)
    job.refresh_from_db(fields=['continuations'])
    continues = job.continuations - 1
    _end_attempt(job, 'continued', str(exc))
    if continues + 1 > settings.EXTRACTION_MAX_CONTINUATIONS:
        _fail(job, f'{exc} Stopped after {continues + 1} continuations (EXTRACTION_MAX_CONTINUATIONS); press '
                   'Process to carry on -- the chunks already read are kept.')
        return None
    if not _set_status(job, ExtractionJob.Status.RETRYING, error_message=f'Continuing: {exc}',
                       next_retry_at=timezone.now() + timedelta(seconds=settings.EXTRACTION_CONTINUE_DELAY_SECONDS)):
        return None
    logger.info('extraction.task.continuing job_id=%s done=%d total=%d', job.id, exc.done, exc.total)
    raise task.retry(exc=exc, countdown=settings.EXTRACTION_CONTINUE_DELAY_SECONDS,
                     max_retries=task.request.retries + 1)


def _continuations(job):
    from .models import ExtractionJob
    return ExtractionJob.objects.filter(id=job.id).values_list('continuations', flat=True).first() or 0


def retry_countdown(attempt, exc=None):
    """Seconds before retry `attempt` (1-based): exponential backoff with jitter (50-100% of
    EXTRACTION_RETRY_BACKOFF_SECONDS x 2^(attempt-1)), never sooner than the provider's Retry-After, never
    longer than EXTRACTION_RETRY_MAX_BACKOFF_SECONDS. The jitter keeps many documents that failed together
    (one provider outage) from all coming back at the same second."""
    base = settings.EXTRACTION_RETRY_BACKOFF_SECONDS * (2 ** (max(1, attempt) - 1))
    delay = base * random.uniform(0.5, 1.0)
    retry_after = getattr(exc, 'retry_after', None)
    if retry_after:
        delay = max(delay, float(retry_after) + random.uniform(0, 2))
    return int(min(delay, settings.EXTRACTION_RETRY_MAX_BACKOFF_SECONDS))


def _handle_recoverable(task, job, exc):
    max_retries = settings.EXTRACTION_MAX_RETRIES
    # Waiting for an exhausted router, or continuing a large document, is not a failed attempt: neither uses up
    # this budget.
    attempt = task.request.retries - _since_reset(job, 'waiting') - _continuations(job) + 1

    if attempt > max_retries:
        logger.error('extraction.task.retries_exhausted job_id=%s attempts=%d', job.id, attempt)
        _fail(job, f'Failed after {max_retries} retries: {exc}')
        return None

    from .models import ExtractionJob

    countdown = retry_countdown(attempt, exc)
    if not _set_status(job, ExtractionJob.Status.RETRYING, retry_count=attempt, error_message=str(exc),
                       next_retry_at=timezone.now() + timedelta(seconds=countdown)):
        return None  # stopped by the user -- don't schedule a retry
    logger.warning('extraction.task.retrying job_id=%s attempt=%d kind=%s countdown=%ds error=%s', job.id, attempt,
                   getattr(exc, 'kind', 'transient'), countdown, exc)
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


def _claim(job, worker=''):
    """Move the job to running if it's pending or retrying -- or running with a heartbeat older than
    EXTRACTION_STALE_SECONDS (its worker died; the message was redelivered). A RUNNING job whose worker is still
    sending heartbeats is never taken: one document is processed by one worker at a time. Returns False for that
    case and for a cancelled, completed or failed job -- a reprocess resets it to pending first, so a finished
    job reaching here is a duplicate message. One conditional UPDATE, so two workers can't both win."""
    from django.db.models import Q

    from .models import ExtractionJob

    now = timezone.now()
    stale = now - timedelta(seconds=settings.EXTRACTION_STALE_SECONDS)
    started_at = job.started_at or now
    updated = ExtractionJob.objects.filter(id=job.id).filter(
        Q(status__in=[ExtractionJob.Status.PENDING, ExtractionJob.Status.RETRYING])
        | Q(status=ExtractionJob.Status.RUNNING, heartbeat_at__lt=stale)
        | Q(status=ExtractionJob.Status.RUNNING, heartbeat_at__isnull=True, updated_at__lt=stale),
    ).update(status=ExtractionJob.Status.RUNNING, started_at=started_at, error_message='', heartbeat_at=now,
             worker=worker[:200], next_retry_at=None, updated_at=now)
    if not updated:
        job.refresh_from_db(fields=['status'])
        return False
    job.status = ExtractionJob.Status.RUNNING
    job.started_at = started_at
    job.error_message = ''
    job.heartbeat_at = now
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

    from django.db.models import Q

    rows = ExtractionJob.objects.filter(id=job.id).exclude(status=ExtractionJob.Status.CANCELLED)
    token = getattr(job, 'task_token', '')
    if token:
        # Only the job's current owner moves it on: a worker it was taken from (recovery) changes nothing.
        rows = rows.filter(Q(celery_task_id=token) | Q(celery_task_id=''))
    updated = rows.update(status=status, updated_at=timezone.now(), **fields)
    if not updated:
        job.status = ExtractionJob.Status.CANCELLED
        return False
    job.status = status
    for name, value in fields.items():
        setattr(job, name, value)
    return True


@shared_task(ignore_result=True)
def recover_extraction_jobs():
    """Periodic (celery beat) and after a worker starts: re-queue jobs whose message or worker was lost
    (services/recovery.py). Never touches completed, failed or stopped jobs."""
    from .services.recovery import recover

    recovered = recover()
    if recovered:
        logger.warning('extraction.recovery.done count=%d reasons=%s', len(recovered),
                       sorted({r['reason'] for r in recovered}))
    return len(recovered)


def two_phase():
    """OCR_QUEUE and EXTRACTION_QUEUE set to different queues: page reading (text + OCR, CPU-bound) and AI
    extraction (network-bound, quota-bound) run on separately sized worker services."""
    return bool(settings.OCR_QUEUE) and settings.OCR_QUEUE != (settings.EXTRACTION_QUEUE or 'celery')


@shared_task(bind=True, acks_late=True, ignore_result=True)
def read_document_pages(self, job_id):
    """Phase 1 of two (two_phase()): read the job's document page by page -- text layer, then OCR where needed --
    saving each page (DocumentPage), then hand the job to run_extraction_job on EXTRACTION_QUEUE, which reuses
    those pages instead of reading again. The job stays queued (status pending) while its pages are read; the
    monitor shows it as reading pages. A read error is left for the extraction task to report: it reads the
    failed pages once more and fails or finishes partial with the reason."""
    from .models import ExtractionJob
    from .services.pdf_reader import PDFPageReader
    from .services.pipeline import _page_progress

    job = ExtractionJob.objects.select_related('document').filter(id=job_id).first()
    if job is None or job.status != ExtractionJob.Status.PENDING:
        return None
    if job.celery_task_id and self.request.id and job.celery_task_id != self.request.id:
        logger.info('extraction.read_pages.skipped_stale job_id=%s task_id=%s', job.id, self.request.id)
        return None
    now = timezone.now()
    ExtractionJob.objects.filter(id=job.id).update(
        current_step=ExtractionJob.Step.READING_PAGES, heartbeat_at=now, worker=(self.request.hostname or '')[:200])
    reader = PDFPageReader()
    reader.on_progress = lambda **counts: _page_progress(job, **counts)
    try:
        reader.read_pages(job.document)
    except Exception as exc:  # reported by the extraction phase, which reads the failed pages again
        logger.warning('extraction.read_pages.failed job_id=%s error=%s', job.id, exc)
    # Hand over unless the user stopped it meanwhile (a conditional update: a Stop always wins).
    result = run_extraction_job.delay(str(job.id))
    handed = ExtractionJob.objects.filter(id=job.id, status=ExtractionJob.Status.PENDING).update(
        celery_task_id=result.id, dispatched_at=timezone.now(), heartbeat_at=None)
    logger.info('extraction.read_pages.done job_id=%s handed_over=%s', job.id, bool(handed))
    return None
