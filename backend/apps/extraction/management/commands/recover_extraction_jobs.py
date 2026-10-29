"""Re-queue extraction jobs whose queue message or worker was lost (services/recovery.py).

    python manage.py recover_extraction_jobs --dry-run   # list what would be re-queued, change nothing
    python manage.py recover_extraction_jobs             # re-queue them
"""
from django.core.management.base import BaseCommand

from ...services.recovery import recover


class Command(BaseCommand):
    help = 'Re-queue extraction jobs whose queue message or worker was lost. Completed / failed / stopped jobs ' \
           'are never touched.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='List what would be re-queued; change nothing.')

    def handle(self, *args, **opts):
        rows = recover(dry_run=opts['dry_run'])
        if not rows:
            self.stdout.write('Nothing to recover.')
        for row in rows:
            self.stdout.write(f"{row['action']}: job {row['job_id']} ({row['status']}, {row['reason']})")
