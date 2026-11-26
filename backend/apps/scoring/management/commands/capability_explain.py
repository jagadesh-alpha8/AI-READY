"""Write the score explanations for a completed run (provisional or final), unmetered, with a cap on calls.

    python manage.py capability_explain RUN_ID                 # print what would be written
    python manage.py capability_explain RUN_ID --save          # store them for the run's reports and API
    python manage.py capability_explain RUN_ID --out file.json
    python manage.py capability_explain RUN_ID --job           # queue the metered background job instead
    python manage.py capability_explain RUN_ID --job --final   # the same for the published final result (to restart
                                                               # its explanations); RUN_ID may be either run

--job queues the same job the API starts (operation 'explain'): metered against the run's second-layer budget,
written areas side by side at the run's indicator concurrency (about 15 minutes at 4 on VISTAS, against about 55 one
at a time), and stored when it finishes. It needs the second-layer jobs on and a worker running. Use it for a Stage 1
result: publishing the final result starts the final run's explanations by itself.

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
        parser.add_argument('--job', action='store_true',
                            help='Queue the metered background job (as the API does) instead of writing here.')
        parser.add_argument('--final', action='store_true',
                            help="With --job: write the published final result's explanations.")
        parser.add_argument('--import', dest='cards',
                            help='Area cards written outside the product ({area code: {verdict, headline, strengths, '
                                 'gaps}}), checked against this run and laid on its newest stored explanations. '
                                 'No model call.')
        parser.add_argument('--written-by', default='hand-written, checked by explanations._check_card')

    def handle(self, *args, **options):
        from apps.scoring.capability.depth import default_model
        from apps.scoring.capability.explanations import build_target, explain
        run = CapabilityRun.objects.filter(pk=options['run_id']).first()
        if run is None:
            raise CommandError('Run not found.')
        if options['job']:
            return self.queue(run, final=options['final'])
        if options['final']:
            raise CommandError('--final goes with --job; without it, pass the final run id itself.')
        if options['cards']:
            return self.import_cards(run, options)
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
            from apps.scoring.capability.publication import publish_if_ready
            if publish_if_ready(run.pk):
                self.stdout.write('Its reports pass the draft checks: published for the college.')
        if options['out']:
            with open(options['out'], 'w') as handle:
                json.dump(written, handle, indent=2, ensure_ascii=False)

    def import_cards(self, run, options):
        """Area cards written without the model, through the product's own checks (explanations.import_cards)."""
        from apps.scoring.capability.explanations import build_target, import_cards
        try:
            target = build_target(run)
        except ValueError as exc:
            raise CommandError(str(exc))
        base = (CapabilityExplanation.objects.filter(run=run, event_id=target['event_id']).order_by('-created_at')
                .values_list('payload', flat=True).first())
        if not base:
            raise CommandError('This run has no stored explanations to lay the cards on: write them first.')
        with open(options['cards']) as handle:
            cards = json.load(handle)
        if isinstance(cards, dict) and isinstance(cards.get('areas'), dict) and 'version' in cards:
            cards = cards['areas']   # a whole explanations payload: its areas' cards
        written, problems = import_cards(target, base, cards, options['written_by'])
        passed = len(written['areas']) - len(problems)
        self.stdout.write(f'{passed} of {len(written["areas"])} area cards pass the checks.')
        for area, errors in problems.items():
            self.stdout.write(f'  {area}: {errors[0]}' + (f' (and {len(errors) - 1} more)' if len(errors) > 1 else ''))
        if options['save']:
            CapabilityExplanation.objects.create(run=run, event_id=target['event_id'], version=written['version'],
                                                 model=options['written_by'][:100], payload=written)
            self.stdout.write('Saved.' + (' The areas that failed stay on plain wording, so the reports stay a '
                                          'draft until they are written.' if problems else ''))
            from apps.scoring.capability.publication import publish_if_ready
            if publish_if_ready(run.pk):
                self.stdout.write('Its reports pass the draft checks: published for the college.')
        if options['out']:
            with open(options['out'], 'w') as handle:
                json.dump(written, handle, indent=2, ensure_ascii=False)

    def queue(self, run, final=False):
        import uuid
        from django.db import transaction
        from rest_framework.exceptions import APIException
        from apps.scoring.capability import second_layer_jobs as jobs
        from apps.scoring.capability.layer2_service import is_final
        if is_final(run):
            if not final:
                raise CommandError('This run is a published final result: add --final (or pass its Stage 1 run id).')
            run = CapabilityRun.objects.get(pk=run.inputs['second_layer']['provisional_run_id'])
        try:
            with transaction.atomic():
                job, _ = jobs.start(run=run, operation='explain', user=None, key=f'explain-cli-{uuid.uuid4().hex[:16]}',
                                    options={'final': True} if final else None)
        except APIException as exc:
            raise CommandError(str(getattr(exc, 'detail', exc)))
        self.stdout.write(f'Queued explanation job {job.pk} for run {run.pk} '
                          f'({job.policy.get("indicator_concurrency", 1)} area(s) at a time). '
                          'The reports show the explanations once it completes.')
