"""Opt-in, bounded provider contract probe using synthetic evidence only."""
import json
from decimal import Decimal
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from apps.scoring.capability.engine import release, indicator_bounds, number, ENGINE_VERSION
from apps.scoring.capability.evaluation import evaluate, PROMPT_VERSION, RETRIEVAL_VERSION
from apps.scoring.capability.execution import policy, BudgetExceeded
from apps.scoring.capability.provider import MeteredService
from apps.extraction.services.ai_service import get_ai_service
from apps.extraction.services.router_pool import get_router_pool, use_lease


class ProbeMeter(MeteredService):
    """Use the production SDK-boundary limits without creating an assessment."""
    def __init__(self, service, probe_policy):
        self.requests, self.reserved, self.log = 0, Decimal(), []
        execution = SimpleNamespace(run_id='synthetic-probe', run=SimpleNamespace(inputs={'execution_policy': probe_policy}))
        super().__init__(service, execution)

    def reserve(self, kwargs):
        _, amount = self.envelope(kwargs)
        if self.requests >= self.policy['max_http_calls'] or self.reserved + amount > Decimal(self.policy['max_cost_usd']):
            raise BudgetExceeded()
        self.requests += 1
        self.reserved += amount
        return self.requests

    def record(self, reservation_id, data):
        self.log.append(data)


class Command(BaseCommand):
    help = 'Print the current scoring contract, or opt in to at most four metered SDK requests against synthetic evidence.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--live-provider', action='store_true', help='Uses configured model credits; does not create an institutional assessment.')

    def handle(self, *args, **options):
        contract = {'methodology': release()['version'], 'engine': ENGINE_VERSION,
                    'prompt': PROMPT_VERSION, 'retrieval': RETRIEVAL_VERSION}
        if not options.get('live_provider'):
            self.stdout.write(json.dumps({**contract, 'live_provider_called': False,
                                          'next_step': 'Use --live-provider on the deployed worker to test the actual configured provider with synthetic evidence.'}, indent=2))
            return
        pool = lease = meter = None
        try:
            probe_policy = policy()
            probe_policy.update(max_http_calls=min(4, probe_policy['max_http_calls']), max_cost_usd=str(min(Decimal(probe_policy['max_cost_usd']), Decimal('0.05'))))
            pool = get_router_pool()
            lease = pool.acquire() if pool else None
            with use_lease(lease):
                meter = ProbeMeter(get_ai_service(), probe_policy)
                rubric = release()
                indicator = next(i for i in rubric['indicators'] if i['code'] == 'AIQIF-C6.1')
                source = {'id': 'synthetic-page', 'text': (
                    'Institution name: Synthetic Institute\nReporting period: 2024-25\n'
                    'Learners and researchers at Synthetic Institute have access to institutional computers during 2024-25.\n'
                    'A technical suitability review for 2024-25 confirmed that none of the available resources supports any introductory AI workload.\n'
                    'No usage reviews or measured service outcomes are established by this synthetic test record.')}
                result = evaluate([source], service=meter, population='Learners and researchers at Synthetic Institute',
                                  reference_period='2024-25', rubric={'indicators': [indicator]}, max_calls=1, strict_errors=True)
                states = result['decisions']
                lower, upper = indicator_bounds(indicator, states)
                passed = states['AIQIF-C6.1.F1'] == 'met' and states['AIQIF-C6.1.F2'] == 'not_met'
                self.stdout.write(json.dumps({**contract, 'live_provider_called': True,
                    'passed': passed, 'requests': meter.requests, 'reserved_cost_usd': str(meter.reserved),
                    'indicator_bounds': {'lower': number(lower * 100 / 3), 'upper': number(upper * 100 / 3)},
                    'decisions': result['records'], 'actual_models': sorted({r.get('actual_model') for r in meter.log if r.get('actual_model')}),
                    'assessment_written': False}, indent=2))
                if not passed:
                    raise CommandError('Provider contract failed: inspect the synthetic decisions and validation reasons before running the full PDF assessment.')
        except CommandError:
            raise
        except Exception:
            # Provider/config exceptions may contain keys, URLs or raw responses.
            raise CommandError('Provider probe could not complete. Check worker configuration, model pricing, quota, telemetry and request limits; no assessment was created.') from None
        finally:
            if pool is not None and lease is not None:
                pool.release(lease)
