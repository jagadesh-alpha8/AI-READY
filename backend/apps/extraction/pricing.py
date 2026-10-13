"""AI price table: USD per 1 million tokens, used to put a cost on every
recorded AI call (apps.extraction.models.AIUsage).

The cost is worked out and stored at the moment of the call, so a later price
change never rewrites what an earlier sprint cost.

Defaults are Anthropic's published API list prices (as of 2026-09). Models not
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
    'claude-sonnet-5-5': {'input': 2, 'output': 10, 'cache_read': 0.20},
    'claude-sonnet-5': {'input': 2, 'output': 10},
    'claude-sonnet-4-6': {'input': 3, 'output': 15},
    'claude-haiku-4-5': {'input': 1, 'output': 5},
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
    p_in = Decimal(str(prices.get('input', 0)))
    p_out = Decimal(str(prices.get('output', 0)))
    p_read = Decimal(str(prices['cache_read'])) if 'cache_read' in prices else p_in * Decimal('0.1')
    p_write = Decimal(str(prices['cache_write'])) if 'cache_write' in prices else p_in * Decimal('1.25')
    total = (
        Decimal(input_tokens) * p_in + Decimal(output_tokens) * p_out
        + Decimal(cache_read_tokens) * p_read + Decimal(cache_write_tokens) * p_write
    ) / _PER_MILLION
    return total.quantize(Decimal('0.000001'))
