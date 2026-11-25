"""Export a sprint's evidence map to a private JSON file outside the repository (for Check 1 and audits).

    python manage.py evidence_map_export SPRINT_ID --output /tmp/vistas-map.json [--map-version V --model M]

Without --map-version/--model, the newest tagging pass of the sprint names them. The output carries the college's own
words (quotations): keep it private and out of Git. No model calls and no database writes.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.evidence_map import spec, tagging
from apps.evidence_map.models import MapJob
from apps.sprints.models import Sprint


class Command(BaseCommand):
    help = "Write a sprint's evidence map (page types, tags, coverage) to a new JSON file outside the repository."

    def add_arguments(self, parser):
        parser.add_argument('sprint_id')
        parser.add_argument('--output', required=True)
        parser.add_argument('--map-version')
        parser.add_argument('--model')

    def handle(self, *args, **options):
        target = Path(options['output']).resolve()
        from apps.scoring.capability.private_output import inside_code
        if target.exists() or inside_code(target):
            raise CommandError('Choose a new output path outside the repository.')
        try:
            sprint = Sprint.objects.get(pk=options['sprint_id'])
        except (Sprint.DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError('Sprint not found.') from exc
        version, model = options['map_version'], options['model']
        if not version or not model:
            job = MapJob.objects.filter(sprint=sprint).order_by('-started_at').first()
            if job is None:
                raise CommandError('The sprint has no tagging pass; give --map-version and --model.')
            version, model = version or job.map_version, model or job.model
        documents = tagging.sprint_documents(sprint)
        counts, rows, hashes = tagging.coverage(sprint, version, model, documents)
        pages = []
        for doc in documents:
            for page in doc['readable']:
                row = rows.get(hashes[page['id']])
                pages.append({'page_id': page['id'], 'document_id': doc['document_id'], 'filename': doc['filename'],
                              'page_number': page['number'], 'chars': len(page['text']),
                              'text_hash': hashes[page['id']],
                              'status': row.status if row else 'not_tagged',
                              'page_type': row.page_type if row else '', 'tags': row.tags if row else [],
                              'error': row.error if row else ''})
        jobs = [{'id': str(j.pk), 'status': j.status, 'shape': j.shape, 'pages_tagged': j.pages_tagged,
                 'pages_failed': j.pages_failed, 'requests': j.requests, 'spend_usd': str(j.spend_usd),
                 'checks': j.checks, 'started_at': j.started_at.isoformat(),
                 'finished_at': j.finished_at.isoformat() if j.finished_at else None}
                for j in MapJob.objects.filter(sprint=sprint, map_version=version, model=model)]
        target.write_text(json.dumps({
            'sprint_id': str(sprint.pk), 'exported_at': datetime.now(timezone.utc).isoformat(),
            'spec_version': spec.SPEC_VERSION, 'map_version': version, 'model': model, 'prompt': spec.PROMPT,
            'coverage': counts, 'jobs': jobs, 'pages': pages}, ensure_ascii=False), encoding='utf-8')
        self.stdout.write(f'Wrote {len(pages)} pages to {target}. Coverage: {counts}.')
