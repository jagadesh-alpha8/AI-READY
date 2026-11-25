"""Meter the existing clients at their SDK boundary, including corrective requests.

SDK retries are disabled for this per-run client only. Every actual request reserves
its full conservative configured-price envelope BEFORE sending. Failed/ambiguous calls
keep the reservation. No secret URLs, keys or provider exception text enter run history.
The ceiling is an application estimate at configured rates, not a provider billing guarantee.
"""
import json
import threading
import time
from decimal import Decimal, ROUND_UP
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.extraction.exceptions import RecoverableExtractionError, ProviderQuotaExhausted
from apps.extraction.pricing import prices_for, positive_token_prices
from apps.extraction.usage import openai_token_counts
from apps.scoring.models import CapabilityExecution, CapabilityRunEvent
from .execution import BudgetExceeded, ExecutionStopped, ExecutionDeadlineExceeded, InputBudgetExceeded
from .storage import digest



#: Waits before the 2nd, 3rd and 4th attempt of one request when the provider is rate limiting, overloaded or
#: unreachable and gives no Retry-After (25 Nov audit, finding 1: one 429 or "overloaded" used to score a whole key
#: indicator as unknown). A provider's own Retry-After is followed up to MAX_RETRY_WAIT seconds. A timeout is retried
#: once: it has already used the whole timeout. Every attempt is metered and counts toward the run's caps.
RETRY_WAITS = (5, 20, 45)
MAX_RETRY_WAIT = 60


def retry_wait(exc, attempt):
    """Seconds to wait before retrying after `exc` on attempt `attempt` (0-based), or None: give up."""
    if getattr(exc, 'kind', None) == 'timeout':
        return 0.1 if attempt == 0 else None
    if attempt >= len(RETRY_WAITS):
        return None
    asked = exc.retry_after or 0
    if asked > MAX_RETRY_WAIT:
        return None
    return max(0.1, asked) if asked else RETRY_WAITS[attempt]

class UnpricedModel(Exception):
    pass


class UsageUnavailable(Exception):
    pass


