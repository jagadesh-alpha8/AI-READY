"""AI usage and cost report for billing -- per institution, sprint and month.

    python manage.py ai_usage_report
    python manage.py ai_usage_report --since 2026-10-01 --until 2026-10-31
    python manage.py ai_usage_report --institution <uuid> --csv > october.csv
    python manage.py ai_usage_report --sprint <uuid>

Same numbers as the admin "AI Usage & Billing" page (both use
apps.extraction.usage.billing_rows). Costs are the sum of priced calls; calls
whose model has no configured price (see apps.extraction.pricing /
AI_PRICING_JSON) are counted under "unpriced_calls". "imported_calls" /
"estimated_calls" are requests whose figures came from a dashboard import
(manage.py import_ai_usage) or an estimate, not exact per-call recording.
"""
import csv
import datetime
import sys
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.extraction.models import AIUsage
from apps.extraction.usage import billing_rows

COLUMNS = ['institution', 'sprint', 'month', 'documents', 'calls', 'input_tokens', 'output_tokens',
           'cost_usd', 'unpriced_calls', 'imported_calls', 'estimated_calls']


class Command(BaseCommand):
    help = 'AI tokens and cost per institution, sprint and month (for billing).'

    def add_arguments(self, parser):
        parser.add_argument('--institution', help='Only this institution (UUID).')
        parser.add_argument('--sprint', help='Only this sprint (UUID).')
        parser.add_argument('--since', help='From this date, inclusive (YYYY-MM-DD).')
        parser.add_argument('--until', help='Up to this date, inclusive (YYYY-MM-DD).')
        parser.add_argument('--csv', action='store_true', help='Output CSV instead of a table.')

    def handle(self, *args, **options):
        queryset = AIUsage.objects.all()
        if options['institution']:
            queryset = queryset.filter(institution_id=options['institution'])
        if options['sprint']:
            queryset = queryset.filter(sprint_id=options['sprint'])
        for key, lookup in (('since', 'created_at__date__gte'), ('until', 'created_at__date__lte')):
            if options[key]:
                try:
                    queryset = queryset.filter(**{lookup: datetime.date.fromisoformat(options[key])})
                except ValueError:
                    raise CommandError(f'--{key} must be a date like 2026-10-31.')

        rows = billing_rows(queryset)
        table = [[row[c] for c in COLUMNS] for row in rows]

        if options['csv']:
            writer = csv.writer(sys.stdout)
            writer.writerow(COLUMNS)
            writer.writerows(table)
            return
        if not table:
            self.stdout.write('No AI usage recorded for these filters.')
            return
        widths = [max(len(str(x)) for x in col) for col in zip(COLUMNS, *table)]
        line = lambda cells: '  '.join(str(c).ljust(w) for c, w in zip(cells, widths))  # noqa: E731
        self.stdout.write(line(COLUMNS))
        self.stdout.write(line(['-' * w for w in widths]))
        for row in table:
            self.stdout.write(line(row))
        total_cost = sum((Decimal(r['cost_usd']) for r in rows), Decimal(0))
        self.stdout.write(
            f"\nTOTAL  calls={sum(r['calls'] for r in rows)}  "
            f"input={sum(r['input_tokens'] for r in rows):,}  "
            f"output={sum(r['output_tokens'] for r in rows):,}  cost=${total_cost:.4f}"
        )
