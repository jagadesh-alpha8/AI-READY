"""AI price table: USD per 1 million tokens, used to put a cost on every
recorded AI call (apps.extraction.models.AIUsage).

The cost is worked out and stored at the moment of the call, so a later price
change never rewrites what an earlier sprint cost.

Defaults are Anthropic's and OpenAI's published API list prices (as of 2026-11). A `long_context` entry gives the
rates a request pays for its whole prompt once the prompt (cache reads and writes included) is over `threshold`
tokens. Models not
listed -- an OpenAI-compatible router combo, a self-hosted model -- still have
their tokens recorded, with cost left empty until a price is configured.
Override or add prices without a code change via AI_PRICING_JSON in .env, e.g.:

    AI_PRICING_JSON={"my-combo": {"input": 0, "output": 0},
                     "claude-sonnet-5-5": {"input": 2, "output": 10, "cache_read": 0.2}}

`cache_read` / `cache_write` default to 10% / 125% of the input price when not
given (prompt-caching reads and 5-minute cache writes).
"""
import json
import logging
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_PRICES = {
    'claude-fable-5-1': {'input': 10, 'output': 50, 'cache_read': 0.25},
    'claude-fable-5': {'input': 10, 'output': 50},
    'claude-opus-5-5': {'input': 4, 'output': 20, 'cache_read': 0.20},
    'claude-opus-5': {'input': 5, 'output': 25},
    'claude-opus-4-8': {'input': 5, 'output': 25},
    'claude-opus-4-7': {'input': 5, 'output': 25},
    'claude-opus-4-6': {'input': 5, 'output': 25},
    'claude-sonnet-5-5': {'input': 2, 'output': 10, 'cache_read': 0.10},
    'claude-sonnet-5': {'input': 2, 'output': 10},
    'claude-sonnet-4-6': {'input': 3, 'output': 15},
    'claude-haiku-5-5': {'input': 0.10, 'output': 0.50, 'cache_read': 0.01, 'cache_write': 0.125,
                         'long_context': {'threshold': 100000, 'input': 0.50, 'output': 2.50, 'cache_read': 0.05,
                                          'cache_write': 0.625}},
    'claude-haiku-4-5': {'input': 1, 'output': 5},
    # OpenAI (2026-11 list prices). Prompts over 272,000 tokens: 2x input and cache, 1.5x output, whole request.
    'gpt-6-luna': {'input': 0.10, 'output': 0.50, 'cache_read': 0.01, 'cache_write': 0.125,
                   'long_context': {'threshold': 272000, 'input': 0.20, 'output': 0.75, 'cache_read': 0.02,
                                    'cache_write': 0.25}},
    'gpt-6.1-sol': {'input': 2, 'output': 10, 'cache_read': 0.10, 'cache_write': 2.50,
                    'long_context': {'threshold': 272000, 'input': 4, 'output': 15, 'cache_read': 0.20,
                                     'cache_write': 5}},
}

_PER_MILLION = Decimal(1_000_000)


def price_table():
    table = {k: dict(v) for k, v in DEFAULT_PRICES.items()}
    raw = getattr(settings, 'AI_PRICING_JSON', '') or ''
    if raw.strip():
        try:
            for model, prices in json.loads(raw).items():
                table[model] = {**table.get(model, {}), **prices}
        except (ValueError, AttributeError) as exc:
            logger.error('ai_pricing.invalid_json error=%s (using default prices)', exc)
    return table


def prices_for(model):
    """Price entry for `model`, or None if unknown. Tolerates provider
    prefixes and dated suffixes, e.g. 'anthropic/claude-haiku-4-5-20251001'."""
    if not model:
        return None
    table = price_table()
    if model in table:
        return table[model]
    bare = model.rsplit('/', 1)[-1]
    if bare in table:
        return table[bare]
    # Longest known model id the name starts with (handles date suffixes).
    for known in sorted(table, key=len, reverse=True):
        if bare.startswith(known):
            return table[known]
    return None


def cost_usd(model, *, input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0):
    """USD cost of one call, or None when the model has no configured price.
    `input_tokens` excludes cache reads/writes (they're priced separately)."""
    prices = prices_for(model)
    if prices is None:
        return None
    long = prices.get('long_context') or {}
    if long.get('threshold') and input_tokens + cache_read_tokens + cache_write_tokens > long['threshold']:
        prices = {**prices, **{k: v for k, v in long.items() if k != 'threshold'}}
    p_in = Decimal(str(prices.get('input', 0)))
    p_out = Decimal(str(prices.get('output', 0)))
    p_read = Decimal(str(prices['cache_read'])) if 'cache_read' in prices else p_in * Decimal('0.1')
    p_write = Decimal(str(prices['cache_write'])) if 'cache_write' in prices else p_in * Decimal('1.25')
    total = (
        Decimal(input_tokens) * p_in + Decimal(output_tokens) * p_out
        + Decimal(cache_read_tokens) * p_read + Decimal(cache_write_tokens) * p_write
    ) / _PER_MILLION
    return total.quantize(Decimal('0.000001'))


def positive_token_prices(model):
    """Hosted budgets need positive configured rates, even for a free-tier account."""
    try:
        prices = prices_for(model) or {}
        values = [Decimal(str(prices[key])) for key in ('input', 'output')]
        return all(value.is_finite() and value > 0 for value in values)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return False
