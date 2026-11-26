"""Add what a completed run's judge credited to the evidence map (apps/evidence_map/learn.py). No model calls.

    python manage.py evidence_map_learn RUN_ID --shape areas --dry-run
    python manage.py evidence_map_learn RUN_ID --shape areas [--exclude reviewed.json]
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.evidence_map import learn, spec, tagging


class Command(BaseCommand):
    help = "Turn a completed run's credited quotations into tags on the evidence map."

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--shape', choices=spec.SHAPES, default=None)
        parser.add_argument('--map-version', default=None)
        parser.add_argument('--exclude', default=None,
                            help='A review sheet (JSON): rows with verdict not_evidence are left out.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if bool(options['shape']) == bool(options['map_version']):
            raise CommandError('Give exactly one of --shape and --map-version.')
        version = options['map_version']
        if options['shape']:
            version = spec.map_version(options['shape'], *spec.rubric_sources())
        exclude = set()
        if options['exclude']:
            rows = json.load(open(options['exclude'], encoding='utf-8'))
            exclude = {(r['requirement'], r['filename'], r['page_number']) for r in rows
                       if r.get('verdict') == 'not_evidence'}
        try:
            added, counts = learn.from_run(options['run_id'], map_version=version, model=tagging._model_name(),
                                           exclude=exclude, dry_run=options['dry_run'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Map version {version}: {'would add' if options['dry_run'] else 'added'} "
                          f"{counts.get('tags', 0) if options['dry_run'] else added} tags. Counts: {dict(counts)}")
