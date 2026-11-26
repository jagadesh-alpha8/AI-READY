"""Write the next steps for a completed run (provisional or final), unmetered, with a cap on calls.

    python manage.py capability_next_steps RUN_ID                 # print what would be written
    python manage.py capability_next_steps RUN_ID --save          # store them for the run's reports and screens
    python manage.py capability_next_steps RUN_ID --out file.json
    python manage.py capability_next_steps RUN_ID --job           # queue the metered background job instead
    python manage.py capability_next_steps RUN_ID --job --final   # the same for the published final result
    python manage.py capability_next_steps --export run.json --packets   # what each step is given; no model call
    python manage.py capability_next_steps --export run.json --out steps.json   # write them from a report's JSON export
    python manage.py capability_next_steps RUN_ID --import answers.json --save  # store steps written elsewhere

--import takes answers in the model's own form, keyed by topic title ({"Responsible-use guidance": {...}}), runs every
one through the same checks as the model's answers (next_steps.validate) and keeps only those that pass; the rest stay
on the plain checklist. For steps written by hand or by another model while the scoring model is unavailable; the
stored row says who wrote them (--written-by).

One model call per chosen step (one in each area, nine at most), a second only to fix the first's problems; through the scoring-
model switch (CAPABILITY_AI_*) at the writing effort. The background job (second-layer operation 'next_steps') is the
metered route for the product; this is for consultants and for checking the wording on a real run.

Generate only on runs whose evidence is fair to the college: the text says what we did not find, so a run that read
too little evidence would point to gaps that are not real.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.models import CapabilityNextSteps, CapabilityRun


class Command(BaseCommand):
    help = 'Write the next steps for a completed run (model calls, unmetered, capped).'

    def add_arguments(self, parser):
        parser.add_argument('run_id', nargs='?')
        parser.add_argument('--export', help="A report's JSON export (file=json) to write from, instead of a run in "
                                             'this database. Never saved.')
        parser.add_argument('--packets', action='store_true',
                            help='Print each chosen step and the passages it would be given; no model call.')
        parser.add_argument('--max-calls', type=int, default=18)
        parser.add_argument('--import', dest='answers', help='Answers in the model\'s form, keyed by topic title.')
        parser.add_argument('--written-by', default='hand-written, checked by next_steps.validate')
        parser.add_argument('--save', action='store_true')
        parser.add_argument('--out')
        parser.add_argument('--job', action='store_true',
                            help='Queue the metered background job (as the API does) instead of writing here.')
        parser.add_argument('--final', action='store_true',
                            help="With --job: write the published final result's next steps.")

    def handle(self, *args, **options):
        from apps.scoring.capability.depth import default_model
        from apps.scoring.capability.next_steps import build_target, packet, target_from_export, write
        if options['export']:
            if options['run_id'] or options['save'] or options['job']:
                raise CommandError('--export reads a file: give no run id, and it is never saved or queued.')
            with open(options['export']) as handle:
                target = target_from_export(json.load(handle))
            return self.write(target, options, packets=packet)
        run = CapabilityRun.objects.filter(pk=options['run_id']).first() if options['run_id'] else None
        if run is None:
            raise CommandError('Run not found.')
        if options['job']:
            return self.queue(run, final=options['final'])
        if options['final']:
            raise CommandError('--final goes with --job; without it, pass the final run id itself.')
        try:
            target = build_target(run)
        except ValueError as exc:
            raise CommandError(str(exc))
        if options['packets']:
            return self.write(target, options, packets=packet)
        if options['answers']:
            written = self.imported(target, options['answers'], options['written_by'])
            model = None
        else:
            model = default_model()
            written = write(target, model, max_calls=options['max_calls'])
        self.stdout.write(f"{written['calls']} calls; {len(written['actions'])} steps written; "
                          f"{len(written['fallbacks'])} on the plain checklist.")
        for key, errors in written['errors'].items():
            self.stdout.write(f'  {key}: {len(errors)} problems left after the retry, e.g. {errors[0]}')
        if options['save']:
            CapabilityNextSteps.objects.create(run=run, event_id=target['event_id'], version=written['version'],
                                               model=(getattr(model, 'model_name', '') if model else
                                                      options['written_by'])[:100], payload=written)
            self.stdout.write('Saved.')
        if options['out']:
            with open(options['out'], 'w') as handle:
                json.dump(written, handle, indent=2, ensure_ascii=False)
        elif not options['save']:
            self.stdout.write(json.dumps(written['actions'], indent=2, ensure_ascii=False))

    def imported(self, target, path, written_by):
        from apps.scoring.capability.next_steps import VERSION, action_key, packet, validate
        with open(path) as handle:
            answers = json.load(handle)
        out = {'version': VERSION, 'run_id': target['run_id'], 'event_id': target['event_id'], 'actions': {},
               'fallbacks': [], 'errors': {}, 'calls': 0, 'written_by': written_by,
               'chosen': [action_key(a) for a in target['actions']]}
        for action in target['actions']:
            key = action_key(action)
            answer = answers.get(action['title'])
            text, problems = (validate(packet(action, target), answer) if answer is not None
                              else (None, ['no answer given']))
            if text is None:
                out['fallbacks'].append(key)
                out['errors'][key] = problems
            else:
                out['actions'][key] = text
        return out

    def write(self, target, options, packets):
        from apps.scoring.capability.depth import default_model
        from apps.scoring.capability.next_steps import write
        if options['packets']:
            out = []
            for action in target['actions']:
                given = packets(action, target)
                out.append({'area': action['area'], 'topic': action['title'], 'start_here': action.get('start_here'),
                            'practices': [r['done_when'] for r in given['requirements']],
                            'passages': [{k: p[k] for k in ('id', 'role', 'where', 'text')} for p in given['passages']]})
            text = json.dumps(out, indent=2, ensure_ascii=False)
        else:
            written = write(target, default_model(), max_calls=options['max_calls'])
            self.stdout.write(f"{written['calls']} calls; {len(written['actions'])} steps written; "
                              f"{len(written['fallbacks'])} on the plain checklist.")
            for key, errors in written['errors'].items():
                self.stdout.write(f'  {key}: {len(errors)} problems left after the retry, e.g. {errors[0]}')
            text = json.dumps(written, indent=2, ensure_ascii=False)
        if options['out']:
            with open(options['out'], 'w') as handle:
                handle.write(text)
        else:
            self.stdout.write(text)

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
                job, _ = jobs.start(run=run, operation='next_steps', user=None,
                                    key=f'next-steps-cli-{uuid.uuid4().hex[:16]}',
                                    options={'final': True} if final else None)
        except APIException as exc:
            raise CommandError(str(getattr(exc, 'detail', exc)))
        self.stdout.write(f'Queued next-steps job {job.pk} for run {run.pk}. '
                          'The reports and screens show the steps once it completes.')
