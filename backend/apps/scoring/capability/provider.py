"""Meter the existing clients at their SDK boundary, including corrective requests.

SDK retries are disabled for this per-run client only. Every actual request reserves
its full conservative configured-price envelope BEFORE sending. Failed/ambiguous calls
keep the reservation. No secret URLs, keys or provider exception text enter run history.
The ceiling is an application estimate at configured rates, not a provider billing guarantee.
"""
import json
import time
from decimal import Decimal, ROUND_UP
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.extraction.exceptions import RecoverableExtractionError, ProviderQuotaExhausted
from apps.extraction.pricing import prices_for
from apps.scoring.models import CapabilityExecution, CapabilityRunEvent
from .execution import BudgetExceeded, ExecutionStopped
from .storage import digest


class UnpricedModel(Exception):
    pass


class UsageUnavailable(Exception):
    pass


class MeteredService:
    def __init__(self, service, execution):
        from apps.extraction.services.openai_client import OpenAIExtractionService
        from apps.extraction.services.anthropic_client import AnthropicExtractionService
        if not isinstance(service, (OpenAIExtractionService, AnthropicExtractionService)):
            raise TypeError('Unsupported capability provider client.')
        self.service = service
        self.run_id = execution.run_id
        self.policy = execution.run.inputs['execution_policy']
        self.limit_breach = False
        self.model = service.model
        self.provider = ('anthropic' if isinstance(service, AnthropicExtractionService)
                         else 'openai_compatible' if service.base_url else 'openai')
        # Fresh client instance per execution; no mutation of the extraction pipeline's clients.
        client = service._client.with_options(max_retries=0, timeout=self.policy['timeout_seconds'])
        self.prices = prices_for(self.model)
        if self.prices is None or not {'input', 'output'} <= set(self.prices):
            raise UnpricedModel()
        self.rates = {key: Decimal(str(value)) for key, value in self.prices.items()}
        if any(not v.is_finite() or v < 0 for v in self.rates.values()):
            raise UnpricedModel()
        if self.provider == 'anthropic':
            sender = client.messages.create
            service._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: self.send(sender, kw)))
        else:
            sender = client.chat.completions.create
            service._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
                create=lambda **kw: self.send(sender, kw))))

    def extract_structured_data(self, **kwargs):
        # One transient retry per indicator; format/JSON fallbacks inside the existing
        # clients also pass through send(), so every extra request consumes the budget.
        for attempt in range(2):
            try:
                result = self.service.extract_structured_data(**kwargs, timeout=self.policy['timeout_seconds'])
                if self.limit_breach:
                    raise BudgetExceeded()
                return result
            except ProviderQuotaExhausted:
                raise
            except RecoverableExtractionError as exc:
                if attempt or (exc.retry_after or 0) > 2:
                    raise
                time.sleep(max(0.1, min(2, exc.retry_after or 0.1)))

    def envelope(self, kwargs):
        # UTF-8 bytes bound ordinary byte-level tokenizer content; explicit allowance
        # covers protocol/tool framing. Exotic router transforms/fees are outside this estimate.
        input_bound = len(json.dumps(kwargs, ensure_ascii=False, default=str).encode()) + 4096
        rate_in = self.rates['input']
        max_in = max(rate_in, self.rates.get('cache_read', rate_in * Decimal('.1')),
                     self.rates.get('cache_write', rate_in * Decimal('1.25')))
        amount = (input_bound * max_in + self.policy['output_tokens'] * self.rates['output']) / Decimal(1000000)
        return input_bound, amount.quantize(Decimal('.000001'), rounding=ROUND_UP)

    @transaction.atomic
    def reserve(self, kwargs):
        execution = CapabilityExecution.objects.select_for_update().get(run_id=self.run_id)
        if self.limit_breach:
            raise BudgetExceeded()
        if execution.status != 'running' or not settings.CAPABILITY_ASSESSMENT_ENABLED:
            raise ExecutionStopped()
        bound, amount = self.envelope(kwargs)
        if (execution.requests_reserved >= self.policy['max_http_calls']
                or execution.usd_reserved + amount > Decimal(self.policy['max_cost_usd'])):
            raise BudgetExceeded()
        execution.requests_reserved += 1
        execution.usd_reserved += amount
        execution.heartbeat_at = timezone.now()
        execution.save(update_fields=['requests_reserved', 'usd_reserved', 'heartbeat_at'])
        event = CapabilityRunEvent.objects.create(run_id=self.run_id, state='partial', payload={
            'kind': 'request_reserved', 'request_number': execution.requests_reserved,
            'provider': self.provider, 'configured_model': self.model, 'input_token_bound': bound,
            'reserved_usd': str(amount), 'request_hash': digest(kwargs),
            'configured_prices': {k: str(v) for k, v in self.rates.items()},
            'settings': {k: kwargs[k] for k in ('temperature', 'seed', 'max_tokens', 'max_completion_tokens', 'timeout')
                         if k in kwargs}, 'schema_hash': digest(kwargs.get('response_format', kwargs.get('tools', [])))})
        return event.pk

    def send(self, sender, kwargs):
        kwargs['max_tokens'] = self.policy['output_tokens']
        kwargs['timeout'] = self.policy['timeout_seconds']
        event_id = self.reserve(kwargs)
        started = time.monotonic()
        try:
            response = sender(**kwargs)
        except Exception:
            self.record(event_id, {'outcome': 'failed_or_unknown_billing', 'usage_known': False,
                                   'duration_ms': round((time.monotonic() - started) * 1000)})
            raise
        usage = getattr(response, 'usage', None)
        token_fields = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens') if (
            self.provider == 'anthropic') else ('prompt_tokens', 'completion_tokens')
        usage_known = usage is not None and all(type(getattr(usage, k, None)) is int for k in token_fields[:2])
        counts = {k: getattr(usage, k, 0) or 0 for k in token_fields} if usage_known else {}
        if self.provider != 'anthropic' and usage_known:
            counts['cached_tokens'] = getattr(getattr(usage, 'prompt_tokens_details', None), 'cached_tokens', 0) or 0
        if usage_known:
            bound, _ = self.envelope(kwargs)
            inputs = counts.get('prompt_tokens', sum(counts.get(k, 0) for k in (
                'input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')))
            outputs = counts.get('completion_tokens', counts.get('output_tokens', 0))
            self.limit_breach = inputs > bound or outputs > self.policy['output_tokens']
        self.record(event_id, {'outcome': 'response_received', 'usage_known': usage_known,
            'actual_model': getattr(response, 'model', None), 'tokens': counts,
            'duration_ms': round((time.monotonic() - started) * 1000)})
        if not usage_known:
            # Reservation retained; do not silently treat missing telemetry as zero cost.
            raise UsageUnavailable()
        return response

    @transaction.atomic
    def record(self, reservation_id, data):
        # A response received after cancellation still belongs in billing history, but
        # it cannot change the terminal assessment state or publish results.
        execution = CapabilityExecution.objects.select_for_update().get(run_id=self.run_id)
        CapabilityRunEvent.objects.create(run_id=self.run_id, state=execution.status,
            payload={'kind': 'request_outcome', 'reservation_event_id': reservation_id, **data})

    def metadata(self):
        events = CapabilityRunEvent.objects.filter(run_id=self.run_id)
        return {'provider': self.provider, 'model': self.model, 'settings': self.policy,
                'configured_prices': {k: str(v) for k, v in self.rates.items()},
                'calls': [e.payload for e in events if e.payload.get('kind') in {'request_reserved', 'request_outcome'}]}
