"""Everything that knows Pinecone exists.

No other module imports the Pinecone SDK. Callers deal in plain dicts and this
app's exception types, so replacing the vector database later means rewriting
this file and nothing else.

The SDK is imported lazily inside `_get_index()`. That is deliberate and load
bearing: `apps.vector_store` is in `INSTALLED_APPS`, so an eager import would
make the `pinecone` package a hard requirement for the whole Django project —
breaking `manage.py` for anyone who has not installed it, which contradicts
"the app must work exactly as before when Pinecone is not configured".
"""
import logging
import time

from django.conf import settings

from ..exceptions import PermanentVectorStoreError, RecoverableVectorStoreError

logger = logging.getLogger(__name__)

#: Default upsert batch size for raw vectors. Pinecone caps such a request at
#: 2 MB; at ~1536 float32 dims plus metadata a chunk is a few KB, so 100 stays
#: well inside that while keeping round trips low. Each store subclass may
#: narrow it — see PineconeIntegratedVectorStore.
UPSERT_BATCH_SIZE = 100

#: Metadata marking where a vector came from. Only college documents are
#: indexed today; benchmark vectors will carry a different value, and every
#: query written now already filters on this so the two can share an index
#: without either seeing the other.
SOURCE_TYPE_COLLEGE_DOCUMENT = 'college_document'


def build_vector_id(institution_id, document_id, chunk_index):
    """The deterministic ID scheme.

    `college_{institution}_document_{document}_chunk_{n}` — reprocessing a
    document produces byte-identical IDs, so an upsert overwrites rather than
    duplicating. That is what makes indexing idempotent; see
    `indexer.index_document` for how chunks that no longer exist get removed.
    """
    return f'college_{institution_id}_document_{document_id}_chunk_{chunk_index}'


def build_vector_metadata(*, document, chunk):
    """Metadata carried alongside a vector.

    Two jobs, and no more than these two:

    * **Isolation** — `college_id` (plus `sprint_id`) is what every query
      filters on, server-side. See `search.py`.
    * **Traceability** — document id/name, page number and the chunk's own
      text, so a retrieved chunk can be cited as "Faculty_Report.pdf, page 17"
      rather than surfacing as an anonymous vector.

    Nothing else from PostgreSQL is copied in. Fields that are not filtered or
    cited would only be a second copy that drifts.
    """
    return {
        'college_id': str(document.sprint.institution_id),
        'sprint_id': str(document.sprint_id),
        'document_id': str(document.id),
        'document_type': document.document_type or '',
        'document_name': document.original_filename or document.title or '',
        'page_number': chunk.get('page_number') or 0,
        'chunk_index': chunk['chunk_index'],
        'text': chunk['text'],
        'source_type': SOURCE_TYPE_COLLEGE_DOCUMENT,
    }


def is_configured():
    """Whether Pinecone could be reached. Checked before any work is queued,
    so an unconfigured deployment never enqueues a task that can only fail."""
    return bool(settings.PINECONE_API_KEY and settings.PINECONE_INDEX_NAME)


def _require_filter(metadata_filter):
    if not metadata_filter:
        raise PermanentVectorStoreError(
            'A metadata filter is required — an unfiltered query would cross institutions.'
        )


def _normalise_match(match):
    """One provider hit -> `{'id', 'score', 'metadata'}`.

    The two Pinecone APIs disagree on shape: a classic query returns
    `id/score/metadata`, an integrated `search` returns `_id/_score/fields`.
    Normalising here keeps that difference inside this module, so `search.py`
    formats one shape and the callers above it never learn there were two.
    """
    if isinstance(match, dict):
        get = match.get
    else:
        def get(key, default=None):
            return getattr(match, key, default)

    metadata = get('metadata') or get('fields') or {}
    score = get('score')
    if score is None:
        score = get('_score')
    identifier = get('id') or get('_id') or ''
    return {'id': identifier, 'score': score, 'metadata': dict(metadata)}


