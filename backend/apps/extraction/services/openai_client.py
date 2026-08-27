"""Reusable client for talking to OpenAI and getting back normalized,
validated Python data.

This module is deliberately *not* a `FactExtractor`/`PageReader`/etc.
implementation (see `base.py`) -- it's the layer those real implementations
will call into once they're built. Nothing in `ExtractionPipeline` uses this
yet; `stub.py` is still what's active. Keeping the two separate means the
OpenAI-specific error handling (rate limits, timeouts, malformed responses)
lives in one tested place instead of being duplicated across whichever
interfaces eventually wrap it.

Celery tasks must not call the OpenAI SDK directly -- they should go through
`OpenAIExtractionService` (or a `FactExtractor`/etc. built on top of it), so
retry/timeout/error handling stays consistent and testable without needing
real network access.
"""
import json
import logging
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from ..exceptions import AIResponseError, PermanentExtractionError, RecoverableExtractionError

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 60


class OpenAIResponseError(AIResponseError):
    """The request to OpenAI succeeded, but the response wasn't usable --
    empty, truncated, blocked by the content filter, or not valid JSON.
    Retrying an identical request against the same input won't fix this,
    so it's permanent rather than recoverable."""


class OpenAIExtractionService:
    """Thin wrapper around the OpenAI SDK: initializes the client, sends
    content with a JSON-schema-constrained request, and returns parsed
    Python data -- or raises one of this app's own exception types so
    callers (ultimately `tasks.py`, via a future `FactExtractor`) don't need
    to know anything about the OpenAI SDK's exception hierarchy.
    """

    def __init__(self, *, api_key=None, model=None, base_url=None, client=None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_EXTRACTION_MODEL
        # Unset means "OpenAI's own api.openai.com" (the SDK's own default).
        # Set means "an OpenAI-compatible endpoint" -- a local router/proxy,
        # a self-hosted gateway, etc. -- that speaks the same request/
        # response shape but isn't OpenAI itself.
        self.base_url = base_url if base_url is not None else settings.AI_BASE_URL or None

        if not self.api_key:
            raise ImproperlyConfigured(
                'OPENAI_API_KEY is not set. Add it to backend/.env (see .env.example) '
                'before using OpenAIExtractionService.'
            )
        if not self.model:
            raise ImproperlyConfigured(
                'OPENAI_EXTRACTION_MODEL is not set. Add it to backend/.env (see .env.example) '
                'before using OpenAIExtractionService.'
            )

        # `client` is accepted for dependency injection in tests -- normal
        # callers just get a real OpenAI client built from the settings above.
        self._client = client if client is not None else OpenAI(api_key=self.api_key, base_url=self.base_url)

    def extract_structured_data(
        self, *, system_prompt, user_content, response_schema,
        schema_name='extraction_result', timeout=DEFAULT_TIMEOUT_SECONDS,
    ):
        """Send `user_content` to the model under `system_prompt`, constrained
        to `response_schema` (a JSON Schema `dict`), and return the parsed
        result (`dict`/`list`, whatever the schema describes).

        Raises:
            RecoverableExtractionError: transient failures worth retrying --
                timeouts, rate limits, connection errors, or a 5xx from OpenAI.
            PermanentExtractionError: failures a retry can't fix -- a 4xx the
                request itself caused (bad request, auth, etc.), or a response
                that doesn't parse as the requested JSON schema.

        Every call logs its model and duration and whether it succeeded --
        never the API key, and never the full prompt/response content (only
        a length), so request/response bodies never end up in application
        logs even though they may contain document text.
        """
        started = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                response_format={
                    'type': 'json_schema',
                    'json_schema': {
                        'name': schema_name,
                        'schema': response_schema,
                        'strict': True,
                    },
                },
                timeout=timeout,
            )
        except RateLimitError as exc:
            self._log_outcome(started, success=False, error='rate_limited')
            raise RecoverableExtractionError(f'OpenAI rate limit hit: {exc}') from exc
        except APITimeoutError as exc:
            self._log_outcome(started, success=False, error='timeout')
            raise RecoverableExtractionError(f'OpenAI request timed out: {exc}') from exc
        except APIConnectionError as exc:
            self._log_outcome(started, success=False, error='connection_error')
            raise RecoverableExtractionError(f'Could not reach OpenAI: {exc}') from exc
        except APIStatusError as exc:
            # 5xx is transient (OpenAI's side) and worth retrying; any other
            # 4xx means the request itself was bad and won't succeed on retry.
            if exc.status_code >= 500:
                self._log_outcome(started, success=False, error=f'server_error_{exc.status_code}')
                raise RecoverableExtractionError(f'OpenAI server error ({exc.status_code}): {exc}') from exc
            self._log_outcome(started, success=False, error=f'client_error_{exc.status_code}')
            raise PermanentExtractionError(f'OpenAI rejected the request ({exc.status_code}): {exc}') from exc
        except APIError as exc:
            # Catch-all for any other SDK-raised error not covered above.
            self._log_outcome(started, success=False, error='api_error')
            raise PermanentExtractionError(f'OpenAI API error: {exc}') from exc

        try:
            result = self._parse_response(response)
        except OpenAIResponseError:
            self._log_outcome(started, success=False, error='invalid_response')
            raise

        self._log_outcome(started, success=True)
        return result

    def _log_outcome(self, started, *, success, error=None):
        duration_ms = (time.monotonic() - started) * 1000
        if success:
            logger.info('openai.request model=%s duration_ms=%.1f success=true', self.model, duration_ms)
        else:
            logger.warning(
                'openai.request model=%s duration_ms=%.1f success=false error=%s',
                self.model, duration_ms, error,
            )

    @staticmethod
    def _parse_response(response):
        choices = getattr(response, 'choices', None)
        if not choices:
            raise OpenAIResponseError('OpenAI response had no choices.')

        choice = choices[0]
        if choice.finish_reason == 'length':
            raise OpenAIResponseError('OpenAI response was truncated (finish_reason=length).')
        if choice.finish_reason == 'content_filter':
            raise OpenAIResponseError('OpenAI response was blocked by the content filter.')

        content = getattr(choice.message, 'content', None)
        if not content:
            raise OpenAIResponseError('OpenAI response had no content.')

        try:
            return json.loads(content)
        except (TypeError, ValueError) as exc:
            raise OpenAIResponseError(f'OpenAI response was not valid JSON: {exc}') from exc
