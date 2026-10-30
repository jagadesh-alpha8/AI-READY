"""Read-only: find numeric facts whose number is not what their cited page prints (verification/numeric.py).

    python manage.py numeric_fact_audit                       # every sprint
    python manage.py numeric_fact_audit --sprint <uuid>
    python manage.py numeric_fact_audit --status decimal_missing --csv out.csv

Lists each suspicious fact with its value, what the page prints, the page and the fact's review status. Nothing
is changed: no fact, no review, no verification record. Repairing a record is a separate, reviewed step (correct
it through Facts Review / a correction proposal, so the history shows who changed it and why).
"""
import csv
from collections import Counter

from django.core.management.base import BaseCommand

from apps.facts.models import ExtractedFact
from apps.facts.verification import engine, numeric


class Command(BaseCommand):
    help = 'Read-only audit of numeric facts against their cited page text.'

    def add_arguments(self, parser):
        parser.add_argument('--sprint', help='Only this sprint (uuid).')
        parser.add_argument('--status', action='append',
                            help='Only these results (decimal_missing, scale_mismatch, other_page, not_found, '
                                 'ambiguous, page_unavailable). Default: all but found.')
        parser.add_argument('--csv', help='Also write the rows to this CSV file.')

    def handle(self, *args, **options):
        facts = (ExtractedFact.objects.filter(data_type__in=numeric.NUMERIC_TYPES)
                 .exclude(status=ExtractedFact.Status.REJECTED).select_related('source_document', 'document'))
        if options['sprint']:
            facts = facts.filter(sprint_id=options['sprint'])
        wanted = set(options['status'] or ['decimal_missing', 'scale_mismatch', 'other_page', 'not_found',
                                           'ambiguous', 'page_unavailable'])
        counts, rows = Counter(), []
        for fact in facts.iterator(chunk_size=200):
            result = engine.verify_snapshot(engine.Snapshot.of(fact)).numeric  # pure: nothing is saved
            counts[result['status']] += 1
            if result['status'] in wanted:
                rows.append([str(fact.sprint_id), str(fact.id), fact.field_key, fact.value, result.get('page_shows', ''),
                             fact.source_page, fact.status, result['status'], result['detail']])
        for status, n in sorted(counts.items()):
            self.stdout.write(f'{status}: {n}')
        for row in rows[:50]:
            self.stdout.write(f'  {row[2]} = {row[3]!r} (page {row[5]}, {row[6]}): {row[8]}')
        if options['csv']:
            with open(options['csv'], 'w', newline='', encoding='utf-8') as handle:
                writer = csv.writer(handle)
                writer.writerow(['sprint', 'fact', 'field_key', 'value', 'page_shows', 'page', 'fact_status',
                                 'result', 'detail'])
                writer.writerows(rows)
            self.stdout.write(f'Wrote {len(rows)} row(s) to {options["csv"]}.')
        self.stdout.write('Read-only: nothing was changed.')