class MeteredService:
    execution_model = CapabilityExecution
    #: The current call's kind (judging or writing), per thread: indicators run concurrently, and each thread sets it
    #: at the start of its own call (extract_structured_data) before any request it makes.
    _call = threading.local()
    execution_key = 'run_id'
    #: Give back what a call's reservation held beyond its billed tokens once the response arrives (settle()). Off
    #: for the assessment, whose ledger reports the reservation; the second layer's jobs settle (SecondLayerMeter).
    settles = False

    def enabled(self):
        return settings.CAPABILITY_ASSESSMENT_ENABLED

    def event(self, state, payload):
        return CapabilityRunEvent.objects.create(run_id=self.run_id, state=state, payload=payload)

    def events(self):
        return CapabilityRunEvent.objects.filter(run_id=self.run_id)

    def budget(self, execution):
        """The row whose counters the limits apply to: the execution itself, unless a subclass shares one budget
        between several executions (the second layer's jobs share their run's). Called with the execution locked;
        a shared row must be locked here too."""
        return execution

    def limits(self, budget):
        """(max requests, max USD) for the budget row: the frozen policy's, unless the row carries its own."""
        return self.policy['max_http_calls'], Decimal(self.policy['max_cost_usd'])

    def __init__(self, service, execution, *, execution_policy=None, ledger_id=None):
        from apps.extraction.services.openai_client import OpenAIExtractionService
        from apps.extraction.services.anthropic_client import AnthropicExtractionService
        if not isinstance(service, (OpenAIExtractionService, AnthropicExtractionService)):
            raise TypeError('Unsupported capability provider client.')
        self.service = service
        self.run_id = ledger_id if ledger_id is not None else execution.run_id
        self.policy = execution_policy if execution_policy is not None else execution.run.inputs['execution_policy']
        self.deadline = time.monotonic() + self.policy['max_duration_seconds']
        self.limit_breach = False
        self.answers = None   # set below when the frozen policy reuses stored answers (apps/stored_judgments)
        self._reserved = {}   # reservation event id -> USD reserved, until the call is settled
        self.model = service.model
        from apps.extraction.services.provider_features import direct_gemini
        self.provider = ('gemini' if direct_gemini(getattr(service, 'base_url', None)) else 'anthropic' if isinstance(service, AnthropicExtractionService)
                         else 'openai_compatible' if service.base_url else 'openai')
        # Fresh client instance per execution; no mutation of the extraction pipeline's clients.
        client = service._client.with_options(max_retries=0, timeout=self.policy['timeout_seconds'])
        self.prices = prices_for(self.model)
        if self.prices is None or not {'input', 'output'} <= set(self.prices):
            raise UnpricedModel()
        if self.provider == 'gemini' and not positive_token_prices(self.model):
            raise UnpricedModel()
        self.rates = {key: Decimal(str(value)) for key, value in self.prices.items() if key != 'long_context'}
        long = self.prices.get('long_context') or {}
        # Prompts over the threshold pay higher rates for the whole request (Claude Haiku 5.5 over 100,000 tokens,
        # GPT-6 models over 272,000): reserved at those rates whenever the request could be that long.
        self.long_threshold = long.get('threshold')
        self.long_rates = {key: Decimal(str(value)) for key, value in long.items() if key != 'threshold'}
        if any(not v.is_finite() or v < 0 for v in [*self.rates.values(), *self.long_rates.values()]):
            raise UnpricedModel()
        if self.provider == 'anthropic':
            # Claude 5.5 models think by default, which a forced tool call can't be combined with: ask for JSON
            # output instead, at the run's frozen effort (None = the model's default).
            service.json_output = True
            service.effort = None   # set per call in shape(), from the call's tier
            sender = client.messages.create
            service._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: self.send(sender, kw)))
        else:
            sender = client.chat.completions.create
            service._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
                create=lambda **kw: self.send(sender, kw))))
        if self.reuses_answers and self.policy.get('stage') == 'assessment' and self.policy.get('stored_judgments'):
            from apps.stored_judgments.store import RunAnswers
            self.answers = RunAnswers(self.run_id)

    #: Stage 1 may reuse stored answers when its frozen policy says so; the second layer never does.
    reuses_answers = True

    def extract_structured_data(self, **kwargs):
        # One transient retry per indicator; format/JSON fallbacks inside the existing
        # clients also pass through send(), so every extra request consumes the budget.
        # The call's kind decides its effort (judging or writing); kept per thread, as indicators run concurrently.
        from .model_choice import tier
        self._call.tier = tier(kwargs.get('schema_name'))
        stored = None
        if self.answers is not None:
            from apps.stored_judgments.store import request_hash
            key = request_hash(provider=self.provider, model=self.model, policy=self.policy,
                               tier=self._call.tier, kwargs=kwargs)
            occurrence = self.answers.occurrence(key)
            row = self.answers.find(key, occurrence)
            if row is not None:
                self.remaining_time()
                from apps.extraction.usage import DB_WRITE_LOCK
                with DB_WRITE_LOCK:
                    self.event('partial', {'kind': 'stored_answer_reused', 'stage': self.policy['stage'],
                                           'request_hash': key, 'occurrence': occurrence,
                                           'schema_name': kwargs.get('schema_name'), 'answered_in_run': str(row.run_id)})
                return row.answer
            stored = (key, occurrence)
        for attempt in range(len(RETRY_WAITS) + 1):
            self.remaining_time()
            try:
                result = self.service.extract_structured_data(**kwargs, timeout=self.policy['timeout_seconds'])
                if self.limit_breach:
                    raise BudgetExceeded()
                if stored is not None:
                    self.answers.keep(*stored, model=self.model, schema_name=kwargs.get('schema_name'), answer=result)
                return result
            except ProviderQuotaExhausted:
                raise
            except RecoverableExtractionError as exc:
                wait = retry_wait(exc, attempt)
                if wait is None or wait >= self.remaining_time():
                    raise
                time.sleep(wait)

    def envelope(self, kwargs):
        # UTF-8 bytes bound ordinary byte-level tokenizer content; explicit allowance
        # covers protocol/tool framing. Exotic router transforms/fees are outside this estimate.
        input_bound = len(json.dumps(kwargs, ensure_ascii=False, default=str).encode()) + 4096
        rates = self.rates
        if self.long_threshold and input_bound > self.long_threshold:
            rates = {**self.rates, **self.long_rates}
        rate_in = rates['input']
        max_in = max(rate_in, rates.get('cache_read', rate_in * Decimal('.1')),
                     rates.get('cache_write', rate_in * Decimal('1.25')))
        amount = (input_bound * max_in + self.policy['output_tokens'] * rates['output']) / Decimal(1000000)
        return input_bound, amount.quantize(Decimal('.000001'), rounding=ROUND_UP)

    def reserve(self, kwargs):
        from apps.extraction.usage import DB_WRITE_LOCK
        with DB_WRITE_LOCK:  # outside the transaction: one writer at a time when indicators run concurrently
            return self._reserve(kwargs)

    @transaction.atomic
    def _reserve(self, kwargs):
        execution = self.execution_model.objects.select_for_update().get(**{self.execution_key: self.run_id})
        if self.limit_breach:
            raise BudgetExceeded()
        if execution.status != 'running' or not self.enabled():
            raise ExecutionStopped()
        bound, amount = self.envelope(kwargs)
        budget = self.budget(execution)
        max_calls, max_cost = self.limits(budget)
        if budget.requests_reserved >= max_calls or budget.usd_reserved + amount > max_cost:
            raise BudgetExceeded()
        rows = [execution] if budget is execution else [execution, budget]
        for row in rows:
            row.requests_reserved += 1
            row.usd_reserved += amount
            row.heartbeat_at = timezone.now()
            row.save(update_fields=['requests_reserved', 'usd_reserved', 'heartbeat_at'])
        event = self.event('partial', {
            'kind': 'request_reserved', 'stage': self.policy['stage'], 'request_number': execution.requests_reserved,
            'provider': self.provider, 'configured_model': self.model, 'input_token_bound': bound,
            'request_utf8_bytes': len(json.dumps(kwargs, ensure_ascii=False, default=str).encode()),
            'schema_utf8_bytes': len(json.dumps(kwargs.get('response_format', kwargs.get('tools', (kwargs.get('output_config') or {}).get('format', []))),
                                                ensure_ascii=False).encode()),
            'reserved_usd': str(amount), 'request_hash': digest(kwargs),
            'configured_prices': self.configured_prices(),
            'settings': {**{k: kwargs[k] for k in ('temperature', 'seed', 'max_tokens', 'max_completion_tokens', 'timeout', 'reasoning_effort')
                         if k in kwargs}, **({'effort': kwargs['output_config']['effort']}
                                            if 'effort' in (kwargs.get('output_config') or {}) else {})},
            'schema_hash': digest(kwargs.get('response_format', kwargs.get('tools', (kwargs.get('output_config') or {}).get('format', []))))})
        self._reserved[event.pk] = amount
        return event.pk

    def remaining_time(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ExecutionDeadlineExceeded()
        return remaining

    def effort(self):
        """The frozen effort for the current call: the writing effort for writing and routing calls when one is set,
        else the judging effort (model_effort). None = the model's default."""
        if getattr(self._call, 'tier', 'judging') == 'writing' and self.policy.get('writing_effort'):
            return self.policy['writing_effort']
        return self.policy.get('model_effort')

    def shape(self, kwargs, timeout):
        """The provider-specific request settings, applied to `kwargs` in place (send() and the probe preflight)."""
        if self.provider == 'openai':
            # OpenAI's reasoning models take max_completion_tokens (reasoning included) and no sampling settings.
            kwargs.pop('max_tokens', None)
            kwargs['max_completion_tokens'] = self.policy['output_tokens']
            if self.effort():
                kwargs['reasoning_effort'] = self.effort()
                kwargs.pop('temperature', None)
                kwargs.pop('seed', None)
        else:
            kwargs['max_tokens'] = self.policy['output_tokens']
        if self.provider == 'anthropic' and 'output_config' in kwargs:
            config = {k: v for k, v in kwargs['output_config'].items() if k != 'effort'}
            kwargs['output_config'] = {**config, **({'effort': self.effort()} if self.effort() else {})}
        kwargs['timeout'] = timeout
        if self.provider == 'gemini':
            from apps.extraction.services.provider_features import gemini_thinking
            effort = self.policy['gemini_reasoning_effort']
            if getattr(self._call, 'tier', 'judging') == 'writing' and self.policy.get('writing_effort'):
                from .model_choice import GEMINI_EFFORT
                effort = GEMINI_EFFORT[self.policy['writing_effort']]
            if gemini_thinking(self.service.base_url, self.model) and effort != 'default':
                kwargs['reasoning_effort'] = effort
            else:
                kwargs.pop('reasoning_effort', None)
        return kwargs

    def send(self, sender, kwargs):
        self.shape(kwargs, min(self.policy['timeout_seconds'], self.remaining_time()))
        bound, _ = self.envelope(kwargs)
        if bound > self.policy['input_token_bound_limit']:
            self.record(None, {'kind': 'request_rejected', 'reason': 'input_budget_exceeded',
                'stage': self.policy['stage'], 'input_token_bound': bound,
                'input_token_bound_limit': self.policy['input_token_bound_limit'], 'usage_known': True})
            raise InputBudgetExceeded()
        event_id = self.reserve(kwargs)
        started = time.monotonic()
        try:
            response = sender(**kwargs)
        except Exception as exc:
            self.record(event_id, {'outcome': 'failed_or_unknown_billing', 'usage_known': False,
                                   'error_type': type(exc).__name__,
                                   'duration_ms': round((time.monotonic() - started) * 1000)})
            raise
        usage = getattr(response, 'usage', None)
        token_fields = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens') if (
            self.provider == 'anthropic') else ('prompt_tokens', 'completion_tokens')
        usage_known = usage is not None and all(type(getattr(usage, k, None)) is int for k in token_fields[:2])
        counts = {k: getattr(usage, k, 0) or 0 for k in token_fields} if usage_known else {}
        if self.provider != 'anthropic' and usage_known:
            counts, usage_known = openai_token_counts(usage, gemini=self.provider == 'gemini')
        if usage_known:
            bound, _ = self.envelope(kwargs)
            inputs = counts.get('prompt_tokens', sum(counts.get(k, 0) for k in (
                'input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')))
            outputs = counts.get('completion_tokens', counts.get('output_tokens', 0))
            self.limit_breach = inputs > bound or outputs > self.policy['output_tokens']
        choices = getattr(response, 'choices', None)
        finish = getattr(response, 'stop_reason', None) if self.provider == 'anthropic' else (getattr(choices[0], 'finish_reason', None) if choices else None)
        self.record(event_id, {'outcome': 'response_received', 'usage_known': usage_known,
            'finish_reason': finish if isinstance(finish, str) and len(finish) <= 64 else None,
            'actual_model': getattr(response, 'model', None), 'tokens': counts,
            'duration_ms': round((time.monotonic() - started) * 1000)})
        if not usage_known:
            # Reservation retained; do not silently treat missing telemetry as zero cost.
            raise UsageUnavailable()
        if self.settles:
            self.settle(event_id, counts)
        return response

    def actual_cost(self, counts):
        """USD for a response's billed tokens at the configured prices (the tier its prompt falls in), or None."""
        from apps.extraction.pricing import cost_usd
        if self.provider == 'anthropic':
            return cost_usd(self.model, input_tokens=counts.get('input_tokens', 0),
                            output_tokens=counts.get('output_tokens', 0),
                            cache_read_tokens=counts.get('cache_read_input_tokens', 0),
                            cache_write_tokens=counts.get('cache_creation_input_tokens', 0))
        cached = counts.get('cached_tokens', 0)
        return cost_usd(self.model, input_tokens=counts.get('prompt_tokens', 0) - cached,
                        output_tokens=counts.get('completion_tokens', 0), cache_read_tokens=cached)

    def settle(self, reservation_id, counts):
        """Release what the reservation held beyond the call's billed cost, from the execution and its budget.

        A reservation is the worst case (the whole input bound at the dearest input rate, plus the full output
        allowance), about $0.24 or more per call on Gemini; test 13's second layer reserved $14.34 for $3.98 of
        calls, so a cost cap on reservations stopped work at about a quarter of the money it named. Settled, the
        budget holds the billed cost of finished calls plus the reservations of calls still in flight. Calls whose
        usage is unknown, or that failed, keep their whole reservation."""
        from apps.extraction.usage import DB_WRITE_LOCK
        reserved = self._reserved.pop(reservation_id, None)
        actual = self.actual_cost(counts)
        if reserved is None or actual is None:
            return
        released = max(Decimal(0), reserved - min(actual, reserved))
        with DB_WRITE_LOCK:
            with transaction.atomic():
                execution = self.execution_model.objects.select_for_update().get(**{self.execution_key: self.run_id})
                budget = self.budget(execution)
                rows = [execution] if budget is execution else [execution, budget]
                for row in rows:
                    row.usd_reserved = max(Decimal(0), row.usd_reserved - released)
                    row.save(update_fields=['usd_reserved'])
                self.event(execution.status, {'kind': 'request_settled', 'reservation_event_id': reservation_id,
                                              'reserved_usd': str(reserved), 'actual_usd': str(actual),
                                              'released_usd': str(released)})

    def record(self, reservation_id, data):
        from apps.extraction.usage import DB_WRITE_LOCK
        with DB_WRITE_LOCK:
            return self._record(reservation_id, data)

    @transaction.atomic
    def _record(self, reservation_id, data):
        # A response received after cancellation still belongs in billing history, but
        # it cannot change the terminal assessment state or publish results.
        execution = self.execution_model.objects.select_for_update().get(**{self.execution_key: self.run_id})
        self.event(execution.status, {'kind': 'request_outcome', 'reservation_event_id': reservation_id, **data})

    def configured_prices(self):
        prices = {k: str(v) for k, v in self.rates.items()}
        if self.long_threshold:
            prices['long_context'] = {'threshold': self.long_threshold, **{k: str(v) for k, v in self.long_rates.items()}}
        return prices

    def metadata(self):
        events = self.events()
        return {'provider': self.provider, 'model': self.model, 'settings': self.policy,
                'configured_prices': self.configured_prices(),
                'calls': [e.payload for e in events if e.payload.get('kind') in {'request_reserved', 'request_outcome', 'request_rejected'}],
                **({'stored_judgments': {**self.answers.summary(), 'reused': [
                    e.payload for e in events if e.payload.get('kind') == 'stored_answer_reused']}}
                   if self.answers is not None else {})}
