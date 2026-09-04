import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.documents.models import Document

from .exceptions import PermanentExtractionError, RecoverableExtractionError
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

    job.status = ExtractionJob.Status.RUNNING
    if job.started_at is None:
        job.started_at = timezone.now()
    job.error_message = ''
    job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])
    logger.info('extraction.task.running job_id=%s attempt=%d', job.id, self.request.retries + 1)

    try:
        ExtractionPipeline().run(job)
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

    job.status = ExtractionJob.Status.COMPLETED
    job.completed_at = timezone.now()
    job.save(update_fields=['status', 'completed_at', 'updated_at'])
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

    job.status = ExtractionJob.Status.RETRYING
    job.retry_count = attempt
    job.error_message = str(exc)
    job.save(update_fields=['status', 'retry_count', 'error_message', 'updated_at'])
    logger.warning('extraction.task.retrying job_id=%s attempt=%d error=%s', job.id, attempt, exc)

    countdown = settings.EXTRACTION_RETRY_BACKOFF_SECONDS * (2 ** task.request.retries)
    raise task.retry(exc=exc, countdown=countdown)


def _fail(job, message):
    from .models import ExtractionJob

    job.status = ExtractionJob.Status.FAILED
    job.error_message = message
    job.completed_at = timezone.now()
    job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])

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
