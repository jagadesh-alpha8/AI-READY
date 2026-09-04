"""Provider-agnostic embedding service.

Same shape as `apps.extraction.services.ai_service`: every call site goes
through `get_embedding_service()` rather than constructing a provider client,
so swapping providers is configuration, never a code change.

**Why this is separate from the extraction AI service.** That factory picks
between OpenAI and Anthropic by key format, because both can do the
structured-extraction work. Embeddings are not symmetrical: Anthropic
publishes no embedding endpoint, so a deployment running Claude for extraction
still needs an OpenAI-compatible key for this. `EMBEDDING_API_KEY` exists for
exactly that case and falls back to the shared keys when they happen to work.

**The compatibility rule that matters:** a query embedding and the stored
vectors must come from the same model. Changing `EMBEDDING_MODEL` invalidates
every vector already in the index. `VectorDocumentIndex.embedding_model`
records which model produced each document's vectors so a mismatch is
detectable rather than silently returning nonsense — see `indexer.py`.
"""
import logging
import time
from abc import ABC, abstractmethod

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ..exceptions import PermanentEmbeddingError, RecoverableEmbeddingError

logger = logging.getLogger(__name__)

#: Output dimensions per known model, so the index can be created with the
#: right size without the operator having to look it up.
KNOWN_MODEL_DIMENSIONS = {
    'text-embedding-3-small': 1536,
    'text-embedding-3-large': 3072,
    'text-embedding-ada-002': 1536,
}


class EmbeddingService(ABC):
    """The whole contract. Anything implementing these two methods and raising
    this app's exception types can be dropped in without touching a caller."""

    #: Identifier stored alongside the vectors it produced.
    model = ''

    @abstractmethod
    def generate_embedding(self, text):
        """Return a `list[float]` for one string."""

    @abstractmethod
    def generate_embeddings(self, texts):
        """Return a `list[list[float]]`, one per input, in the same order.

        Separate from `generate_embedding` because indexing a document means
        embedding dozens of chunks, and one batched request is both faster and
        far cheaper than N round trips.
        """


