"""Export the evidence an assessment of this sprint would read, read-only, to a private file outside the repository.

Builds the manifest and page sources with the same function an assessment uses to freeze its inputs
(`storage.evidence_snapshot`), so offline retrieval experiments see exactly the text a run would see.
No model calls, no database writes, and no run is created. The output carries institutional text:
keep it private and out of Git.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability.pipeline_diagnostics import page_coverage
from apps.scoring.capability.storage import digest, evidence_snapshot
from apps.sprints.models import Sprint


class Command(BaseCommand):
    help = "Write a sprint's assessment evidence (manifest and page sources) to a new JSON file outside the repository."

    def add_arguments(self, parser):
        parser.add_argument('sprint_id')
        parser.add_argument('--output', required=True, help='New JSON path outside the repository.')

    def handle(self, *args, **options):
        target = Path(options['output']).resolve()
        repository = Path(settings.BASE_DIR).resolve().parent
        if target.exists() or repository in target.parents:
            raise CommandError('Choose a new output path outside the repository.')
        try:
            sprint = Sprint.objects.get(pk=options['sprint_id'])
        except (Sprint.DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError('Sprint not found.') from exc
        manifest, sources = evidence_snapshot(sprint)
        coverage = page_coverage(manifest, sources)
        target.write_text(json.dumps({
            'sprint_id': str(sprint.pk), 'exported_at': datetime.now(timezone.utc).isoformat(),
            'manifest_hash': digest(manifest), 'sources_hash': digest(sources),
            'coverage': coverage, 'manifest': manifest, 'sources': sources,
        }, ensure_ascii=False), encoding='utf-8')
        totals = coverage['totals']
        self.stdout.write(f"Wrote {len(sources)} page sources from {len(manifest)} documents to {target}. "
                          f"Expected pages {totals['expected']}, stored {totals['rows']}, "
                          f"missing {totals['missing_rows']}; complete={coverage['complete']}.")
