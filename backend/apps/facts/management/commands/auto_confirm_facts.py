"""Verify unreviewed facts with the shared pipeline and apply the automation policy (apps/facts/verification/).

    python manage.py auto_confirm_facts --sprint <uuid>            # dry run: nothing is written
    python manage.py auto_confirm_facts --sprint <uuid> --commit   # record verification; the policy applies in
                                                                   #   FACT_VERIFICATION_MODE (shadow: records what
                                                                   #   it would do; enforce: confirms eligible facts)
Reviewed facts are never touched. AI confidence alone never confirms a fact.
"""
from django.core.management.base import BaseCommand

from apps.facts.auto_confirm import auto_confirm
from apps.facts.models import ExtractedFact


class Command(BaseCommand):
    help = 'Verify unreviewed facts and apply the automation policy (dry run unless --commit).'

    def add_arguments(self, parser):
        parser.add_argument('--sprint', help='Only this sprint (uuid). Without it: every sprint.')
        parser.add_argument('--commit', action='store_true', help='Record verification and apply the policy.')

    def handle(self, *args, **options):
        facts = ExtractedFact.objects.all()
        if options['sprint']:
            facts = facts.filter(sprint_id=options['sprint'])
        result = auto_confirm(facts, dry_run=not options['commit'])
        mode = result['mode']
        verb = {'enforce': 'Confirmed', 'shadow': 'Would confirm (shadow mode)'}.get(mode, 'Would confirm')
        self.stdout.write(f"{verb}: {len(result['confirmed'])} fact(s).")
        for reason, n in sorted(result['skipped'].items()):
            self.stdout.write(f'  left for review ({reason}): {n}')
        if not options['commit']:
            self.stdout.write('Dry run: nothing was written. Add --commit to record verification.')
