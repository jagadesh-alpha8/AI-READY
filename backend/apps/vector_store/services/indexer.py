"""Orchestrates one document: read → clean → chunk → embed → upsert.

The only module that touches both Django models and the vector services, and
it stays free of Celery so the whole pipeline can be run and tested
synchronously. `tasks.py` is the thin retry wrapper around `index_document`.
"""
import hashlib
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.extraction.exceptions import ExtractionError
from apps.extraction.services.pdf_reader import PDFPageReader

from ..exceptions import PermanentVectorStoreError, VectorStoreError
from ..models import VectorDocumentIndex
from . import embeddings as embedding_service
from . import pinecone_client
from .chunking import chunk_pages

logger = logging.getLogger(__name__)


def is_enabled():
    """Whether indexing can run at all.

    Pinecone is always required. An embedding key is required only for a
    raw-vector index: an integrated index embeds server-side, so demanding a
    second vendor's key there would disable a perfectly working setup.

    Deliberately does no network I/O — it runs on every document upload.
    Under `auto` it assumes the index can embed and lets the real check happen
    at index time, where a failure is recorded on the row and visible.

    Callers check this *before* queueing, so a deployment that never configures
    Pinecone behaves exactly as it did before this app existed: no tasks, no
    rows, no errors.
    """
    if not pinecone_client.is_configured():
        return False
    if (settings.PINECONE_EMBEDDING_MODE or 'auto').strip().lower() == 'manual':
        return embedding_service.is_configured()
    return True


def content_hash_for(chunks):
    """SHA-256 over the chunk texts.

    Hashes the extracted *text*, not the file: text is what gets embedded, so
    two uploads of the same content differing only in PDF metadata should not
    trigger a re-embed, and a file whose text extraction improved should.
    """
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk['text'].encode('utf-8'))
        digest.update(b'\x00')
    return digest.hexdigest()


def _read_pages(document):
    """Extracted text for the document, via the pipeline's own reader.

    Re-reads the file rather than receiving pages from the extraction job.
    Page text for a large PDF is megabytes; passing it through a Celery
    message would be far more expensive than parsing again, and reusing
    `PDFPageReader` keeps one implementation of "how this project reads a
    document".
    """
    try:
        result = PDFPageReader().read_pages(document)
    except ExtractionError as exc:
        # The reader's taxonomy mirrors ours 1:1, but callers here catch
        # VectorStoreError, so translate rather than leaking a foreign type.
        raise _translate_reader_error(exc) from exc
    if not result.get('format_supported', True):
        raise PermanentVectorStoreError(
            result.get('format_note') or 'This document format cannot be read for indexing.'
        )
    return result.get('pages') or []


def _translate_reader_error(exc):
    from apps.extraction.exceptions import RecoverableExtractionError

    from ..exceptions import RecoverableVectorStoreError

    if isinstance(exc, RecoverableExtractionError):
        return RecoverableVectorStoreError(str(exc))
    return PermanentVectorStoreError(str(exc))


def _record(index_row, **fields):
    for key, value in fields.items():
        setattr(index_row, key, value)
    index_row.save(update_fields=[*fields.keys(), 'updated_at'])


def get_or_create_index_row(document):
    """The tracking row for a document, created PENDING on first sight."""
    row, _ = VectorDocumentIndex.objects.get_or_create(
        document=document,
        defaults={
            'institution_id': document.sprint.institution_id,
            'sprint_id': document.sprint_id,
        },
    )
    return row


