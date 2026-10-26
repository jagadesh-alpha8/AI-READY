"""Run the Stage 4 source watcher once, by hand.

    python manage.py run_source_watcher                       # every enabled feed
    python manage.py run_source_watcher --codes UGC-001 NBA-001
    python manage.py run_source_watcher --codes UGC-001 --dry-run --include-disabled
                                                              # fetch + compare, save nothing

Only records snapshots and change events for review; it never edits a source,
requirement, benchmark or release. Respects robots.txt.
"""
from django.core.management.base import BaseCommand, CommandError

from ...services.watcher import run_watcher


class Command(BaseCommand):
    help = 'Check the official pages of source feeds and record changes for review.'

    def add_arguments(self, parser):
        parser.add_argument('--codes', nargs='*', help='Only the feeds of these source codes.')
        parser.add_argument('--dry-run', action='store_true', help='Fetch and compare only; save nothing.')
        parser.add_argument('--include-disabled', action='store_true',
                            help='Also check feeds that are not enabled (use with --codes).')

    def handle(self, *args, codes, dry_run, include_disabled, **opts):
        from ...permissions import catalogue_locked
        if catalogue_locked():
            raise CommandError('Benchmark Studio is read-only (BENCHMARK_CATALOGUE_READ_ONLY): the manager workbooks '
                               'are the standard catalogue, so the source watcher is switched off.')
        run, results = run_watcher(codes=codes, trigger='manual', dry_run=dry_run, include_disabled=include_disabled)
        style = {'unchanged': str, 'baseline': self.style.SUCCESS, 'changed': self.style.WARNING,
                 'failed': self.style.ERROR, 'skipped': self.style.WARNING}
        for feed, r in results:
            line = f'  {feed.document.source_code:<14} {r["result"]:<9} events={r["events"]}  {r["detail"]}'
            self.stdout.write(style.get(r['result'], str)(line))
        if not results:
            self.stdout.write('No feeds matched (feeds are disabled until someone enables them; '
                              'use --include-disabled with --codes to try one).')
        self.stdout.write(('DRY RUN (nothing saved): ' if dry_run else f'Run {run.pk} {run.status}: ')
                          + f'{len(results)} feed(s), {sum(r["events"] for _, r in results)} change event(s).')
