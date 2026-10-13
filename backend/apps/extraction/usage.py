"""Recording AI token usage (and its cost) for every AI call made during
extraction -- see apps.extraction.models.AIUsage.

The extraction pipeline opens a `usage_scope(...)` saying which sprint /
document / job / stage the next AI calls belong to; the AI clients call
`record_openai_usage` / `record_anthropic_usage` with each raw response.
Calls made outside any scope (ad-hoc scripts, unit tests of the clients) are
not recorded. Recording must never break an extraction, so every failure here
is logged and swallowed.
"""
import contextvars
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_scope = contextvars.ContextVar('ai_usage_scope', default=None)


@contextmanager
def usage_scope(*, job=None, document=None, sprint=None, stage=None):
    """Attribute AI calls inside this block. Nested scopes inherit and override
    the outer one's fields (e.g. the pipeline sets the job once, then the stage
    per step)."""
    current = dict(_scope.get() or {})
    if job is not None:
        current.update(job=job, document=document or job.document, sprint=sprint or job.sprint)
    if document is not None:
        current['document'] = document
    if sprint is not None:
        current['sprint'] = sprint
    if stage is not None:
        current['stage'] = stage
    token = _scope.set(current)
    try:
        yield
    finally:
        _scope.reset(token)


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _save(*, provider, model, input_tokens, output_tokens, cache_read_tokens=0, cache_write_tokens=0,
          reasoning_tokens=0, duration_ms=0):
    scope = _scope.get()
    if not scope:
        return None
    try:
        from .models import AIUsage
        from .pricing import cost_usd

        sprint = scope.get('sprint')
        return AIUsage.objects.create(
            institution_id=getattr(sprint, 'institution_id', None),
            sprint=sprint,
            document=scope.get('document'),
            extraction_job=scope.get('job'),
            stage=scope.get('stage') or AIUsage.Stage.OTHER,
            provider=provider,
            model=model or '',
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            duration_ms=max(0, int(duration_ms)),
            cost_usd=cost_usd(
                model, input_tokens=input_tokens, output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens,
            ),
        )
    except Exception as exc:  # never let bookkeeping fail an extraction
        logger.error('ai_usage.record_failed model=%s error=%s', model, exc)
        return None


def record_openai_usage(response, *, provider, model, duration_ms=0):
    """OpenAI / OpenAI-compatible chat completion: `usage.prompt_tokens`
    includes cached tokens (reported in prompt_tokens_details.cached_tokens);
    `completion_tokens` includes reasoning tokens."""
    usage = getattr(response, 'usage', None)
    if usage is None:
        return None
    prompt = _int(getattr(usage, 'prompt_tokens', 0))
    cached = _int(getattr(getattr(usage, 'prompt_tokens_details', None), 'cached_tokens', 0))
    return _save(
        provider=provider,
        model=model,  # as configured -- the price-table key (a router's combo name, not the routed model)
        input_tokens=max(0, prompt - cached),
        output_tokens=_int(getattr(usage, 'completion_tokens', 0)),
        cache_read_tokens=cached,
        reasoning_tokens=_int(getattr(getattr(usage, 'completion_tokens_details', None), 'reasoning_tokens', 0)),
        duration_ms=duration_ms,
    )


def record_anthropic_usage(response, *, model, duration_ms=0):
    """Claude Messages API: `input_tokens` excludes cache reads/writes;
    `output_tokens` includes thinking."""
    usage = getattr(response, 'usage', None)
    if usage is None:
        return None
    return _save(
        provider='anthropic',
        model=model,
        input_tokens=_int(getattr(usage, 'input_tokens', 0)),
        output_tokens=_int(getattr(usage, 'output_tokens', 0)),
        cache_read_tokens=_int(getattr(usage, 'cache_read_input_tokens', 0)),
        cache_write_tokens=_int(getattr(usage, 'cache_creation_input_tokens', 0)),
        duration_ms=duration_ms,
    )


def money(value):
    """A summed cost as an exact 6-decimal string (databases differ in how
    many decimals a SUM returns), or None."""
    if value is None:
        return None
    from decimal import Decimal
    return str(Decimal(value).quantize(Decimal('0.000001')))


_SUM_FIELDS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'reasoning_tokens')


