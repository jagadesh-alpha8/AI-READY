"""Celery tasks for vector indexing.

A thin retry wrapper around `services.indexer.index_document`, matching the
policy `apps.extraction.tasks` already uses: recoverable failures retry with
exponential backoff, permanent and unrecognised ones fail immediately rather
than hiding a real bug behind a retry loop.

Embedding and upserting are async for the same reason extraction is — a
document can be dozens of embedding calls, and no HTTP request should wait for
that.
"""
import logging

from celery import shared_task
from django.conf import settings

from .exceptions import PermanentVectorStoreError, RecoverableVectorStoreError
from .models import VectorDocumentIndex

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=settings.VECTOR_INDEX_MAX_RETRIES, acks_late=True)
def index_document_vectors(self, document_id, force=False):
    """Index one document into Pinecone."""
    from apps.documents.models import Document

    from .services import indexer

    if not indexer.is_enabled():
        # Reached only if configuration was removed between queueing and
        # running. Not an error — the deployment has simply switched the
        # feature off.
        logger.info('vector_store.task.disabled document_id=%s', document_id)
        return None

    try:
        document = Document.objects.select_related('sprint').get(id=document_id)
    except Document.DoesNotExist:
        logger.error('vector_store.task.missing_document document_id=%s', document_id)
        return None

    logger.info(
        'vector_store.task.running document_id=%s attempt=%d', document_id, self.request.retries + 1,
    )

    try:
        index_row = indexer.index_document(document, force=force)
    except RecoverableVectorStoreError as exc:
        return _handle_recoverable(self, document_id, exc)
    except PermanentVectorStoreError as exc:
        # index_document has already written the reason onto the row.
        logger.error('vector_store.task.failed_permanent document_id=%s error=%s', document_id, exc)
        return None
    except Exception:
        logger.exception('vector_store.task.failed_unexpected document_id=%s', document_id)
        return None

    logger.info(
        'vector_store.task.completed document_id=%s vectors=%d', document_id, index_row.vector_count,
    )
    return str(index_row.id)


def _handle_recoverable(task, document_id, exc):
    max_retries = settings.VECTOR_INDEX_MAX_RETRIES
    attempt = task.request.retries + 1

    if attempt > max_retries:
        logger.error(
            'vector_store.task.retries_exhausted document_id=%s attempts=%d', document_id, attempt,
        )
        VectorDocumentIndex.objects.filter(document_id=document_id).update(
            status=VectorDocumentIndex.Status.FAILED,
            error_message=f'Failed after {max_retries} retries: {exc}',
        )
        return None

    VectorDocumentIndex.objects.filter(document_id=document_id).update(
        status=VectorDocumentIndex.Status.PENDING,
        error_message=f'Retrying after: {exc}',
    )
    countdown = settings.VECTOR_INDEX_RETRY_BACKOFF_SECONDS * (2 ** task.request.retries)
    logger.warning(
        'vector_store.task.retrying document_id=%s attempt=%d countdown=%ds error=%s',
        document_id, attempt, countdown, exc,
    )
    raise task.retry(exc=exc, countdown=countdown)


@shared_task
def index_sprint_vectors(sprint_id, force=False):
    """Fan out indexing across every processed document in a sprint.

    One task per document rather than one long task for the sprint: a single
    bad document then costs one document, and each gets its own retry budget —
    the same reasoning behind per-row transactions elsewhere in this codebase.
    """
    from apps.documents.models import Document

    from .services import indexer

    if not indexer.is_enabled():
        logger.info('vector_store.task.disabled sprint_id=%s', sprint_id)
        return 0

    documents = Document.objects.filter(
        sprint_id=sprint_id, status=Document.Status.PROCESSED,
    ).select_related('sprint')

    queued = 0
    for document in documents:
        if indexer.queue_document(document, force=force) is not None:
            queued += 1
    logger.info('vector_store.task.sprint_queued sprint_id=%s queued=%d', sprint_id, queued)
    return queued
