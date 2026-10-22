"""Apply the auto-confirm rule (apps/facts/auto_confirm.py) to facts extracted before it existed.

    python manage.py auto_confirm_facts --sprint <uuid>            # dry run: what would be confirmed
    python manage.py auto_confirm_facts --sprint <uuid> --commit   # confirm them
"""
from django.core.management.base import BaseCommand, CommandError

from apps.facts.auto_confirm import auto_confirm, threshold
from apps.facts.models import ExtractedFact


class Command(BaseCommand):
    help = 'Auto-confirm unreviewed facts above FACT_AUTO_CONFIRM_MIN_CONFIDENCE (dry run unless --commit).'

    def add_arguments(self, parser):
        parser.add_argument('--sprint', help='Only this sprint (uuid). Without it: every sprint.')
        parser.add_argument('--commit', action='store_true', help='Actually confirm (default: dry run).')

    def handle(self, *args, **options):
        if threshold() is None:
            raise CommandError('Auto-confirmation is switched off (FACT_AUTO_CONFIRM_MIN_CONFIDENCE=off).')
        facts = ExtractedFact.objects.all()
        if options['sprint']:
            facts = facts.filter(sprint_id=options['sprint'])
        result = auto_confirm(facts, dry_run=not options['commit'])
        verb = 'Confirmed' if options['commit'] else 'Would confirm'
        self.stdout.write(f"{verb} {len(result['confirmed'])} fact(s) above {result['threshold']:.2f}.")
        for reason, n in sorted(result['skipped'].items()):
            self.stdout.write(f'  left for review ({reason}): {n}')
        if not options['commit']:
            self.stdout.write('Dry run: nothing changed. Add --commit to confirm them.')
