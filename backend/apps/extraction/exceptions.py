class ExtractionError(Exception):
    """Base class for extraction pipeline errors."""


class RecoverableExtractionError(ExtractionError):
    """A transient failure (I/O hiccup, temporary lock, flaky dependency) that
    is safe and worth retrying.

    `kind` says what kind of transient failure it was (network, timeout, server_error, rate_limited, busy, io)
    and `retry_after` how many seconds the provider asked us to wait (Retry-After), when it said; the task's
    backoff respects it (tasks._retry_countdown)."""

    kind = 'transient'

    def __init__(self, message='', *, kind=None, retry_after=None):
        super().__init__(message)
        if kind:
            self.kind = kind
        self.retry_after = retry_after


class ProviderRateLimited(RecoverableExtractionError):
    """The provider (or our own shared rate limit, services/rate_limit.py) said "too many requests / tokens
    right now". Clears by itself; retried after `retry_after` when known."""

    kind = 'rate_limited'


class ProviderUnavailable(RecoverableExtractionError):
    """The provider could not be reached, timed out or answered with a 5xx -- retried with backoff + jitter."""

    kind = 'network'


class ProviderQuotaExhausted(RecoverableExtractionError):
    """The AI provider behind this router / endpoint is out of quota or credit (services/provider_errors.py).
    Not the document's fault: in multi-router mode the router is taken out of rotation until an admin
    reactivates it and the document moves to the next router; in single mode retrying cannot help."""

    kind = 'quota_exhausted'

    def __init__(self, message, reason=''):
        super().__init__(message)
        self.reason = reason or message
        # Credit (the account's balance) vs quota (a plan / billing limit): both need a person, neither clears
        # with a retry. Shown on the monitor; neither is ever retried in a loop.
        text = f'{message} {reason}'.lower()
        self.kind = 'credit_exhausted' if ('credit' in text or '402' in text or 'payment' in text
                                           or 'balance' in text) else 'quota_exhausted'


class AllRoutersExhausted(RecoverableExtractionError):
    """Every configured router is out of quota/credit (or was already tried for this document). The job waits
    -- bounded by AI_ROUTER_EXHAUSTED_MAX_WAITS -- for an admin to reactivate a router."""


class PermanentExtractionError(ExtractionError):
    """A failure that retrying will not fix (corrupt/unsupported file,
    a document that no longer exists). The job is failed immediately,
    without burning retry attempts."""


class AIResponseError(PermanentExtractionError):
    """An AI provider's request succeeded, but the response wasn't usable
    (empty, truncated, refused, or missing the shape a caller asked for).
    Provider-specific response errors (openai_client.OpenAIResponseError,
    anthropic_client.AnthropicResponseError) subclass this so code that
    doesn't care which provider answered can catch just this one type."""


class ExtractionCancelled(Exception):
    """The user stopped this job (Stop / Stop Processing on the AI Processing
    Monitor). Raised at the next safe checkpoint -- between pipeline steps or
    between AI calls -- so the worker abandons the document cleanly instead of
    finishing it and overwriting the "cancelled" status. Deliberately not an
    ExtractionError: a stop is not a failure and must never be retried."""


class ExtractionContinues(Exception):
    """This attempt did its share of a large document's chunks (OPENAI_FACT_EXTRACTION_MAX_CHUNKS new AI calls
    per attempt) and saved them; the task queues the next attempt straight away to carry on. Not a failure and
    not counted against the retry budget -- the document is finished over several bounded attempts."""

    def __init__(self, done, total):
        super().__init__(f'{done} of {total} text chunks read; continuing with the rest.')
        self.done, self.total = done, total


class ExtractionSuperseded(ExtractionCancelled):
    """Another worker now owns this job: it was recovered after this worker stopped sending heartbeats
    (services/recovery.py) and handed out again under a new task id. This worker abandons it at its next
    checkpoint without touching the job's status -- the new owner carries on (reusing saved pages / chunks)."""