class PineconeVectorStore:
    """Thin wrapper over one Pinecone index that stores **raw vectors**.

    `index` is injectable so tests exercise every path here against a fake
    without touching the network — see `tests.py`.
    """

    #: This store needs embeddings supplied to it. `indexer` and `search` read
    #: this to decide whether to build an embedding service at all.
    handles_embedding = False

    #: Vectors per upsert call.
    UPSERT_BATCH_SIZE = UPSERT_BATCH_SIZE

    def __init__(self, *, api_key=None, index_name=None, namespace=None, index=None):
        self.api_key = api_key or settings.PINECONE_API_KEY
        self.index_name = index_name or settings.PINECONE_INDEX_NAME
        self.namespace = namespace if namespace is not None else settings.PINECONE_NAMESPACE
        self._index = index

    def _get_index(self):
        if self._index is not None:
            return self._index

        if not self.api_key or not self.index_name:
            raise PermanentVectorStoreError(
                'Pinecone is not configured. Set PINECONE_API_KEY and PINECONE_INDEX_NAME.'
            )
        try:
            from pinecone import Pinecone
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise PermanentVectorStoreError(
                'The `pinecone` package is not installed. Add it with '
                '`pip install -r requirements/base.txt`.'
            ) from exc

        try:
            self._index = Pinecone(api_key=self.api_key).Index(self.index_name)
        except Exception as exc:
            raise self._translate(exc, 'connecting to the index') from exc
        return self._index

    @staticmethod
    def _translate(exc, what):
        """Map an SDK exception onto this app's retry taxonomy.

        **Status code first.** An earlier version matched keywords against
        `str(exc)`, which for this SDK includes the full HTTP response header
        dump — so a permanent `400 Bad Request` matched on the word
        "Connection" in `Connection: keep-alive` and was retried three times
        for nothing. The numeric status is the only reliable signal, and text
        matching is now the fallback for transport errors that have none.

        The SDK's exception types are still not imported, so this module keeps
        its lazy-import property. Neither the message nor the body carries the
        API key — that travels in a request header.
        """
        name = type(exc).__name__
        status = getattr(exc, 'status', None) or getattr(exc, 'status_code', None)
        # `body` is the provider's own JSON error, far more readable than the
        # header dump `str(exc)` produces.
        detail = (getattr(exc, 'body', None) or str(exc)).strip()

        if isinstance(status, int):
            if status == 429 or status >= 500:
                logger.warning(
                    'vector_store.pinecone.transient op=%s status=%s', what, status,
                )
                return RecoverableVectorStoreError(
                    f'Pinecone failed while {what} (HTTP {status}): {detail}'
                )
            logger.error('vector_store.pinecone.permanent op=%s status=%s', what, status)
            return PermanentVectorStoreError(
                f'Pinecone rejected the request while {what} (HTTP {status}): {detail}'
            )

        # No status: a transport-level failure that never reached Pinecone.
        transient_names = {
            'PineconeProtocolError', 'ConnectionError', 'Timeout', 'ReadTimeout',
            'ConnectTimeout', 'MaxRetryError', 'NewConnectionError',
        }
        lowered = detail.lower()
        transient_text = any(
            marker in lowered
            for marker in ('rate limit', 'too many requests', 'timed out',
                           'temporarily unavailable', 'connection refused',
                           'connection reset', 'failed to establish')
        )
        if name in transient_names or transient_text:
            logger.warning('vector_store.pinecone.transient op=%s error=%s', what, name)
            return RecoverableVectorStoreError(f'Pinecone failed while {what}: {detail}')

        logger.error('vector_store.pinecone.permanent op=%s error=%s', what, name)
        return PermanentVectorStoreError(f'Pinecone rejected the request while {what}: {detail}')

    # ---------------------------------------------------------------- write

    def upsert(self, vectors):
        """Upsert `[{'id', 'values', 'metadata'}]`, batched.

        Upsert, never insert: with deterministic IDs a re-run overwrites the
        previous vector for that chunk in place.
        """
        if not vectors:
            return 0
        index = self._get_index()
        started = time.monotonic()
        written = 0
        for start in range(0, len(vectors), self.UPSERT_BATCH_SIZE):
            batch = vectors[start:start + self.UPSERT_BATCH_SIZE]
            try:
                index.upsert(vectors=batch, namespace=self.namespace or None)
            except Exception as exc:
                raise self._translate(exc, 'upserting vectors') from exc
            written += len(batch)
        logger.info(
            'vector_store.pinecone.upsert index=%s count=%d duration_ms=%.1f',
            self.index_name, written, (time.monotonic() - started) * 1000,
        )
        return written

    def delete_ids(self, ids):
        """Delete specific vector IDs. Used to drop chunks a shorter revision
        of a document no longer has — see `indexer.index_document`."""
        if not ids:
            return 0
        index = self._get_index()
        try:
            index.delete(ids=list(ids), namespace=self.namespace or None)
        except Exception as exc:
            raise self._translate(exc, 'deleting vectors') from exc
        logger.info('vector_store.pinecone.delete index=%s count=%d', self.index_name, len(ids))
        return len(ids)

    # ----------------------------------------------------------------- read

    def query(self, *, query_text, top_k, metadata_filter, embedder=None):
        """Similarity search, always with a server-side metadata filter.

        Takes the query *text* rather than a vector: turning text into a search
        is the one thing that genuinely differs between a manual and an
        integrated index, so each store owns its own half of it. Here that
        means embedding locally first.

        `metadata_filter` is a required keyword with no default on purpose:
        every query in this system is scoped to one institution, and a
        parameter that could be forgotten is exactly how that guarantee would
        eventually be lost.
        """
        _require_filter(metadata_filter)
        if embedder is None:
            raise PermanentVectorStoreError(
                'This index stores raw vectors, so an embedding service is required to query it.'
            )
        vector = embedder.generate_embedding(query_text)

        index = self._get_index()
        started = time.monotonic()
        try:
            response = index.query(
                vector=vector,
                top_k=top_k,
                filter=metadata_filter,
                include_metadata=True,
                namespace=self.namespace or None,
            )
        except Exception as exc:
            raise self._translate(exc, 'querying the index') from exc

        raw = response.get('matches', []) if isinstance(response, dict) else getattr(
            response, 'matches', [],
        )
        matches = [_normalise_match(m) for m in raw]
        logger.info(
            'vector_store.pinecone.query index=%s top_k=%d matches=%d duration_ms=%.1f',
            self.index_name, top_k, len(matches), (time.monotonic() - started) * 1000,
        )
        return matches


