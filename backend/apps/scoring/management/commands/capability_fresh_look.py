"""Order the one fresh look for a requirement's compact re-judge, with a reason (capability/compact.py). Nothing
waits for this: a fresh look also runs by itself when the stored result was not a clean reading.

    python manage.py capability_fresh_look RUN AIQIF-C1.1.F2 --reason "The college says page 14 was not read."
"""
from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability.compact import order_fresh_look


class Command(BaseCommand):
    help = "Order a fresh look at a requirement's stored compact re-judge."

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('requirement')
        parser.add_argument('--reason', required=True)

    def handle(self, *args, **options):
        try:
            count = order_fresh_look(options['run_id'], options['requirement'], options['reason'])
        except ValueError as exc:
            raise CommandError(str(exc))
        self.stdout.write(f'{count} stored look(s) will be judged afresh at the next re-judge.' if count
                          else 'No stored look without a fresh look already: nothing to order.')
