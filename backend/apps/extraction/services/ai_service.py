"""Provider-agnostic AI service factory.

Every AI call site in this app (openai_classifier.py, openai_fact_extractor.
py, conflict_checker.py) goes through `get_ai_service()` instead of
constructing `OpenAIExtractionService` directly, so switching providers is
ever only "paste a different key (and maybe a base URL) into .env" -- never
a code change. Two ways a provider gets picked, checked in this order:

1. `AI_BASE_URL` is set -- an OpenAI-*compatible* endpoint (a local model
   router, a self-hosted gateway, a multi-provider proxy, ...) that isn't
   OpenAI itself. Used exactly as configured; a key's format means nothing
   here since these services mint their own key formats.
2. Otherwise, the configured key's own format (OpenAI and Anthropic keys
   are unambiguously prefixed) -- no separate "which provider" setting to
   drift out of sync with the key actually in use.

All concrete services (`OpenAIExtractionService`, `AnthropicExtractionService`,
and any OpenAI-compatible endpoint via the former with a `base_url`)
implement the identical `extract_structured_data(system_prompt=, user_content=,
response_schema=, schema_name=)` contract and raise the same
`RecoverableExtractionError`/`PermanentExtractionError` taxonomy, so nothing
downstream of this factory needs to change to support a new one.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

#: Sensible default model per provider, used only when no explicit model is
#: configured (AI_MODEL, or -- OpenAI only -- the older OPENAI_EXTRACTION_MODEL).
#: Both picked for the same reason: fast, cheap, and fully capable of the
#: structured-extraction work this app asks of them.
DEFAULT_MODELS = {
    'openai': 'gpt-4o-mini',
    'anthropic': 'claude-haiku-4-5-20251001',
}

#: Recognized API key prefixes. Checked longest/most-specific first --
#: Anthropic's 'sk-ant-' would otherwise also match a naive 'sk-' check.
_PROVIDER_KEY_PREFIXES = [
    ('anthropic', 'sk-ant-'),
    ('openai', 'sk-'),
]


def detect_provider(api_key):
    """Return 'openai' or 'anthropic' based purely on the key's own format
    -- never guessed, never defaulted. An unrecognized format fails loudly
    rather than silently assuming a provider, so a typo'd or unsupported key
    is caught immediately instead of surfacing as a confusing auth error
    from the wrong SDK."""
    for provider, prefix in _PROVIDER_KEY_PREFIXES:
        if api_key.startswith(prefix):
            return provider
    raise ImproperlyConfigured(
        f'Could not identify an AI provider from this API key\'s format (starts with '
        f'{api_key[:7]!r}...). Recognized formats: OpenAI ("sk-..."), Anthropic ("sk-ant-...").'
    )


def _resolve_model(provider, explicit_model):
    if explicit_model:
        return explicit_model
    if settings.AI_MODEL:
        return settings.AI_MODEL
    # OPENAI_EXTRACTION_MODEL is provider-specific and predates AI_MODEL --
    # only honour it when the key actually in use is an OpenAI one, or a
    # leftover "gpt-4o-mini" would get handed to a Claude client the moment
    # someone swaps in an Anthropic key without also clearing this setting.
    if provider == 'openai' and settings.OPENAI_EXTRACTION_MODEL:
        return settings.OPENAI_EXTRACTION_MODEL
    return DEFAULT_MODELS[provider]


def get_ai_service(*, api_key=None, model=None, base_url=None):
    """Return the right concrete extraction service for whichever API key is
    configured. `AI_API_KEY` takes precedence; `OPENAI_API_KEY` is still
    read unchanged, for anyone already using it from before multi-provider
    support existed -- both are just "the configured key" here, whichever
    provider it turns out to belong to.

    A configured `AI_BASE_URL` (a local router, self-hosted gateway, or any
    other OpenAI-*compatible* endpoint) always wins over key-format
    detection: the caller has already told us exactly where to send
    requests, so guessing a provider from what the key looks like would
    only be wrong -- these services' keys don't follow OpenAI's or
    Anthropic's format at all.
    """
    resolved_key = api_key or settings.AI_API_KEY or settings.OPENAI_API_KEY
    if not resolved_key:
        raise ImproperlyConfigured(
            'No AI provider API key is configured. Set AI_API_KEY (or OPENAI_API_KEY) in '
            'backend/.env before using get_ai_service().'
        )

    resolved_base_url = base_url or settings.AI_BASE_URL
    if resolved_base_url:
        resolved_model = model or settings.AI_MODEL or settings.OPENAI_EXTRACTION_MODEL
        if not resolved_model:
            raise ImproperlyConfigured(
                'AI_BASE_URL is set but no model is configured. Set AI_MODEL to the model ID '
                'your OpenAI-compatible endpoint expects.'
            )
        from .openai_client import OpenAIExtractionService
        return OpenAIExtractionService(api_key=resolved_key, model=resolved_model, base_url=resolved_base_url)

    provider = detect_provider(resolved_key)
    resolved_model = _resolve_model(provider, model)

    if provider == 'anthropic':
        from .anthropic_client import AnthropicExtractionService
        return AnthropicExtractionService(api_key=resolved_key, model=resolved_model)

    from .openai_client import OpenAIExtractionService
    return OpenAIExtractionService(api_key=resolved_key, model=resolved_model)
