"""Write the score explanations for a completed run (provisional or final), unmetered, with a cap on calls.

    python manage.py capability_explain RUN_ID                 # print what would be written
    python manage.py capability_explain RUN_ID --save          # store them for the run's reports and API
    python manage.py capability_explain RUN_ID --out file.json

One model call per area (9), at most two each. The background job (second-layer operation 'explain') is the metered
route for the product; this is for consultants and for checking the wording on a real run.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.models import CapabilityExplanation, CapabilityRun


class Command(BaseCommand):
    help = 'Write the score explanations for a completed run (model calls, unmetered, capped).'

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--max-calls', type=int, default=18)
        parser.add_argument('--save', action='store_true')
        parser.add_argument('--out')

    def handle(self, *args, **options):
        from apps.scoring.capability.depth import default_model
        from apps.scoring.capability.explanations import build_target, explain
        run = CapabilityRun.objects.filter(pk=options['run_id']).first()
        if run is None:
            raise CommandError('Run not found.')
        try:
            target = build_target(run)
        except ValueError as exc:
            raise CommandError(str(exc))
        model = default_model()
        written = explain(target, model, max_calls=options['max_calls'])
        self.stdout.write(f"{written['calls']} calls; {len(written['requirements'])} requirements explained; "
                          f"{len(written['fallbacks'])} plain fallbacks.")
        for area, errors in written['errors'].items():
            self.stdout.write(f'  {area}: {len(errors)} problems left after the retry, e.g. {errors[0]}')
        if options['save']:
            CapabilityExplanation.objects.create(run=run, event_id=target['event_id'], version=written['version'],
                                                 model=getattr(model, 'model_name', ''), payload=written)
            self.stdout.write('Saved.')
        if options['out']:
            with open(options['out'], 'w') as handle:
                json.dump(written, handle, indent=2, ensure_ascii=False)
