"""Make every run's display copy complete now, instead of on each run's first open (capability/run_view.py).

Safe to run at any time and repeatedly: it reads each run and rewrites only its copy, never the run.
"""
from django.core.management.base import BaseCommand

from apps.scoring.capability.run_view import ensure
from apps.scoring.models import CapabilityRun


class Command(BaseCommand):
    help = "Build or refresh the runs' display copies (the run list and run detail read them)."

    def add_arguments(self, parser):
        parser.add_argument('--sprint', help='Only this sprint id.')

    def handle(self, *args, **options):
        runs = CapabilityRun.objects.order_by('created_at')
        if options.get('sprint'):
            runs = runs.filter(sprint_id=options['sprint'])
        ids = list(runs.values_list('pk', flat=True))
        for run_id in ids:
            view = ensure(run_id)
            self.stdout.write(f'{run_id}: {"completed copy" if view.event_id else "list fields"}'
                              f'{"" if view.verified or not view.event_id else " (integrity check failed)"}')
        self.stdout.write(f'{len(ids)} run(s).')
