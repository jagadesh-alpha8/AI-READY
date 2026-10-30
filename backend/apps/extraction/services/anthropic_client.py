"""Reusable client for talking to Anthropic (Claude) and getting back
normalized, validated Python data -- the Claude counterpart to
`openai_client.OpenAIExtractionService`, implementing the exact same public
contract (`extract_structured_data(...)`) so callers never need to know
which provider they're actually talking to. See `ai_service.get_ai_service`
for how one gets chosen.

Claude has no equivalent to OpenAI's `response_format: json_schema` mode --
the reliable way to get schema-constrained JSON back is forcing a single
tool call whose `input_schema` *is* the requested schema (with `strict:
True`, Anthropic's own guarantee that the tool call's `input` matches it
exactly), then reading that tool call's `input` as the result.
"""
import logging
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from anthropic import (
    Anthropic,
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)

from ..exceptions import (
    AIResponseError, PermanentExtractionError, ProviderQuotaExhausted, ProviderRateLimited, ProviderUnavailable,
)
from . import rate_limit
from ..usage import record_anthropic_usage

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = settings.AI_REQUEST_TIMEOUT_SECONDS
#: A document chunk's facts array can run to dozens of items (each with a
#: field_name/value/source_snippet/confidence_reason), which routinely
#: exceeds 4096 output tokens on data-dense pages -- hitting that cap
#: doesn't error, it silently truncates and drops the rest of the chunk's
#: facts (see AnthropicResponseError's max_tokens case). 16000 matches this
#: app's other non-streaming AI calls' headroom without risking the SDK's
#: HTTP timeout.
DEFAULT_MAX_TOKENS = 16000


class AnthropicResponseError(AIResponseError):
    """The request to Claude succeeded, but the response wasn't usable --
    no matching tool call, truncated, refused, or context-window exceeded.
    Retrying an identical request against the same input won't fix this,
    so it's permanent rather than recoverable."""


