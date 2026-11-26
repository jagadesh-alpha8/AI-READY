"""Tag a sprint's pages for the evidence map (spec: claude/ai-ready-evidence-map-spec.md in the claude.ai project).

    python manage.py evidence_map_tag SPRINT_ID --dry-run            # what it would send, no model calls
    python manage.py evidence_map_tag SPRINT_ID --max-cost 3         # tag every untagged page, stop at $3 spent
    python manage.py evidence_map_tag SPRINT_ID --shape areas        # one call per area instead of one per chunk
    python manage.py evidence_map_tag SPRINT_ID --document "Self-Study" --limit-pages 40   # a pilot

Only pages with no tagged row under the same map version and model are sent, so a stopped or failed pass resumes.
The tagger is EVIDENCE_MAP_AI_API_KEY / EVIDENCE_MAP_AI_MODEL when set, else the scoring model. No assessment reads
the map yet: running this changes no score.
"""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.evidence_map import spec, tagging
from apps.sprints.models import Sprint


class Command(BaseCommand):
    help = "Read a sprint's pages against the rubric once and store what each page is evidence of."

    def add_arguments(self, parser):
        parser.add_argument('sprint_id')
        parser.add_argument('--shape', choices=spec.SHAPES, default='one',
                            help="'one': the whole rubric per request; 'areas': one request per area; "
                                 "'areas-every': one per area, checking every indicator of the area per page.")
        parser.add_argument('--max-cost', type=float, default=None,
                            help='Stop starting requests once this many US dollars are spent (default '
                                 'EVIDENCE_MAP_MAX_COST_USD).')
        parser.add_argument('--concurrency', type=int, default=4)
        parser.add_argument('--document', action='append', help='Only documents whose filename contains this.')
        parser.add_argument('--limit-pages', type=int, default=None, help='Tag at most this many pages (a pilot).')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be sent; no calls, no writes.')

    def handle(self, *args, **options):
        try:
            sprint = Sprint.objects.get(pk=options['sprint_id'])
        except (Sprint.DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError('Sprint not found.') from exc
        if options['dry_run']:
            work = tagging.plan(sprint, shape=options['shape'], documents=options['document'],
                                limit_pages=options['limit_pages'])
            self.stdout.write(
                f"Map version {work['version']} ({options['shape']}), model {work['model'] or '(none configured)'}.\n"
                f"Pages: {work['pages_total']} readable ({work['pages_unique']} distinct texts), "
                f"{work['pages_unreadable']} unreadable, {work['pages_done']} already tagged, "
                f"{work['pages_to_tag']} to tag.\n"
                f"Requests: {work['requests']} ({len(work['chunks'])} chunks x {len(work['prompts'])} prompt(s)); "
                f"about {work['input_chars']:,} input characters.")
            return
        job = tagging.run(sprint, shape=options['shape'], concurrency=options['concurrency'],
                          max_cost_usd=options['max_cost'], documents=options['document'],
                          limit_pages=options['limit_pages'], log=lambda m: self.stdout.write('  ' + m))
        self.stdout.write(
            f"\nJob {job.pk}: {job.get_status_display()}. Map version {job.map_version}, model {job.model}.\n"
            f"Pages tagged {job.pages_tagged}, failed {job.pages_failed}, of {job.pages_to_tag} to tag "
            f"({job.pages_total} readable, {job.pages_skipped} unreadable). Requests {job.requests}; "
            f"spent ${job.spend_usd:.4f} of ${job.spend_cap_usd}.\nChecks: {job.checks}")
        if job.error:
            raise CommandError(job.error)
