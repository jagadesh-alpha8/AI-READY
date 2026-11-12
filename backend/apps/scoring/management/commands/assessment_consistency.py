"""Consistency and change report for a saved assessment export (no model calls, no database).

    python manage.py assessment_consistency new.json                 # within-run pass agreement
    python manage.py assessment_consistency new.json --compare old.json
                                                                       # plus run-to-run change; with a different
                                                                       # judge it lists every newly credited condition
                                                                       # with its quotes for a precision check
"""
import json

from django.core.management.base import BaseCommand

from apps.scoring.capability.consistency import TARGETS, between_runs, within_run


class Command(BaseCommand):
    help = 'Within-run and run-to-run consistency of a part-credit assessment export.'

    def add_arguments(self, parser):
        parser.add_argument('export')
        parser.add_argument('--compare', help='A second export of the same corpus.')
        parser.add_argument('--json', action='store_true', help='Print the full result as JSON.')

    def handle(self, *args, **options):
        with open(options['export'], encoding='utf-8') as f:
            report = json.load(f)
        result = {'targets': TARGETS, 'within_run': within_run(report)}
        if options['compare']:
            with open(options['compare'], encoding='utf-8') as f:
                result['between_runs'] = between_runs(report, json.load(f))
        if options['json']:
            self.stdout.write(json.dumps(result, indent=1, ensure_ascii=False))
            return
        w = result['within_run']
        if w.get('available'):
            self.stdout.write(f"Pass agreement {w['pass_agreement']:.0%} (target >= {TARGETS['pass_agreement']:.0%}); "
                              f"score pass 1 {w['score_pass_1']} vs pass 2 {w['score_pass_2']}, gap {w['score_gap']} "
                              f"(target <= {TARGETS['score_gap']}); largest area gap {w['area_gap']} "
                              f"(target <= {TARGETS['area_gap']}); {w['decided_by_third_pass']} decided by a third pass.")
        else:
            self.stdout.write(w['note'])
        b = result.get('between_runs')
        if b:
            self.stdout.write(f"Run score {b['score']} vs {b['other_score']} (gap {b['run_score_gap']}); same status "
                              f"{b['run_same_status']:.0%}; {len(b['gained'])} conditions gained credit, {len(b['lost'])} lost.")
