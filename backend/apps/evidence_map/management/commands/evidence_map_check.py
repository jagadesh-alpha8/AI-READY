"""The requirement check: for each requirement, the pages a word search ranks closest that the map left without a
strong tag for its indicator are checked once more (apps/evidence_map/requirement_check.py).

    python manage.py evidence_map_check SPRINT_ID --shape areas --dry-run        # what it would send, no calls
    python manage.py evidence_map_check SPRINT_ID --shape areas --max-cost 0.50  # one request per key indicator
    python manage.py evidence_map_check SPRINT_ID --map-version em1-... --indicator C9.2
"""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.evidence_map import requirement_check, spec, tagging
from apps.sprints.models import Sprint


class Command(BaseCommand):
    help = "Check each requirement's closest untagged pages once more and add what is evidence to the map."

    def add_arguments(self, parser):
        parser.add_argument('sprint_id')
        parser.add_argument('--shape', choices=spec.SHAPES, default=None, help='The map to check, by its shape.')
        parser.add_argument('--map-version', default=None, help='The map to check, by its version.')
        parser.add_argument('--per-requirement', type=int, default=requirement_check.PER_REQUIREMENT)
        parser.add_argument('--indicator', action='append', help='Only this key indicator (for example C9.2).')
        parser.add_argument('--max-cost', type=float, default=0.5, help='Stop once this many US dollars are spent.')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be sent; no calls, no writes.')

    def handle(self, *args, **options):
        try:
            sprint = Sprint.objects.get(pk=options['sprint_id'])
        except (Sprint.DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError('Sprint not found.') from exc
        if bool(options['shape']) == bool(options['map_version']):
            raise CommandError('Give exactly one of --shape and --map-version.')
        version = options['map_version']
        if options['shape']:
            rubric, profiles, parts = spec.rubric_sources()
            version = spec.map_version(options['shape'], rubric, profiles, parts)
        if not 1 <= options['per_requirement'] <= 10:
            raise CommandError('--per-requirement must be from 1 to 10.')
        indicators = [spec._long(i) for i in options['indicator'] or []] or None
        model = tagging._model_name()
        if options['dry_run']:
            work = requirement_check.plan(sprint, map_version=version, model=model,
                                          per_requirement=options['per_requirement'], indicators=indicators)
            self.stdout.write(f"Map version {version}, model {model or '(none configured)'}, check {work['version']}.\n"
                              f"Requests: {work['requests']} (one per key indicator); pages: {work['pages']}; "
                              f"about {work['input_chars']:,} input characters.")
            return
        job = requirement_check.run(sprint, map_version=version, model=model, per_requirement=options['per_requirement'],
                                    max_cost_usd=options['max_cost'], indicators=indicators,
                                    log=lambda m: self.stdout.write('  ' + m))
        checks = {k: v for k, v in job.checks.items() if k != 'asked'}
        self.stdout.write(f"\nJob {job.pk}: {job.get_status_display()}. Map version {job.map_version}, model "
                          f"{job.model}.\nIndicators checked {job.chunks_done} of {job.chunks_total}; pages "
                          f"{job.pages_tagged}; spent ${job.spend_usd:.4f} of ${job.spend_cap_usd}.\nChecks: {checks}")
        if job.error:
            raise CommandError(job.error)