class OpenAIEmbeddingService(EmbeddingService):
    """OpenAI (and any OpenAI-compatible endpoint, via `EMBEDDING_BASE_URL`).

    The SDK is imported lazily so this module — and therefore the whole app —
    stays importable in an environment that never uses embeddings.
    """

    #: Requests are chunked to this many inputs. The API accepts more, but a
    #: smaller batch keeps a single failure from costing the whole document
    #: and stays clear of per-request token ceilings on large chunks.
    BATCH_SIZE = 64
    TIMEOUT_SECONDS = 60

    def __init__(self, *, api_key=None, model=None, base_url=None, client=None):
        self.api_key = api_key or _resolve_api_key()
        self.model = model or settings.EMBEDDING_MODEL
        self.base_url = base_url or settings.EMBEDDING_BASE_URL or None

        if not self.api_key:
            raise ImproperlyConfigured(
                'No embedding API key is configured. Set EMBEDDING_API_KEY (or OPENAI_API_KEY) '
                'in backend/.env before indexing or searching vectors.'
            )
        if not self.model:
            raise ImproperlyConfigured('EMBEDDING_MODEL is not set.')

        # `client` is injected by tests; normal callers get a real one.
        self._client = client

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            kwargs = {'api_key': self.api_key}
            if self.base_url:
                kwargs['base_url'] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def generate_embedding(self, text):
        return self.generate_embeddings([text])[0]

    def generate_embeddings(self, texts):
        texts = list(texts)
        if not texts:
            return []
        if any(not isinstance(t, str) or not t.strip() for t in texts):
            # An empty input embeds to a meaningless vector that would then
            # compete with real evidence at search time.
            raise PermanentEmbeddingError('Cannot embed an empty or non-string input.')

        vectors = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            vectors.extend(self._embed_batch(texts[start:start + self.BATCH_SIZE]))
        return vectors

    def _embed_batch(self, batch):
        from openai import (
            APIConnectionError,
            APIError,
            APIStatusError,
            APITimeoutError,
            RateLimitError,
        )

        started = time.monotonic()
        try:
            response = self._get_client().embeddings.create(
                model=self.model, input=batch, timeout=self.TIMEOUT_SECONDS,
            )
        except RateLimitError as exc:
            self._log(started, False, 'rate_limited', len(batch))
            raise RecoverableEmbeddingError(f'Embedding rate limit hit: {exc}') from exc
        except APITimeoutError as exc:
            self._log(started, False, 'timeout', len(batch))
            raise RecoverableEmbeddingError(f'Embedding request timed out: {exc}') from exc
        except APIConnectionError as exc:
            self._log(started, False, 'connection_error', len(batch))
            raise RecoverableEmbeddingError(f'Could not reach the embedding provider: {exc}') from exc
        except APIStatusError as exc:
            # 5xx is the provider's problem and worth retrying; any other 4xx
            # means the request itself is wrong and never will be right.
            if exc.status_code >= 500:
                self._log(started, False, f'server_error_{exc.status_code}', len(batch))
                raise RecoverableEmbeddingError(
                    f'Embedding provider server error ({exc.status_code}): {exc}'
                ) from exc
            self._log(started, False, f'client_error_{exc.status_code}', len(batch))
            raise PermanentEmbeddingError(
                f'Embedding provider rejected the request ({exc.status_code}): {exc}'
            ) from exc
        except APIError as exc:
            self._log(started, False, 'api_error', len(batch))
            raise PermanentEmbeddingError(f'Embedding provider error: {exc}') from exc

        data = getattr(response, 'data', None)
        if not data or len(data) != len(batch):
            self._log(started, False, 'malformed_response', len(batch))
            raise PermanentEmbeddingError(
                f'Expected {len(batch)} embeddings, got {len(data) if data else 0}.'
            )

        self._log(started, True, None, len(batch))
        # Sorted by index: the API documents order-preservation, but relying on
        # response order to align vectors with chunks would be a silent
        # corruption if that ever changed.
        return [item.embedding for item in sorted(data, key=lambda d: d.index)]

    def _log(self, started, success, error, count):
        """Never logs the key, the input text, or the vectors — only shape and
        timing, matching how the extraction clients log."""
        duration_ms = (time.monotonic() - started) * 1000
        if success:
            logger.info(
                'embedding.request model=%s inputs=%d duration_ms=%.1f success=true',
                self.model, count, duration_ms,
            )
        else:
            logger.warning(
                'embedding.request model=%s inputs=%d duration_ms=%.1f success=false error=%s',
                self.model, count, duration_ms, error,
            )


def _resolve_api_key():
    """`EMBEDDING_API_KEY` first, then the shared AI keys — but only when they
    are usable here. An Anthropic key is explicitly not: Anthropic has no
    embedding endpoint, and handing it to an OpenAI client would surface as a
    confusing 401 rather than the real configuration problem."""
    if settings.EMBEDDING_API_KEY:
        return settings.EMBEDDING_API_KEY
    for candidate in (settings.OPENAI_API_KEY, settings.AI_API_KEY):
        if candidate and not candidate.startswith('sk-ant-'):
            return candidate
    return ''


def embedding_dimensions(model=None):
    """Vector width for the configured model. `EMBEDDING_DIMENSIONS` wins when
    set, so an unrecognised or custom model can still be described without a
    code change."""
    if settings.EMBEDDING_DIMENSIONS:
        return int(settings.EMBEDDING_DIMENSIONS)
    return KNOWN_MODEL_DIMENSIONS.get(model or settings.EMBEDDING_MODEL, 1536)


def is_configured():
    """Whether embeddings could run. Checked before dispatching work so an
    unconfigured deployment stays quiet instead of queueing tasks that will
    only fail."""
    return bool(_resolve_api_key() and settings.EMBEDDING_MODEL)


def get_embedding_service(**kwargs):
    """The factory every caller uses.

    Only one implementation exists today. It is still routed through a factory
    so adding a second (a local model, a different vendor) is one branch here
    rather than an edit at every call site.
    """
    return OpenAIEmbeddingService(**kwargs)
