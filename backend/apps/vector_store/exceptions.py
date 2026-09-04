"""Error taxonomy for the vector-indexing layer.

Mirrors `apps.extraction.exceptions` deliberately: the Celery task in
`tasks.py` decides whether to retry purely from which of these it catches, the
same way `run_extraction_job` does. Keeping the two shapes identical means
anyone who has read one retry policy already understands the other.
"""


class VectorStoreError(Exception):
    """Base class for every failure in this app."""


class RecoverableVectorStoreError(VectorStoreError):
    """A transient failure worth retrying with backoff — a rate limit, a
    timeout, a connection error, or a 5xx from Pinecone or the embedding
    provider."""


class PermanentVectorStoreError(VectorStoreError):
    """A failure retrying cannot fix — a bad API key, a missing index, an
    unreadable document, or a malformed response. Fails the indexing run
    immediately instead of burning retries on it."""


class EmbeddingError(VectorStoreError):
    """Base for embedding-provider problems. Subclasses pick the retry
    behaviour; this exists so callers that don't care can catch one type."""


class RecoverableEmbeddingError(EmbeddingError, RecoverableVectorStoreError):
    """Rate limit / timeout / connection / 5xx from the embedding provider."""


class PermanentEmbeddingError(EmbeddingError, PermanentVectorStoreError):
    """4xx from the embedding provider, or a response that doesn't parse —
    wrong key, wrong model name, malformed input."""
