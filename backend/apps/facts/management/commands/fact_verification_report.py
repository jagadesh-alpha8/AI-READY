"""Read-only reports on fact verification -- run these BEFORE enabling FACT_VERIFICATION_MODE=enforce.

    python manage.py fact_verification_report --sprint <uuid>              # workload + shadow replay + audit
    python manage.py fact_verification_report --shadow                     # replay over every sprint
    python manage.py fact_verification_report --audit --sprint <uuid>      # what verification says today
    python manage.py fact_verification_report --sprint <uuid> --json       # machine-readable

Nothing is written: no verification record, no fact status, no review, no score. Historical decisions stay as
people made them; a re-evaluation of them is only ever proposed here, never applied.
"""
import json

from django.core.management.base import BaseCommand

from apps.facts.models import ExtractedFact
from apps.facts.verification import metrics


class Command(BaseCommand):
    help = 'Read-only: workload, shadow replay of the automation rules, and an audit of existing facts.'

    def add_arguments(self, parser):
        parser.add_argument('--sprint', help='Only this sprint (uuid). Without it: every sprint.')
        parser.add_argument('--shadow', action='store_true', help='Only the shadow replay.')
        parser.add_argument('--audit', action='store_true', help='Only the audit of existing facts.')
        parser.add_argument('--limit', type=int, default=2000, help='At most this many facts per report.')
        parser.add_argument('--json', action='store_true', help='Print JSON.')

    def handle(self, *args, **options):
        facts = ExtractedFact.objects.all()
        if options['sprint']:
            facts = facts.filter(sprint_id=options['sprint'])
        both = not options['shadow'] and not options['audit']
        out = {}
        if options['sprint'] and both:
            from apps.sprints.models import Sprint
            out['workload'] = metrics.workload(Sprint.objects.get(pk=options['sprint']))
        if options['shadow'] or both:
            out['shadow'] = metrics.shadow_report(facts, limit=options['limit'])
        if options['audit'] or both:
            out['audit'] = metrics.historical_audit(facts.order_by('-created_at')[:options['limit']])
        if options['json']:
            self.stdout.write(json.dumps(out, indent=2, default=str))
            return
        if 'workload' in out:
            self.stdout.write('Workload')
            for key, value in out['workload'].items():
                self.stdout.write(f'  {key}: {value}')
        if 'shadow' in out:
            s = out['shadow']
            self.stdout.write(f'\nShadow replay ({s["policy_version"]}, mode now: {s["mode"]})')
            for key, value in s['totals'].items():
                self.stdout.write(f'  {key}: {value}')
            self.stdout.write(f'  precision if enabled: {s["precision_if_enabled"]}')
            self.stdout.write(f'  share of reviews saved: {s["review_saved_share"]}')
            self.stdout.write('  why the rest go to a person: ' + ', '.join(
                f'{k} {v}' for k, v in s['review_reasons'].items()))
            self.stdout.write('  calibration (reviewer agreement by extraction confidence):')
            for band, row in s['calibration'].items():
                self.stdout.write(f'    {band}: {row["agreement"]:.0%} of {row["agreed"] + row["changed"]}')
            for row in s['false_automatic_decisions'][:10]:
                self.stdout.write(f'  ! would have confirmed {row["field_key"]}={row["extracted"]!r}; the reviewer '
                                  f'{row["decided"].lower()} it (now {row["now"]!r})')
        if 'audit' in out:
            self.stdout.write('\nAudit of existing facts (status/outcome: count)')
            for key, value in out['audit']['counts'].items():
                self.stdout.write(f'  {key}: {value}')
        self.stdout.write('\nRead-only: nothing was changed.')
