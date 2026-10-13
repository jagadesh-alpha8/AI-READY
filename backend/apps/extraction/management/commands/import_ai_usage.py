"""Add AI usage for a sprint from a provider / router dashboard (e.g. 9Router)
-- for usage from before automatic recording existed.

    python manage.py import_ai_usage --sprint <uuid> --requests 711 \\
        --input-tokens 1369687 --output-tokens 227699 --cost 3.11 \\
        --model my-combo --date 2026-10-07 \\
        --note "9Router dashboard, 7-day total as of 2026-10-08"

Stored as ONE AIUsage row with source=imported, attributed to the sprint as a
whole (a dashboard total can't be split per document). Shown as "imported"
on the usage pages and in `ai_usage_report`. Refuses to add a second import
with the same note for the same sprint, so running it twice is safe.
Use --dry-run to see what would be stored.
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.extraction.models import AIUsage
from apps.extraction.pricing import cost_usd
from apps.sprints.models import Sprint


class Command(BaseCommand):
    help = 'Import AI token usage for a sprint from a provider/router dashboard.'

    def add_arguments(self, parser):
        parser.add_argument('--sprint', required=True, help='Sprint UUID.')
        parser.add_argument('--requests', type=int, required=True, help='Number of API requests.')
        parser.add_argument('--input-tokens', type=int, required=True, help='Uncached input tokens.')
        parser.add_argument('--output-tokens', type=int, required=True)
        parser.add_argument('--cached-tokens', type=int, default=0, help='Cached (cache-read) input tokens.')
        parser.add_argument('--cost', help='Cost in USD as shown on the dashboard. Omit to use the price table.')
        parser.add_argument('--model', default='', help='Model name (e.g. my-combo).')
        parser.add_argument('--provider', default='openai_compatible')
        parser.add_argument('--date', help='Date the usage happened (YYYY-MM-DD); decides the billing month.')
        parser.add_argument('--note', required=True, help='Where the figures came from and what they cover.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **o):
        try:
            sprint = Sprint.objects.select_related('institution').get(id=o['sprint'])
        except (Sprint.DoesNotExist, ValueError):
            raise CommandError(f"Sprint {o['sprint']} not found.")
        for key in ('requests', 'input_tokens', 'output_tokens', 'cached_tokens'):
            if o[key] < 0:
                raise CommandError(f'--{key.replace("_", "-")} cannot be negative.')

        if o['cost'] is not None:
            try:
                cost = Decimal(o['cost']).quantize(Decimal('0.000001'))
            except InvalidOperation:
                raise CommandError('--cost must be a number, e.g. 3.11')
        else:
            cost = cost_usd(o['model'], input_tokens=o['input_tokens'], output_tokens=o['output_tokens'],
                            cache_read_tokens=o['cached_tokens'])

        when = timezone.now()
        if o['date']:
            try:
                day = datetime.date.fromisoformat(o['date'])
            except ValueError:
                raise CommandError('--date must be like 2026-10-07.')
            when = timezone.make_aware(datetime.datetime.combine(day, datetime.time(12, 0)))

        if AIUsage.objects.filter(sprint=sprint, source=AIUsage.Source.IMPORTED, note=o['note']).exists():
            raise CommandError('An import with this exact note already exists for this sprint -- not adding it twice.')

        summary = (
            f"{sprint} ({sprint.institution.name}): {o['requests']} requests, "
            f"{o['input_tokens']:,} input + {o['cached_tokens']:,} cached + {o['output_tokens']:,} output tokens, "
            f"cost {'$' + str(cost) if cost is not None else 'not priced'}, dated {when:%Y-%m-%d}"
        )
        if o['dry_run']:
            self.stdout.write(f'DRY RUN -- would import: {summary}')
            return

        row = AIUsage.objects.create(
            institution=sprint.institution, sprint=sprint, stage=AIUsage.Stage.OTHER,
            source=AIUsage.Source.IMPORTED, request_count=o['requests'],
            provider=o['provider'], model=o['model'],
            input_tokens=o['input_tokens'], output_tokens=o['output_tokens'],
            cache_read_tokens=o['cached_tokens'], cost_usd=cost, note=o['note'],
        )
        AIUsage.objects.filter(id=row.id).update(created_at=when)  # billing month = when it happened
        self.stdout.write(self.style.SUCCESS(f'Imported: {summary}'))
