"""Shared AI request / token rate limits, across every worker, in the Redis the project already runs.

    with throttle(provider, model, api_key, estimated_tokens) as slot:
        response = client.call(...)
        slot.record(actual_tokens)

Limits are per (provider, model, API key) -- the key is only ever used as a short SHA-256 fingerprint, never
stored or logged -- over fixed one-minute windows:

    AI_RATE_LIMIT_RPM   requests per minute   (0 = no limit, the default)
    AI_RATE_LIMIT_TPM   tokens per minute     (0 = no limit, the default); a request counts its estimate up
                        front and is corrected to the provider's reported usage afterwards

A request that would go over waits for the next window, up to AI_RATE_LIMIT_MAX_WAIT_SECONDS; past that it
raises ProviderRateLimited so the job is retried later instead of holding a worker. When a provider answers
429 with a Retry-After, `block()` makes every worker using that key wait it out, not just the one that got it.

When a provider says the account is out of quota or credit, `mark_exhausted()` records it for
AI_QUOTA_EXHAUSTED_HOLD_SECONDS: every other worker's request with that key then fails at once with the same
reason instead of each spending a call (and a retry) to find out. It clears by itself after the hold, or with
`manage.py ai_router_reactivate`.

Redis unavailable: requests go ahead unthrottled (logged) -- the provider's own 429s still apply.
"""
import hashlib
import logging
import time
from contextlib import contextmanager

from django.conf import settings

from ..exceptions import ProviderQuotaExhausted, ProviderRateLimited

logger = logging.getLogger(__name__)

_PREFIX = 'aios:ai-rate'
_redis = None


def _client():
    global _redis
    if _redis is None:
        import redis
        url = settings.AI_ROUTER_REDIS_URL or settings.CELERY_BROKER_URL
        _redis = redis.Redis.from_url(url, socket_timeout=3, socket_connect_timeout=3)
    return _redis


def bucket(provider, model, api_key):
    """'openai_compatible:qwen:1a2b3c4d5e6f' -- the key's fingerprint only."""
    fingerprint = hashlib.sha256((api_key or '').encode()).hexdigest()[:12]
    return f'{provider or "ai"}:{model or "?"}:{fingerprint}'


def estimate_tokens(*texts, output_tokens=None, has_image=False):
    """A conservative token estimate for a request: ~4 characters per token, plus room for the answer and images."""
    chars = 0
    extra_tokens = 1000 if has_image else 0
    for t in texts:
        if isinstance(t, str):
            chars += len(t)
        elif isinstance(t, list):
            for part in t:
                if isinstance(part, dict):
                    if part.get('type') == 'text':
                        chars += len(part.get('text') or '')
                    elif 'image' in part.get('type', ''):
                        extra_tokens += 1000
                elif isinstance(part, str):
                    chars += len(part)
    return chars // 4 + extra_tokens + (output_tokens if output_tokens is not None else settings.AI_RATE_LIMIT_OUTPUT_ESTIMATE)


class Slot:
    def __init__(self, key, window, estimated):
        self._key, self._window, self.estimated = key, window, estimated

    def record(self, actual_tokens):
        """Correct this window's token count from the estimate to what the provider reported."""
        if not self._key or not settings.AI_RATE_LIMIT_TPM or actual_tokens is None:
            return
        try:
            _client().incrby(f'{self._key}:tok:{self._window}', int(actual_tokens) - int(self.estimated))
        except Exception as exc:
            logger.warning('ai.rate_limit.record_failed error=%s', exc)


def _wait_blocked(client, key, deadline):
    """Honour a Retry-After another worker received for this key."""
    until = client.get(f'{key}:blocked')
    if not until:
        return
    wait = float(until) - time.time()
    if wait <= 0:
        return
    if time.time() + wait > deadline:
        raise ProviderRateLimited(f'The AI provider asked to wait {wait:.0f}s before more requests.',
                                  retry_after=wait)
    time.sleep(wait)


def enabled():
    """AI_RATE_LIMIT_ENABLED (default on; off in the test run, which must never write to a real Redis)."""
    return settings.AI_RATE_LIMIT_ENABLED


