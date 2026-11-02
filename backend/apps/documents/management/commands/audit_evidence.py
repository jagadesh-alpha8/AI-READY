"""Read-only deployment/sprint inventory; no document text, credentials or AI calls."""
import json
import subprocess
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError

from apps.documents.models import Document, DriveImportJob
from apps.extraction.models import DocumentPage
from apps.scoring.models import CapabilityRun
from apps.sprints.models import Sprint


def _safe_import(job):
    """Project diagnostic fields, never stored exception strings/provider bodies.

    Legacy results may not have source identities or reason codes. Preserve that
    absence instead of guessing identities from ambiguous basenames.
    """
    results = job.results if isinstance(job.results, dict) else {}
    safe_results = {}
    allowed = ('status', 'filename', 'document_id', 'drive_file_id', 'source_path', 'folder')
    reason_codes = {'unsupported_type', 'download_failed', 'validation_rejected'}
    for key, value in results.items():
        if key in {'additional_files', 'skipped_files'} and isinstance(value, list):
            rows = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                row = {field: item[field] for field in allowed if field in item}
                if key == 'skipped_files':
                    code = item.get('reason_code')
                    row['reason_code'] = code if code in reason_codes else 'legacy_unspecified'
                rows.append(row)
            safe_results[key] = rows
        elif key == 'progress' and isinstance(value, dict):
            safe_results[key] = {field: value[field] for field in ('processed', 'total') if field in value}
        elif isinstance(value, dict) and value.get('status') in {'found', 'missing'}:
            safe_results[key] = {field: value[field] for field in allowed if field in value}
    return {'id': str(job.pk), 'status': job.status, 'files_scanned': job.files_scanned,
            'files_imported': job.files_imported, 'error_present': bool(job.error_message),
            'results': safe_results}


class Command(BaseCommand):
    help = 'Print a read-only JSON inventory for one sprint; does not call an AI provider.'

    def add_arguments(self, parser):
        parser.add_argument('--sprint', required=True, help='Sprint UUID')

    def handle(self, *args, **options):
        try:
            sprint = Sprint.objects.get(pk=options['sprint'])
        except (Sprint.DoesNotExist, ValueError, ValidationError) as exc:
            raise CommandError('Sprint not found or invalid UUID.') from exc
        try:
            commit = subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=settings.BASE_DIR,
                stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
        except (OSError, subprocess.SubprocessError):
            commit = None
        docs = list(Document.objects.filter(sprint=sprint).order_by('created_at'))
        current = [d for d in docs if d.superseded_at is None]
        current_ids = [d.pk for d in current if d.status != Document.Status.REJECTED]
        pages = DocumentPage.objects.filter(document_id__in=current_ids)
        names = Counter(d.original_filename.casefold() for d in docs)
        runs = []
        for run in CapabilityRun.objects.filter(sprint=sprint).order_by('-created_at')[:5]:
            event = run.events.last()
            result = (event.payload or {}).get('result', {}) if event else {}
            runs.append({
                'run_id': str(run.pk), 'state': event.state if event else None,
                'created_at': run.created_at, 'population': run.inputs.get('population'),
                'reference_period': run.inputs.get('reference_period'),
                'frozen_documents': len(run.inputs.get('manifest', [])),
                'frozen_readable_pages': len(run.inputs.get('sources', [])),
                'lower': result.get('lower'), 'upper': result.get('upper'),
                'exact_score': result.get('exact_score'),
                'frozen_document_ids': [m['document_id'] for m in run.inputs.get('manifest', [])],
            })
        report = {
            'version': 'evidence-inventory-0.2', 'checkout_commit': commit,
            'sprint_id': str(sprint.pk),
            'limits': {'max_files': settings.GOOGLE_DRIVE_IMPORT_MAX_FILES,
                       'max_folders': settings.GOOGLE_DRIVE_IMPORT_MAX_FOLDERS},
            'documents_total': len(docs), 'current_documents': len(current),
            'superseded_documents': len(docs) - len(current),
            'current_status_counts': dict(Counter(d.status for d in current)),
            'current_page_status_counts': dict(Counter(pages.values_list('status', flat=True))),
            'duplicate_basename_groups': {n: c for n, c in names.items() if c > 1},
            'documents': [{'id': str(d.pk), 'filename': d.original_filename,
                           'drive_file_id': d.drive_file_id, 'source_path': d.source_path,
                           'status': d.status, 'expected_pages': d.page_count,
                           'previous_version_id': str(d.previous_version_id) if d.previous_version_id else None,
                           'superseded_at': d.superseded_at} for d in docs],
            'imports': [_safe_import(job) for job in
                        DriveImportJob.objects.filter(sprint=sprint).order_by('created_at')],
            'recent_runs': runs,
            'note': 'Counts describe this sprint only. A Git checkout SHA does not prove running workers were restarted.',
        }
        self.stdout.write(json.dumps(report, indent=2, default=str))