class PineconeIntegratedVectorStore(PineconeVectorStore):
    """A Pinecone index that **embeds server-side**.

    Created with an `embed` config (e.g. `llama-text-embed-v2`), such an index
    is written with `upsert_records` — records carrying *text*, not vectors —
    and read with `search`, which embeds the query itself. Passing raw vectors
    to one is rejected by Pinecone, which is why this is a separate store
    rather than a different embedding provider behind the same calls.

    Everything else is inherited: the same deterministic IDs, the same
    metadata, the same delete-by-id pruning, the same error taxonomy. The
    institution filter is applied server-side exactly as before.
    """

    #: Pinecone owns the embedding, so no embedding key or model is needed and
    #: `indexer`/`search` skip building an embedding service entirely.
    handles_embedding = True

    #: `upsert_records` is capped at 96 records per call, NOT the 2 MB size
    #: limit that governs raw-vector upserts — Pinecone has to embed each
    #: record server-side, so the ceiling is a count. Exceeding it returns
    #: `400 Invalid input: Batch size exceeds 96`. Found against a live index
    #: with a real PDF that chunked past 96.
    UPSERT_BATCH_SIZE = 96

    #: `upsert_records` takes a namespace positionally. The empty string is
    #: the default namespace on every API version; the literal "__default__"
    #: is rejected with a 400 before version 2025-04, which is what this SDK
    #: negotiates. Verified against a live index.
    DEFAULT_NAMESPACE = ''

    #: Which metadata fields to ask `search` to return. Everything the
    #: traceability guarantee needs — omitting `text` would give back a hit
    #: nobody could cite.
    RETURN_FIELDS = [
        'text', 'college_id', 'sprint_id', 'document_id', 'document_type',
        'document_name', 'page_number', 'chunk_index', 'source_type',
    ]

    def _namespace(self):
        return self.namespace or self.DEFAULT_NAMESPACE

    def upsert(self, vectors):
        """Accepts the same payload the manual store does and rewrites it.

        `indexer` builds one shape; this flattens it into a record — `_id` plus
        the metadata fields, with the chunk text under the key the index's
        `field_map` names. `values` is dropped: there are no local embeddings
        to send.
        """
        if not vectors:
            return 0
        index = self._get_index()
        namespace = self._namespace()
        started = time.monotonic()
        written = 0

        for start in range(0, len(vectors), self.UPSERT_BATCH_SIZE):
            records = [
                {'_id': item['id'], **item['metadata']}
                for item in vectors[start:start + self.UPSERT_BATCH_SIZE]
            ]
            try:
                index.upsert_records(namespace, records)
            except Exception as exc:
                raise self._translate(exc, 'upserting records') from exc
            written += len(records)

        logger.info(
            'vector_store.pinecone.upsert_records index=%s count=%d duration_ms=%.1f',
            self.index_name, written, (time.monotonic() - started) * 1000,
        )
        return written

    def delete_ids(self, ids):
        """Deleting by id is identical on an integrated index."""
        if not ids:
            return 0
        index = self._get_index()
        try:
            index.delete(ids=list(ids), namespace=self._namespace())
        except Exception as exc:
            raise self._translate(exc, 'deleting records') from exc
        logger.info('vector_store.pinecone.delete index=%s count=%d', self.index_name, len(ids))
        return len(ids)

    def query(self, *, query_text, top_k, metadata_filter, embedder=None):
        """Search by text. Pinecone embeds the query with the index's own
        model, which is what guarantees query/stored compatibility here — the
        mismatch the manual path has to guard against cannot arise.

        `embedder` is accepted and ignored so both stores share one signature.
        """
        _require_filter(metadata_filter)
        index = self._get_index()
        started = time.monotonic()
        try:
            response = index.search(
                namespace=self._namespace(),
                query={
                    'inputs': {'text': query_text},
                    'top_k': top_k,
                    'filter': metadata_filter,
                },
                fields=self.RETURN_FIELDS,
            )
        except Exception as exc:
            raise self._translate(exc, 'searching the index') from exc

        result = response.get('result') if isinstance(response, dict) else getattr(
            response, 'result', None,
        )
        hits = []
        if result is not None:
            hits = (result.get('hits') if isinstance(result, dict) else getattr(result, 'hits', [])) or []

        matches = [_normalise_match(hit) for hit in hits]
        logger.info(
            'vector_store.pinecone.search index=%s top_k=%d matches=%d duration_ms=%.1f',
            self.index_name, top_k, len(matches), (time.monotonic() - started) * 1000,
        )
        return matches


