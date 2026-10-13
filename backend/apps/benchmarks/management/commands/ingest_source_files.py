"""Copy downloaded source files from Google Drive into app storage and verify them.

    python manage.py ingest_source_files               # every downloaded draft not yet ingested
    python manage.py ingest_source_files --codes UGC-005 NBA-002
    python manage.py ingest_source_files --retry       # also re-check verified / mismatched ones
    python manage.py ingest_source_files --dry-run     # fetch and compare, store nothing

The Drive files must be shared "Anyone with the link - Viewer" (same as the
Upload Data Pack Drive import). Licensed standards are never fetched.
"""
from django.core.management.base import BaseCommand

from ...services.file_intake import run_intake


class Command(BaseCommand):
    help = 'Fetch, store and checksum-verify source files (Drive file links).'

    def add_arguments(self, parser):
        parser.add_argument('--codes', nargs='*', help='Only these source codes.')
        parser.add_argument('--retry', action='store_true', help='Include already-ingested versions.')
        parser.add_argument('--dry-run', action='store_true', help='Fetch and compare only; store nothing.')
        parser.add_argument('--actor', default='ingest_source_files')

    def handle(self, *args, codes, retry, dry_run, actor, **opts):
        summary = run_intake(codes, retry=retry, dry_run=dry_run, actor=actor)
        style = {'verified': self.style.SUCCESS, 'computed': self.style.SUCCESS, 'mismatch': self.style.ERROR,
                 'failed': self.style.ERROR, 'skipped': self.style.WARNING}
        for r in summary.results:
            line = f'  {r.version.document.source_code:<14} {r.status:<9} {r.note}'
            self.stdout.write(style.get(r.status, str)(line))
        counts = {s: summary.count(s) for s in ('verified', 'computed', 'mismatch', 'skipped', 'failed')}
        self.stdout.write(('DRY RUN: ' if dry_run else '') + f'{len(summary.results)} versions: {counts}')
