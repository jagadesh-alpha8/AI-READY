"""Telling "this provider account is out of quota / credit" apart from every other provider error.

    quota_exhaustion(status_code, body, message)  -> a short reason, or '' when it is not quota exhaustion

Only an explicit out-of-credit / billing / quota answer counts -- never a bare status code:
- 402 Payment Required always counts;
- 400 / 403 / 429 (and a 5xx that a router uses to wrap the provider's answer) count only when the provider's
  code or message says so: OpenAI `insufficient_quota` / `billing_hard_limit_reached`, Anthropic "credit balance
  is too low", Gemini / Google "exceeded your current quota" / billing, OpenRouter "insufficient credits", ...
A per-minute / per-second limit ("Quota exceeded for ... per minute", "Rate limit reached ... RPM") is a
temporary rate limit, not exhaustion. Invalid requests, unknown models, context-length errors and any other
4xx keep their normal (permanent) handling. Nothing here ever returns or logs a key.
"""
import json
import re

#: Provider error codes / types that mean the account cannot pay for more requests.
_QUOTA_CODES = {
    'insufficient_quota', 'billing_hard_limit_reached', 'billing_not_active', 'insufficient_credits',
    'credit_balance_too_low', 'quota_exceeded', 'payment_required', 'out_of_credits',
}
#: Messages that mean the same, as providers and routers word them.
_QUOTA_TEXT = re.compile(
    r'(insufficient[_ ]quota|exceeded your current quota|credit balance is too low|'
    r'insufficient (?:credits?|balance|funds)|out of credits?|no credits? (?:left|remaining)|'
    r'billing (?:hard )?limit|billing (?:details|account|is not active|not active)|payment required|'
    r'quota (?:has been )?exhausted|quota exceeded|exceeded (?:the |your )?(?:monthly |daily )?quota|'
    r'purchase (?:more )?credits|add (?:more )?credits|top[- ]?up)',
    re.IGNORECASE)
#: ...unless the limit is per time window: that clears by itself.
_TEMPORARY = re.compile(
    r'(per[_ ]?(?:minute|second|min|sec)|perminute|persecond|\brpm\b|\btpm\b|\brps\b|'
    r'requests per|tokens per|try again in|retry after|please retry in)', re.IGNORECASE)


def _texts(body, message):
    """Codes and messages from an error body (dict, JSON text or anything printable) plus the SDK message."""
    codes, texts = set(), [str(message or '')]
    if isinstance(body, (bytes, str)):
        try:
            body = json.loads(body)
        except (TypeError, ValueError):
            texts.append(body.decode(errors='replace') if isinstance(body, bytes) else body)
            body = None

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('code', 'type', 'status', 'reason') and isinstance(item, str):
                    codes.add(item.strip().lower())
                if key in ('message', 'detail', 'error', 'msg') and isinstance(item, str):
                    texts.append(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(body)
    return codes, ' '.join(texts)


def quota_exhaustion(status_code, body=None, message=''):
    codes, text = _texts(body, message)
    if status_code == 402:
        return 'payment required (HTTP 402)'
    hit = next((c for c in codes if c in _QUOTA_CODES), '') or (_QUOTA_TEXT.search(text) or [''])[0]
    if not hit:
        return ''
    if _TEMPORARY.search(text):
        return ''  # a per-minute / per-second quota is a rate limit that clears by itself
    return f'{hit.lower()} (HTTP {status_code})' if status_code else hit.lower()