#: Cached per index name. `describe_index` is a network call, so it is made
#: once per process rather than on every document. Cleared by tests.
_MODE_CACHE = {}


def reset_mode_cache():
    _MODE_CACHE.clear()


def detect_embedding_mode(index_name=None, api_key=None):
    """'integrated' or 'manual' for the configured index.

    `PINECONE_EMBEDDING_MODE` short-circuits this; 'auto' asks the index
    whether it carries an `embed` config. A failed lookup falls back to
    'manual' — the conservative answer, since sending raw vectors to an
    integrated index fails loudly, while the reverse would silently store
    nothing useful.
    """
    configured = (settings.PINECONE_EMBEDDING_MODE or 'auto').strip().lower()
    if configured in ('integrated', 'manual'):
        return configured

    index_name = index_name or settings.PINECONE_INDEX_NAME
    api_key = api_key or settings.PINECONE_API_KEY
    if index_name in _MODE_CACHE:
        return _MODE_CACHE[index_name]

    mode = 'manual'
    try:
        from pinecone import Pinecone

        description = Pinecone(api_key=api_key).describe_index(index_name)
        embed = (
            description.get('embed') if isinstance(description, dict)
            else getattr(description, 'embed', None)
        )
        if embed:
            mode = 'integrated'
    except Exception as exc:
        logger.warning(
            'vector_store.pinecone.mode_detect_failed index=%s error=%s falling_back=manual',
            index_name, type(exc).__name__,
        )

    _MODE_CACHE[index_name] = mode
    logger.info('vector_store.pinecone.mode index=%s mode=%s', index_name, mode)
    return mode


def get_vector_store(**kwargs):
    """The store for the configured index — the only constructor callers use.

    Which class comes back depends on how the index was created, so switching
    between a self-embedding index and a raw-vector one is configuration, not
    a code change.
    """
    if detect_embedding_mode() == 'integrated':
        return PineconeIntegratedVectorStore(**kwargs)
    return PineconeVectorStore(**kwargs)
