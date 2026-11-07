"""Export one run's frozen page text for one document, read-only, to a private file outside the repository.

Used to build and audit answer keys against exactly the text an assessment saw. The output carries
institutional text: keep it private and out of Git. No model calls and no database writes.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability.storage import digest
from apps.scoring.models import CapabilityRun


class Command(BaseCommand):
    help = "Write a run's frozen source pages for one document to a new JSON file outside the repository."

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--match', required=True, help='Substring of the document filename, e.g. "Self-Study".')
        parser.add_argument('--output', required=True, help='New JSON path outside the repository.')

    def handle(self, *args, **options):
        target = Path(options['output']).resolve()
        repository = Path(settings.BASE_DIR).resolve().parent
        if target.exists() or repository in target.parents:
            raise CommandError('Choose a new output path outside the repository.')
        try:
            run = CapabilityRun.objects.get(pk=options['run_id'])
        except (CapabilityRun.DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError('Run not found.') from exc
        hash_matches = digest(run.inputs) == run.inputs_hash
        if not hash_matches:
            self.stderr.write('Warning: frozen inputs do not match their recorded hash; the export records this.')
        manifest = [d for d in run.inputs['manifest'] if options['match'] in (d.get('filename') or '')]
        if len(manifest) != 1:
            raise CommandError(f'"{options["match"]}" matches {len(manifest)} documents in this run.')
        document = manifest[0]
        pages = sorted((s for s in run.inputs['sources'] if s['document_id'] == document['document_id']),
                       key=lambda s: s['page_number'])
        target.write_text(json.dumps({
            'run_id': str(run.pk), 'inputs_hash': run.inputs_hash, 'inputs_hash_verified': hash_matches,
            'document': {k: document.get(k) for k in ('document_id', 'filename', 'checksum', 'version', 'expected_pages')},
            'pages': [{'id': s['id'], 'page_number': s['page_number'], 'text_source': s.get('text_source'),
                       'text': s['text']} for s in pages],
        }, ensure_ascii=False, indent=1))
        self.stdout.write(f"Wrote {len(pages)} of {document.get('expected_pages')} pages of "
                          f"{document['filename']} to {target}.")
