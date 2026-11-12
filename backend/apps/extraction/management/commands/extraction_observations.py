"""Explicit read-only exports/comparison; no provider calls and no catalogue mutations."""
import json
from pathlib import Path
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from apps.extraction.observations import compare
from apps.facts.catalogue import VERSION, canonical_type


class Command(BaseCommand):
    help = 'Export a frozen extraction snapshot, inspect new category candidates, or compare two independent exports.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--job', help='Extraction job UUID; export its latest immutable snapshot.')
        group.add_argument('--compare', nargs=2, metavar=('FIRST_JSON', 'SECOND_JSON'))

    def handle(self, *args, **options):
        try:
            if options['compare']:
                payload = compare(*(json.loads(Path(p).read_text()) for p in options['compare']))
            else:
                from apps.extraction.models import ExtractionSnapshot
                snapshot = ExtractionSnapshot.objects.filter(job_id=options['job']).first()
                if snapshot is None:
                    raise CommandError('No frozen extraction snapshot for this job. Historical jobs were not backfilled.')
                payload = dict(snapshot.payload, job_id=str(snapshot.job_id), snapshot_id=str(snapshot.pk))
                candidates = Counter(f['field_key'] for f in payload['facts'] if not canonical_type(f['field_key']))
                payload['category_candidates'] = {'catalogue_version': VERSION,
                    'unmapped_keys': dict(sorted(candidates.items())),
                    'notice': 'Candidates require human review and a versioned catalogue change; they never alter scoring automatically.'}
            self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
        except (ValueError, KeyError, OSError) as exc:
            raise CommandError(str(exc)) from exc