class AnthropicExtractionService:
    """Thin wrapper around the Anthropic SDK, mirroring OpenAIExtractionService
    field-for-field: initializes the client, sends content constrained to a
    JSON schema via a forced single tool call, and returns parsed Python
    data -- or raises one of this app's own exception types so callers don't
    need to know anything about the Anthropic SDK's exception hierarchy.
    """

    def __init__(self, *, api_key=None, model=None, client=None):
        self.api_key = api_key or settings.AI_API_KEY
        self.model = model or settings.AI_MODEL

        if not self.api_key:
            raise ImproperlyConfigured(
                'No Anthropic API key is configured. Set AI_API_KEY in backend/.env '
                'before using AnthropicExtractionService.'
            )
        if not self.model:
            raise ImproperlyConfigured(
                'No model is configured for AnthropicExtractionService. Set AI_MODEL in '
                'backend/.env, or construct this service with an explicit model=.'
            )

        # `client` is accepted for dependency injection in tests -- normal
        # callers just get a real Anthropic client built from the settings above.
        self._client = client if client is not None else Anthropic(
            api_key=self.api_key, max_retries=settings.AI_SDK_MAX_RETRIES)

    def supports_vision(self):
        from .vision_fallback import model_supports_vision
        return model_supports_vision(self.model, provider='anthropic')

    def extract_structured_data(
        self, *, system_prompt, user_content, response_schema,
        schema_name='extraction_result', timeout=DEFAULT_TIMEOUT_SECONDS, image_b64=None,
    ):
        """Send `user_content` (and optional `image_b64`) to the model under `system_prompt`, constrained
        to `response_schema` (a JSON Schema `dict`) via a forced tool call,
        and return the parsed result (`dict`/`list`, whatever the schema
        describes).

        Raises:
            RecoverableExtractionError: transient failures worth retrying --
                timeouts, rate limits, connection errors, or a 5xx from Claude.
            PermanentExtractionError: failures a retry can't fix -- a 4xx the
                request itself caused (bad request, auth, etc.), or a response
                that doesn't parse as the requested JSON schema.

        Every call logs its model and duration and whether it succeeded --
        never the API key, and never the full prompt/response content.
        """
        started = time.monotonic()
        try:
            # Shared per-key request / token limits across every worker (services/rate_limit.py).
            estimate = rate_limit.estimate_tokens(system_prompt, user_content, output_tokens=DEFAULT_MAX_TOKENS, has_image=bool(image_b64))
            with rate_limit.throttle('anthropic', self.model, self.api_key, estimate) as slot:
                response = self._create(system_prompt, user_content, response_schema, schema_name, timeout, image_b64=image_b64)
                usage = getattr(response, 'usage', None)
                slot.record((getattr(usage, 'input_tokens', 0) or 0) + (getattr(usage, 'output_tokens', 0) or 0)
                            if usage is not None else None)
        except RateLimitError as exc:
            quota = _quota(exc)
            if quota:
                self._log_outcome(started, success=False, error='quota_exhausted')
                rate_limit.mark_exhausted('anthropic', self.model, self.api_key, quota)
                raise ProviderQuotaExhausted(f'The AI provider is out of quota or credit: {quota}.', quota) from exc
            self._log_outcome(started, success=False, error='rate_limited')
            wait = rate_limit.retry_after_seconds(exc)
            rate_limit.block('anthropic', self.model, self.api_key, wait)
            raise ProviderRateLimited(f'Claude rate limit hit: {exc}', retry_after=wait) from exc
        except APITimeoutError as exc:
            self._log_outcome(started, success=False, error='timeout')
            raise ProviderUnavailable(f'Claude request timed out: {exc}', kind='timeout') from exc
        except APIConnectionError as exc:
            self._log_outcome(started, success=False, error='connection_error')
            raise ProviderUnavailable(f'Could not reach Claude: {exc}', kind='network') from exc
        except APIStatusError as exc:
            # "Your credit balance is too low" arrives as a 400: out of credit, not a bad request.
            quota = _quota(exc)
            if quota:
                self._log_outcome(started, success=False, error='quota_exhausted')
                rate_limit.mark_exhausted('anthropic', self.model, self.api_key, quota)
                raise ProviderQuotaExhausted(f'The AI provider is out of quota or credit: {quota}.', quota) from exc
            # 5xx is transient (Anthropic's side) and worth retrying; any
            # other 4xx means the request itself was bad and won't succeed on retry.
            if exc.status_code >= 500:
                self._log_outcome(started, success=False, error=f'server_error_{exc.status_code}')
                raise ProviderUnavailable(f'Claude server error ({exc.status_code}): {exc}', kind='server_error',
                                          retry_after=rate_limit.retry_after_seconds(exc)) from exc
            self._log_outcome(started, success=False, error=f'client_error_{exc.status_code}')
            raise PermanentExtractionError(f'Claude rejected the request ({exc.status_code}): {exc}') from exc
        except APIError as exc:
            # Catch-all for any other SDK-raised error not covered above.
            self._log_outcome(started, success=False, error='api_error')
            raise PermanentExtractionError(f'Claude API error: {exc}') from exc

        # Billed even if it then fails to parse -- record it now (no-op outside
        # an extraction's usage scope).
        record_anthropic_usage(response, model=self.model, duration_ms=(time.monotonic() - started) * 1000)

        try:
            result = self._parse_response(response, schema_name)
        except AnthropicResponseError:
            self._log_outcome(started, success=False, error='invalid_response')
            raise

        self._log_outcome(started, success=True)
        return result

    def _create(self, system_prompt, user_content, response_schema, schema_name, timeout, image_b64=None):
        if image_b64:
            content_blocks = [
                {
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': 'image/png',
                        'data': image_b64,
                    },
                },
                {'type': 'text', 'text': user_content},
            ]
        else:
            content_blocks = user_content

        return self._client.messages.create(
            model=self.model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system_prompt,
            messages=[{'role': 'user', 'content': content_blocks}],
            tools=[{
                'name': schema_name,
                'description': f'Return data matching the {schema_name} schema. Always call this tool.',
                'input_schema': response_schema,
                'strict': True,
            }],
            tool_choice={'type': 'tool', 'name': schema_name, 'disable_parallel_tool_use': True},
            timeout=timeout,
            # Repeatable extraction (settings.AI_TEMPERATURE); Anthropic has no seed.
            **({'temperature': settings.AI_TEMPERATURE} if settings.AI_TEMPERATURE is not None else {}),
        )

    @staticmethod
    def _parse_response(response, schema_name):
        if response.stop_reason == 'max_tokens':
            raise AnthropicResponseError('Claude response was truncated (stop_reason=max_tokens).')
        if response.stop_reason == 'refusal':
            raise AnthropicResponseError('Claude declined to answer (stop_reason=refusal).')
        if response.stop_reason == 'model_context_window_exceeded':
            raise AnthropicResponseError('The input was too large for the model\'s context window.')

        for block in response.content or []:
            if getattr(block, 'type', None) == 'tool_use' and getattr(block, 'name', None) == schema_name:
                return block.input

        raise AnthropicResponseError(f'Claude response had no "{schema_name}" tool call.')

    def _log_outcome(self, started, *, success, error=None):
        duration_ms = (time.monotonic() - started) * 1000
        if success:
            logger.info('anthropic.request model=%s duration_ms=%.1f success=true', self.model, duration_ms)
        else:
            logger.warning(
                'anthropic.request model=%s duration_ms=%.1f success=false error=%s',
                self.model, duration_ms, error,
            )


def _quota(exc):
    """The out-of-quota reason in an SDK error, or '' (services/provider_errors.py)."""
    from .provider_errors import quota_exhaustion
    return quota_exhaustion(getattr(exc, 'status_code', None), getattr(exc, 'body', None), getattr(exc, 'message', str(exc)))
