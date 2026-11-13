"""Show or raise one provisional run's second-layer budget (shared by all its background jobs; second_layer_jobs.py).

    python manage.py layer2_budget RUN_ID                               # limits, what is reserved, the jobs so far
    python manage.py layer2_budget RUN_ID --max-calls 300 --max-cost 12 # raise the limits (never below what is reserved)

The budget is created when the run's first job starts. Raising it is a consultant's decision and is recorded on the
run's newest job's ledger.
"""
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.scoring.capability.execution import AssessmentDisabled
from apps.scoring.capability.second_layer_jobs import ensure_budget
from apps.scoring.models import CapabilityRun, SecondLayerBudget, SecondLayerEvent, SecondLayerJob


class Command(BaseCommand):
    help = "Show or raise a run's second-layer budget."

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--max-calls', type=int)
        parser.add_argument('--max-cost')

    def handle(self, *args, **options):
        run = CapabilityRun.objects.filter(pk=options['run_id']).first()
        if run is None:
            raise CommandError('Run not found.')
        if options['max_calls'] is not None or options['max_cost'] is not None:
            try:
                cost = Decimal(options['max_cost']) if options['max_cost'] is not None else None
            except InvalidOperation:
                raise CommandError('--max-cost must be a number of US dollars.')
            with transaction.atomic():
                try:
                    ensure_budget(run)
                except AssessmentDisabled as exc:
                    raise CommandError(str(exc.detail))
                budget = SecondLayerBudget.objects.select_for_update().get(run=run)
                before = {'max_http_calls': budget.max_http_calls, 'max_cost_usd': str(budget.max_cost_usd)}
                if options['max_calls'] is not None:
                    if not budget.requests_reserved <= options['max_calls'] <= 1000:
                        raise CommandError(f'--max-calls must be between {budget.requests_reserved} (already '
                                           'reserved) and 1000.')
                    budget.max_http_calls = options['max_calls']
                if cost is not None:
                    if not cost.is_finite() or not budget.usd_reserved <= cost <= 100 or cost <= 0:
                        raise CommandError(f'--max-cost must be between {budget.usd_reserved} (already reserved) '
                                           'and 100.')
                    budget.max_cost_usd = cost
                budget.save(update_fields=['max_http_calls', 'max_cost_usd'])
                job = SecondLayerJob.objects.filter(run=run).first()
                if job is not None:
                    SecondLayerEvent.objects.create(job=job, payload={
                        'kind': 'budget_changed', 'before': before,
                        'after': {'max_http_calls': budget.max_http_calls, 'max_cost_usd': str(budget.max_cost_usd)}})
        budget = SecondLayerBudget.objects.filter(run=run).first()
        if budget is None:
            self.stdout.write('No second-layer job has started for this run yet; no budget is frozen.')
            return
        self.stdout.write(f'Requests: {budget.requests_reserved} of {budget.max_http_calls}. '
                          f'Cost reserved: ${budget.usd_reserved} of ${budget.max_cost_usd}.')
        for job in SecondLayerJob.objects.filter(run=run):
            self.stdout.write(f'  {job.created_at:%Y-%m-%d %H:%M} {job.operation:<9} {job.status:<9} '
                              f'{job.requests_reserved} requests, ${job.usd_reserved} {job.error_code}')