def index_document(document, *, force=False, store=None, embedder=None):
    """Index one document, idempotently.

    Args:
        force: re-embed even when the content hash and embedding model are
            unchanged. Without it an unchanged document is a no-op, which is
            what makes "re-run indexing for the sprint" cheap to press.
        store / embedder: injected in tests; production builds its own.

    Returns:
        The `VectorDocumentIndex` row, updated in place.

    Raises:
        VectorStoreError subclasses. The caller (`tasks.index_document_vectors`)
        decides retry from the type; this function always leaves the row
        describing what happened first.
    """
    index_row = get_or_create_index_row(document)

    # Snapshot the previous run BEFORE marking this one in progress. Reading
    # `index_row.status` after the write below would always see PROCESSING, so
    # the unchanged-content short-circuit further down could never fire and
    # every re-index would re-embed.
    previous = {
        'status': index_row.status,
        'content_hash': index_row.content_hash,
        'embedding_model': index_row.embedding_model,
        'vector_count': index_row.vector_count,
    }
    _record(index_row, status=VectorDocumentIndex.Status.PROCESSING, error_message='')

    try:
        pages = _read_pages(document)
        chunks = chunk_pages(pages)

        if not chunks:
            # An honest terminal state, not a failure: a scanned PDF with no
            # OCR, or a genuinely empty file, has nothing to embed. Recorded as
            # indexed-with-zero so it is not retried forever, and any stale
            # vectors from a previous revision are removed below.
            store = store or pinecone_client.get_vector_store()
            _delete_stale(store, document, previous['vector_count'], 0)
            _record(
                index_row,
                status=VectorDocumentIndex.Status.INDEXED,
                vector_count=0,
                content_hash=content_hash_for([]),
                indexed_at=timezone.now(),
                error_message='No extractable text to index.',
            )
            logger.info('vector_store.index.empty document_id=%s', document.id)
            return index_row

        store = store or pinecone_client.get_vector_store()

        # An integrated index embeds server-side, so no embedding service is
        # built and no key is needed. The model recorded on the row is the
        # index's own, which is still what a later query is compared against.
        if store.handles_embedding:
            model_name = settings.EMBEDDING_MODEL or 'pinecone-integrated'
        else:
            embedder = embedder or embedding_service.get_embedding_service()
            model_name = embedder.model

        new_hash = content_hash_for(chunks)
        unchanged = (
            not force
            and previous['status'] == VectorDocumentIndex.Status.INDEXED
            and previous['content_hash'] == new_hash
            and previous['embedding_model'] == model_name
        )
        if unchanged:
            _record(index_row, status=VectorDocumentIndex.Status.INDEXED, indexed_at=timezone.now())
            logger.info('vector_store.index.unchanged document_id=%s', document.id)
            return index_row

        # `values` is absent for an integrated index; that store drops it and
        # sends the chunk text instead. One payload shape serves both.
        vector_values = (
            [None] * len(chunks) if store.handles_embedding
            else embedder.generate_embeddings([c['text'] for c in chunks])
        )
        payload = [
            {
                'id': pinecone_client.build_vector_id(
                    document.sprint.institution_id, document.id, chunk['chunk_index'],
                ),
                'values': values,
                'metadata': pinecone_client.build_vector_metadata(document=document, chunk=chunk),
            }
            for chunk, values in zip(chunks, vector_values)
        ]
        store.upsert(payload)

        # Order matters: upsert first, then prune. If the prune fails the index
        # is merely stale-with-extra-chunks, which search tolerates; pruning
        # first would leave a window where real evidence is missing.
        _delete_stale(store, document, previous['vector_count'], len(chunks))

        _record(
            index_row,
            status=VectorDocumentIndex.Status.INDEXED,
            vector_count=len(chunks),
            embedding_model=model_name,
            content_hash=new_hash,
            indexed_at=timezone.now(),
            error_message='',
        )
        logger.info(
            'vector_store.index.complete document_id=%s chunks=%d model=%s',
            document.id, len(chunks), model_name,
        )
        return index_row

    except VectorStoreError as exc:
        _record(index_row, status=VectorDocumentIndex.Status.FAILED, error_message=str(exc))
        raise
    except Exception as exc:
        _record(
            index_row,
            status=VectorDocumentIndex.Status.FAILED,
            error_message=f'Unexpected error: {exc}',
        )
        raise


def _delete_stale(store, document, previous_count, new_count):
    """Remove vectors a shorter revision of the document no longer has.

    Chunk indexes are contiguous from 0, so anything from `new_count` to
    `previous_count - 1` is obsolete and its ID is computable without asking
    Pinecone what exists. That keeps cleanup to one call and works on every
    index type, including serverless indexes where delete-by-metadata-filter
    is unavailable.

    The trade-off: this trusts `vector_count`. If that row were lost, orphans
    would survive — they stay correctly scoped by metadata, so they can only
    ever be over-retrieval of this same document, never a cross-institution
    leak.
    """
    if previous_count <= new_count:
        return 0
    stale = [
        pinecone_client.build_vector_id(document.sprint.institution_id, document.id, i)
        for i in range(new_count, previous_count)
    ]
    store.delete_ids(stale)
    logger.info(
        'vector_store.index.pruned document_id=%s removed=%d', document.id, len(stale),
    )
    return len(stale)


def queue_document(document, *, force=False):
    """Queue one document for indexing, if indexing is switched on at all.

    Returns the tracking row, or None when the feature is unconfigured. Every
    failure to reach the broker is swallowed into the row rather than raised:
    indexing is an addition to the document workflow and must never be able to
    break it.
    """
    if not is_enabled():
        logger.debug('vector_store.queue.disabled document_id=%s', document.id)
        return None

    from ..tasks import index_document_vectors

    index_row = get_or_create_index_row(document)
    _record(index_row, status=VectorDocumentIndex.Status.PENDING, error_message='')

    def _dispatch():
        try:
            result = index_document_vectors.delay(str(document.id), force)
            VectorDocumentIndex.objects.filter(pk=index_row.pk).update(
                celery_task_id=getattr(result, 'id', '') or '',
            )
        except Exception as exc:
            logger.error(
                'vector_store.queue.broker_unreachable document_id=%s error=%s', document.id, exc,
            )
            VectorDocumentIndex.objects.filter(pk=index_row.pk).update(
                status=VectorDocumentIndex.Status.FAILED,
                error_message=f'Could not reach the Celery broker: {exc}',
            )

    # Dispatch after commit so the worker cannot start before the PENDING row
    # is visible to it — the classic read-your-own-write race with a fast queue.
    transaction.on_commit(_dispatch)
    return index_row
