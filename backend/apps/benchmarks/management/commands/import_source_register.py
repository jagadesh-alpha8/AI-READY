"""Import the intern Source Register into the Source Library.

    python manage.py import_source_register "path/to/BenchMarking Structure.xlsx"            # dry run
    python manage.py import_source_register "path/to/BenchMarking Structure.xlsx" --commit   # save
    ... --report report.csv    # every row with its errors / warnings

A dry run reads, checks and writes everything inside a transaction, then
rolls it back -- the counts are exactly what --commit would do.
"""
import csv

from django.core.management.base import BaseCommand, CommandError

from ...services.register_import import apply_register, read_register


class Command(BaseCommand):
    help = 'Import the Source Register (.xlsx) into the Source Library (dry run unless --commit).'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--commit', action='store_true', help='Save the import (default: dry run).')
        parser.add_argument('--actor', default='', help='Who is importing (recorded in the audit log).')
        parser.add_argument('--report', help='Write a CSV of every row with its errors and warnings.')

    def handle(self, *args, path, commit, actor, report, **opts):
        try:
            rows = read_register(path)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f'Cannot read {path}: {exc}')
        actor = actor or 'import_source_register'
        summary = apply_register(rows, actor=actor, commit=commit, reason=f'Source Register import from {path}')

        for row in rows:
            for msg in row.errors:
                self.stdout.write(self.style.ERROR(f'  {row.row_id} {row.data["source_code"] or "-"}  SKIPPED: {msg}'))
        self.stdout.write(self.style.SUCCESS(('COMMITTED' if commit else 'DRY RUN (nothing saved)')
                                             + f': {summary.rows} rows, {summary.skipped} skipped, '
                                             f'{summary.flagged} imported with review flags'))
        self.stdout.write(f'  created: {summary.created}')
        self.stdout.write(f'  updated: {summary.updated}')
        for line in summary.locked:
            self.stdout.write(self.style.WARNING(f'  locked: {line}'))
        if report:
            with open(report, 'w', newline='', encoding='utf-8') as fh:
                w = csv.writer(fh)
                w.writerow(['Row ID', 'Source Code', 'Title', 'Result', 'Errors', 'Warnings'])
                for row in rows:
                    w.writerow([row.row_id, row.data['source_code'], row.data['title'],
                                'skipped' if row.errors else ('flagged' if row.warnings else 'clean'),
                                ' | '.join(row.errors), ' | '.join(row.warnings)])
            self.stdout.write(f'  report: {report}')
        if not commit:
            self.stdout.write('Run again with --commit to save.')
