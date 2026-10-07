import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.documents.models import Document

from .exceptions import ExtractionCancelled, PermanentExtractionError, RecoverableExtractionError
from .services import ExtractionPipeline

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

    # Stopped while still queued: never start it. (A Celery revoke alone isn't
    # enough -- a worker restart forgets revoked task ids.)
    if not _set_status(
        job, ExtractionJob.Status.RUNNING, started_at=job.started_at or timezone.now(), error_message='',
    ):
        logger.info('extraction.task.skipped_cancelled job_id=%s', job.id)
        return None
    logger.info('extraction.task.running job_id=%s attempt=%d', job.id, self.request.retries + 1)

    try:
        ExtractionPipeline().run(job)
    except ExtractionCancelled:
        logger.info('extraction.task.stopped job_id=%s step=%s', job.id, job.current_step)
        _advance_sprint_if_all_jobs_done(job.sprint)
        return None
    except PermanentExtractionError as exc:
        logger.error('extraction.task.failed_permanent job_id=%s error=%s', job.id, exc)
        _fail(job, str(exc))
        return None
    except RecoverableExtractionError as exc:
        return _handle_recoverable(self, job, exc)
    except Exception as exc:
        logger.exception('extraction.task.failed_unexpected job_id=%s', job.id)
        _fail(job, f'Unexpected error: {exc}')
        return None

    if not _set_status(job, ExtractionJob.Status.COMPLETED, completed_at=timezone.now()):
        # Stopped in the last instant, after its facts were saved: keep the
        # facts, and keep the "cancelled" status the user chose.
        logger.info('extraction.task.stopped_after_finish job_id=%s', job.id)
        _advance_sprint_if_all_jobs_done(job.sprint)
        return None
    logger.info('extraction.task.completed job_id=%s', job.id)

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


def _handle_recoverable(task, job, exc):
    max_retries = settings.EXTRACTION_MAX_RETRIES
    attempt = task.request.retries + 1

    if attempt > max_retries:
        logger.error('extraction.task.retries_exhausted job_id=%s attempts=%d', job.id, attempt)
        _fail(job, f'Failed after {max_retries} retries: {exc}')
        return None

    from .models import ExtractionJob

    if not _set_status(job, ExtractionJob.Status.RETRYING, retry_count=attempt, error_message=str(exc)):
        return None  # stopped by the user -- don't schedule a retry
    logger.warning('extraction.task.retrying job_id=%s attempt=%d error=%s', job.id, attempt, exc)

    countdown = settings.EXTRACTION_RETRY_BACKOFF_SECONDS * (2 ** task.request.retries)
    raise task.retry(exc=exc, countdown=countdown)


def _fail(job, message):
    from .models import ExtractionJob

    if not _set_status(job, ExtractionJob.Status.FAILED, error_message=message, completed_at=timezone.now()):
        return  # stopped by the user; a stop is not a failure

    if job.document.status != Document.Status.PROCESSED:
        job.document.status = Document.Status.FAILED
        job.document.save(update_fields=['status', 'updated_at'])


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