@contextmanager
def throttle(provider, model, api_key, estimated_tokens=0):
    if not enabled():
        yield Slot(None, None, estimated_tokens)
        return
    rpm, tpm = settings.AI_RATE_LIMIT_RPM, settings.AI_RATE_LIMIT_TPM
    key = f'{_PREFIX}:{bucket(provider, model, api_key)}'
    try:
        client = _client()
        reason = client.get(f'{key}:exhausted')
        if reason:
            reason = reason.decode() if isinstance(reason, bytes) else str(reason)
            raise ProviderQuotaExhausted(f'The AI provider is out of quota or credit: {reason} (found by an earlier '
                                         'request; not retried).', reason)
        deadline = time.time() + settings.AI_RATE_LIMIT_MAX_WAIT_SECONDS
        _wait_blocked(client, key, deadline)
        while rpm or tpm:
            window = int(time.time() // 60)
            pipe = client.pipeline()
            pipe.incr(f'{key}:req:{window}')
            pipe.incrby(f'{key}:tok:{window}', int(estimated_tokens))
            pipe.expire(f'{key}:req:{window}', 120)
            pipe.expire(f'{key}:tok:{window}', 120)
            requests, tokens, _, _ = pipe.execute()
            over = (rpm and requests > rpm) or (tpm and tokens > tpm and tokens > estimated_tokens)
            if not over:
                break
            # Give the window back what we just took, then wait for the next one.
            pipe = client.pipeline()
            pipe.decr(f'{key}:req:{window}')
            pipe.decrby(f'{key}:tok:{window}', int(estimated_tokens))
            pipe.execute()
            wait = (window + 1) * 60 - time.time() + 0.05
            if time.time() + wait > deadline:
                raise ProviderRateLimited(
                    f'Shared AI rate limit reached ({rpm or "-"} requests / {tpm or "-"} tokens per minute); '
                    'retrying later.', retry_after=wait)
            logger.info('ai.rate_limit.waiting bucket=%s seconds=%.1f', key.rsplit(':', 1)[-1], wait)
            time.sleep(wait)
        else:
            window = None
    except (ProviderRateLimited, ProviderQuotaExhausted):
        raise
    except Exception as exc:  # Redis down: go ahead; the provider's own limits still apply
        logger.warning('ai.rate_limit.unavailable error=%s', exc)
        yield Slot(None, None, estimated_tokens)
        return
    yield Slot(key, window, estimated_tokens)


def mark_exhausted(provider, model, api_key, reason):
    if not enabled():
        return
    key = f'{_PREFIX}:{bucket(provider, model, api_key)}'
    try:
        _client().set(f'{key}:exhausted', str(reason)[:300], ex=max(1, settings.AI_QUOTA_EXHAUSTED_HOLD_SECONDS))
    except Exception as exc:
        logger.warning('ai.rate_limit.exhausted_mark_failed error=%s', exc)


def clear_exhausted():
    """Forget every "out of quota / credit" mark (credit was added). Returns how many were cleared."""
    client = _client()
    keys = list(client.scan_iter(f'{_PREFIX}:*:exhausted'))
    return client.delete(*keys) if keys else 0


def block(provider, model, api_key, seconds):
    """A provider said Retry-After `seconds`: every worker using this key waits it out."""
    if not seconds or seconds <= 0 or not enabled():
        return
    key = f'{_PREFIX}:{bucket(provider, model, api_key)}'
    seconds = min(float(seconds), float(settings.AI_RETRY_MAX_DELAY_SECONDS))
    try:
        _client().set(f'{key}:blocked', time.time() + seconds, ex=int(seconds) + 1)
    except Exception as exc:
        logger.warning('ai.rate_limit.block_failed error=%s', exc)


def retry_after_seconds(exc):
    """Seconds a provider error asks us to wait: `retry-after-ms`, `retry-after` (seconds or an HTTP date), or
    the x-ratelimit reset headers; None when it does not say."""
    response = getattr(exc, 'response', None)
    headers = getattr(response, 'headers', None) or {}
    try:
        value = headers.get('retry-after-ms')
        if value:
            return max(0.0, float(value) / 1000)
        value = headers.get('retry-after')
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                from email.utils import parsedate_to_datetime
                return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        for name in ('x-ratelimit-reset-requests', 'x-ratelimit-reset-tokens', 'x-ratelimit-reset'):
            value = headers.get(name)
            if value:
                return _duration(value)
    except Exception:
        return None
    return None


def _duration(text):
    """'1s', '6m0s', '250ms', '20' -> seconds."""
    import re
    text = str(text).strip()
    if re.fullmatch(r'\d+(\.\d+)?', text):
        return float(text)
    total, matched = 0.0, False
    for number, unit in re.findall(r'(\d+(?:\.\d+)?)(ms|h|m|s)', text):
        matched = True
        total += float(number) * {'ms': 0.001, 's': 1, 'm': 60, 'h': 3600}[unit]
    return total if matched else None
