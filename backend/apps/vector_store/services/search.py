"""College evidence retrieval.

The read half of this app, and the piece the future benchmarking framework
will call: a benchmark criterion becomes a semantic query, this returns the
college's own evidence for it, and an LLM reasons over that evidence. Nothing
here knows what a benchmark is, and nothing here scores anything.

Two guarantees the rest of the system depends on:

* **Isolation.** The institution filter is applied by Pinecone, server-side,
  and is built here rather than accepted from the caller — so no call site can
  omit it or widen it.
* **Traceability.** Every result carries the document, page and chunk it came
  from. There is no code path that returns an anonymous vector, because the
  LLM downstream must be able to say "according to Faculty_Report.pdf,
  page 17" instead of asserting something unsourced.
"""
import logging

from django.conf import settings

from ..exceptions import PermanentVectorStoreError
from . import embeddings as embedding_service
from . import pinecone_client
from .pinecone_client import SOURCE_TYPE_COLLEGE_DOCUMENT, get_vector_store

logger = logging.getLogger(__name__)


def build_filter(*, institution_id, sprint_id=None, document_type=None, document_ids=None):
    """The Pinecone metadata filter for a college-evidence query.

    `college_id` is unconditional. `source_type` is pinned to college
    documents so that when benchmark vectors are added to the same index later
    they cannot appear in these results without anyone revisiting this call.
    """
    if not institution_id:
        raise PermanentVectorStoreError('An institution id is required for evidence search.')

    metadata_filter = {
        'college_id': {'$eq': str(institution_id)},
        'source_type': {'$eq': SOURCE_TYPE_COLLEGE_DOCUMENT},
    }
    if sprint_id:
        metadata_filter['sprint_id'] = {'$eq': str(sprint_id)}
    if document_type:
        metadata_filter['document_type'] = {'$eq': str(document_type)}
    if document_ids:
        metadata_filter['document_id'] = {'$in': [str(d) for d in document_ids]}
    return metadata_filter


def _as_int(value):
    """Pinecone returns numeric metadata as floats; page and chunk indexes are
    counts, so they come back as ints or None."""
    if value is None or value == '':
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _format(match):
    """One Pinecone match → one citable result."""
    metadata = (match.get('metadata') if isinstance(match, dict) else match.metadata) or {}
    score = match.get('score') if isinstance(match, dict) else match.score
    # Pinecone stores metadata numbers as doubles, so integers come back as
    # 17.0 / 4.0. Coerced here so the API returns `"page_number": 17`, not
    # `17.0` — a page number is not a real quantity.
    page = _as_int(metadata.get('page_number'))
    return {
        'score': round(float(score), 4) if score is not None else None,
        'text': metadata.get('text', ''),
        'document_id': metadata.get('document_id', ''),
        'document_name': metadata.get('document_name', ''),
        'document_type': metadata.get('document_type', ''),
        'page_number': page or None,
        'chunk_index': _as_int(metadata.get('chunk_index')),
        'sprint_id': metadata.get('sprint_id', ''),
        'institution_id': metadata.get('college_id', ''),
    }


def search_college_evidence(
    *,
    institution_id,
    query,
    sprint_id=None,
    document_type=None,
    document_ids=None,
    top_k=None,
    store=None,
    embedder=None,
):
    """Return the college's most relevant document chunks for `query`.

    Args:
        institution_id: **required** — the isolation boundary.
        query: natural-language text, e.g. "AI certified faculty and faculty
            AI training".
        sprint_id / document_type / document_ids: optional narrowing, all
            applied as server-side metadata filters.
        top_k: defaults to `VECTOR_SEARCH_DEFAULT_TOP_K`, capped at
            `VECTOR_SEARCH_MAX_TOP_K` so a caller cannot ask for an unbounded
            result set.
        store / embedder: injected in tests.

    Returns:
        A list of dicts sorted by descending similarity, each carrying its
        score and full provenance.

    Raises:
        `VectorStoreError` subclasses — the caller decides what a failure means
        for its own response.
    """
    if not query or not query.strip():
        raise PermanentVectorStoreError('A non-empty query is required.')

    requested = top_k or settings.VECTOR_SEARCH_DEFAULT_TOP_K
    resolved_top_k = max(1, min(int(requested), settings.VECTOR_SEARCH_MAX_TOP_K))

    metadata_filter = build_filter(
        institution_id=institution_id,
        sprint_id=sprint_id,
        document_type=document_type,
        document_ids=document_ids,
    )

    store = store or get_vector_store()
    # An integrated index embeds the query itself with the same model it used
    # for the stored vectors, so compatibility is guaranteed there. For a
    # raw-vector index we must supply the embedding, and it has to come from
    # the model recorded on those vectors — see embeddings.py.
    if not store.handles_embedding:
        embedder = embedder or embedding_service.get_embedding_service()

    matches = store.query(
        query_text=query.strip(),
        top_k=resolved_top_k,
        metadata_filter=metadata_filter,
        embedder=embedder,
    )
    results = [_format(m) for m in matches]

    logger.info(
        'vector_store.search institution_id=%s sprint_id=%s top_k=%d results=%d',
        institution_id, sprint_id or '-', resolved_top_k, len(results),
    )
    return results


def is_enabled():
    """Whether search can run — same condition as indexing."""
    from .indexer import is_enabled as indexing_enabled

    return indexing_enabled()
