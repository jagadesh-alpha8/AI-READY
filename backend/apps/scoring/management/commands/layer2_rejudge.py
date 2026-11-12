"""Credit path of the second layer (skeleton; see capability/layer2.py): re-judge the requirements new evidence was
submitted for, on their provisional packets plus the new passages, and merge.

    python manage.py layer2_rejudge export.json                     # dry run: list the targets, no model calls
    python manage.py layer2_rejudge export.json --run --out result.json
    python manage.py layer2_rejudge --run-id <provisional run> --run --publish

export.json is the provisional run's assessment export; --run-id builds it from this database instead. --run spends
model calls (two passes and the tie-break per key indicator re-judged; not metered against a run budget yet).
--publish (needs the run in this database) publishes the final result as a new run refining the provisional one, which
reports, recommendations and plan evaluations then use.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import layer2
from apps.scoring.capability.layer2 import Layer2Error
from apps.scoring.capability.layer2_service import credit_routes, export_for_run, publish_final, rejudge_credit


class Command(BaseCommand):
    help = 'Re-judge requirements with new second-layer evidence on their provisional packets.'

    def add_arguments(self, parser):
        parser.add_argument('export', nargs='?')
        parser.add_argument('--run-id', help='Build the export from this provisional run in the database.')
        parser.add_argument('--run', action='store_true', help='Make the model calls.')
        parser.add_argument('--publish', action='store_true', help='Publish the final result as a run (needs --run).')
        parser.add_argument('--out', help='Write the result to this JSON file.')
        parser.add_argument('--max-calls', type=int, default=36)

    def handle(self, *args, **options):
        if bool(options['export']) == bool(options['run_id']):
            raise CommandError('Give an export file or --run-id, not both.')
        if options['publish'] and not options['run']:
            raise CommandError('--publish needs --run.')
        try:
            if options['run_id']:
                export = export_for_run(options['run_id'])
            else:
                with open(options['export'], encoding='utf-8') as f:
                    export = json.load(f)
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
            service = get_ai_service()
            result = rejudge_credit(export, service, routes=routes, max_calls=options['max_calls'])
            final_run = publish_final(result, service=service) if options['publish'] else None
        except Layer2Error as exc:
            raise CommandError(str(exc))
        for row in result['merge']:
            detail = f"credit {row['previous_credit']} -> {row['final_credit']}"
            if row['second_credit'] is not None and row['second_credit'] != row['final_credit']:
                detail += f"; the re-judgment alone gave {row['second_credit']}"
            if row.get('unlocked_parts'):
                detail += f"; parts counted once the subject was shown: {', '.join(row['unlocked_parts'])}"
            if row.get('issue'):
                detail += f"; {row['issue']}"
            self.stdout.write(f"  {row['condition_id']}: {row['decision']} ({detail})")
        for row in result['contradictions']:
            self.stdout.write(f"  For review, not applied: new evidence contradicts {row['condition_id']} "
                              f"(parts {', '.join(row['parts'])}).")
        self.stdout.write(f"Score: {result['provisional_score']} provisional, {result['final_score']} after re-judging.")
        if final_run is not None:
            self.stdout.write(f'Published the final result as run {final_run.pk} (refines {export["run_id"]}).')
        if options['out']:
            with open(options['out'], 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=1, ensure_ascii=False, default=str)
