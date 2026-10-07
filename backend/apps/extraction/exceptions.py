class ExtractionError(Exception):
    """Base class for extraction pipeline errors."""


class RecoverableExtractionError(ExtractionError):
    """A transient failure (I/O hiccup, temporary lock, flaky dependency) that
    is safe and worth retrying."""


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
