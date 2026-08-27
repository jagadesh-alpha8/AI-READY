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
