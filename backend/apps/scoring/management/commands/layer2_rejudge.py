"""Credit path of the second layer (skeleton; see capability/layer2.py): re-judge the requirements new evidence was
submitted for, on their provisional packets plus the new passages, and merge.

    python manage.py layer2_rejudge export.json                     # dry run: list the targets, no model calls
    python manage.py layer2_rejudge export.json --run --out result.json

export.json is the provisional run's assessment export. --run spends model calls (two passes and the tie-break per
key indicator re-judged; not metered against a run budget yet). Nothing is published as a run.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import layer2
from apps.scoring.capability.layer2 import Layer2Error
from apps.scoring.capability.layer2_service import credit_routes, rejudge_credit


class Command(BaseCommand):
    help = 'Re-judge requirements with new second-layer evidence on their provisional packets.'

    def add_arguments(self, parser):
        parser.add_argument('export')
        parser.add_argument('--run', action='store_true', help='Make the model calls.')
        parser.add_argument('--out', help='Write the result to this JSON file.')
        parser.add_argument('--max-calls', type=int, default=36)

    def handle(self, *args, **options):
        with open(options['export'], encoding='utf-8') as f:
            export = json.load(f)
        try:
            records, rubric = export['assessment']['records'], export['rubric']
            routes = credit_routes(export['run_id'])
            targets = layer2.credit_targets(records, rubric, routes)
            self.stdout.write(f'{len(routes)} routes; {len(targets)} key indicators to re-judge:')
            for code, target in targets.items():
                self.stdout.write(f"  {code}: {', '.join(target['conditions'])} ({len(target['windows'])} new passages)")
            if not options['run']:
                self.stdout.write('Dry run: no model calls (use --run).')
                return
            from apps.extraction.services.ai_service import get_ai_service
            result = rejudge_credit(export, get_ai_service(), routes=routes, max_calls=options['max_calls'])
        except Layer2Error as exc:
            raise CommandError(str(exc))
        for row in result['merge']:
            self.stdout.write(f"  {row['condition_id']}: {row['decision']} "
                              f"({row['previous_credit']} -> {row['second_credit']})")
        for row in result['contradictions']:
            self.stdout.write(f"  For review, not applied: new evidence contradicts {row['condition_id']} "
                              f"(parts {', '.join(row['parts'])}).")
        self.stdout.write(f"Score: {result['provisional_score']} provisional, {result['final_score']} after re-judging.")
        if options['out']:
            with open(options['out'], 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=1, ensure_ascii=False, default=str)