def summarize_usage(queryset, *, top_documents=10):
    """Totals for a set of AIUsage rows, plus breakdowns by stage, by model and
    the costliest documents. Costs are strings (exact decimals); `cost_usd` is
    the sum of priced calls only, and `unpriced_calls` / `unpriced_models` show
    what's missing a price."""
    from django.db.models import Count, F, Max, Min, Q, Sum

    sums = {f: Sum(f) for f in _SUM_FIELDS}

    def _row(values):
        out = {f: values.get(f) or 0 for f in _SUM_FIELDS}
        out['total_tokens'] = sum(out[f] for f in _SUM_FIELDS if f != 'reasoning_tokens')
        out['calls'] = values.get('calls') or 0
        out['cost_usd'] = money(values.get('cost')) or '0.000000'
        return out

    totals = queryset.aggregate(
        calls=Sum('request_count'), cost=Sum('cost_usd'), first_call=Min('created_at'), last_call=Max('created_at'),
        unpriced_calls=Sum('request_count', filter=Q(cost_usd__isnull=True)),
        imported_calls=Sum('request_count', filter=Q(source='imported')),
        estimated_calls=Sum('request_count', filter=Q(source='estimated')), **sums,
    )
    summary = _row(totals)
    summary.update(
        first_call=totals['first_call'],
        last_call=totals['last_call'],
        unpriced_calls=totals['unpriced_calls'] or 0,
        # Non-exact figures: from a dashboard import / an estimate (see AIUsage.Source).
        imported_calls=totals['imported_calls'] or 0,
        estimated_calls=totals['estimated_calls'] or 0,
        notes=sorted(set(queryset.exclude(note='').values_list('note', flat=True))),
        unpriced_models=sorted(set(
            queryset.filter(cost_usd__isnull=True).values_list('model', flat=True)
        )),
        documents=queryset.exclude(document=None).values('document').distinct().count(),
    )

    def _group(field):
        rows = queryset.values(field).annotate(calls=Sum('request_count'), cost=Sum('cost_usd'), **sums).order_by(field)
        return [{field: r[field], **_row(r)} for r in rows]

    summary['by_stage'] = _group('stage')
    summary['by_model'] = _group('model')
    top = (
        queryset.exclude(document=None)
        .values('document', 'document__original_filename')
        .annotate(calls=Sum('request_count'), cost=Sum('cost_usd'), **sums)
        .order_by(F('cost').desc(nulls_last=True), '-output_tokens')[:top_documents]
    )
    summary['top_documents'] = [
        {'document_id': r['document'], 'filename': r['document__original_filename'], **_row(r)} for r in top
    ]
    return summary


def billing_rows(queryset):
    """Usage per institution x sprint x month -- the billing view shared by the
    admin "AI Usage & Billing" page and `manage.py ai_usage_report`."""
    from django.db.models import Count, Q, Sum
    from django.db.models.functions import TruncMonth

    rows = (
        queryset.annotate(month=TruncMonth('created_at'))
        .values('institution_id', 'institution__name', 'sprint_id', 'sprint__name', 'sprint__sprint_code', 'month')
        .annotate(
            calls=Sum('request_count'),
            documents=Count('document', distinct=True),
            input_tokens=Sum('input_tokens'),
            output_tokens=Sum('output_tokens'),
            cache_read_tokens=Sum('cache_read_tokens'),
            cache_write_tokens=Sum('cache_write_tokens'),
            cost=Sum('cost_usd'),
            unpriced_calls=Sum('request_count', filter=Q(cost_usd__isnull=True)),
            imported_calls=Sum('request_count', filter=Q(source='imported')),
            estimated_calls=Sum('request_count', filter=Q(source='estimated')),
        )
        .order_by('institution__name', 'month', 'sprint__sprint_code')
    )
    return [{
        'institution_id': str(r['institution_id']) if r['institution_id'] else None,
        'institution': r['institution__name'] or '(none)',
        'sprint_id': str(r['sprint_id']) if r['sprint_id'] else None,
        'sprint': r['sprint__name'] or r['sprint__sprint_code'] or (str(r['sprint_id'])[:8] if r['sprint_id'] else '(none)'),
        'month': r['month'].strftime('%Y-%m') if r['month'] else '',
        'documents': r['documents'],
        'calls': r['calls'],
        'input_tokens': (r['input_tokens'] or 0) + (r['cache_read_tokens'] or 0) + (r['cache_write_tokens'] or 0),
        'output_tokens': r['output_tokens'] or 0,
        'cost_usd': money(r['cost']) or '0.000000',
        'unpriced_calls': r['unpriced_calls'] or 0,
        'imported_calls': r['imported_calls'] or 0,
        'estimated_calls': r['estimated_calls'] or 0,
    } for r in rows]
