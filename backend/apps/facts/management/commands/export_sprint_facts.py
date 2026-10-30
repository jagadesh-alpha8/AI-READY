"""Read-only export of one sprint's documents, extraction jobs and facts as JSON -- for comparing two runs of the
same document (e.g. a local sprint and a live one) without touching either database.

    python manage.py export_sprint_facts <sprint-uuid> > sprint.json

Writes nothing to the database. Includes: the sprint and institution; each document's name, version, SHA-256
checksum, size, page count and processing state; every extraction job with its attempts, warnings, chunk and
page counters and AI usage (provider / model / tokens); the AI settings this server runs with (no secrets); and
every fact with its key, value, status, page, quote, confidence and kind.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _settings_snapshot():
    keys = ('AI_PROVIDER', 'AI_PROCESSING_MODE', 'OPENAI_EXTRACTION_MODEL', 'OPENAI_BASE_URL', 'ANTHROPIC_MODEL',
            'OPENAI_FACT_EXTRACTION_MAX_CHUNKS', 'OPENAI_FACT_EXTRACTION_MAX_CHUNK_CHARS', 'OPENAI_MAX_CHUNK_CHARS',
            'OCR_PROVIDER', 'PDF_MIN_TEXT_CHARS_PER_PAGE', 'PDF_TABLE_EXTRACTION', 'VISION_FALLBACK_ENABLED',
            'EXTRACTION_MAX_RETRIES', 'EXTRACTION_MAX_CONTINUATIONS', 'AI_ROUTER_URLS', 'FACT_VERIFICATION_MODE',
            'AI_TEMPERATURE', 'OPENAI_TEMPERATURE')
    out = {}
    for key in keys:
        if hasattr(settings, key):
            value = getattr(settings, key)
            if key == 'AI_ROUTER_URLS' and value:
                value = [str(u).split('?')[0] for u in value]  # never a key or token
            out[key] = value if isinstance(value, (str, int, float, bool, list, type(None))) else str(value)
    return out


class Command(BaseCommand):
    help = 'Read-only JSON export of a sprint: documents, extraction jobs and facts.'

    def add_arguments(self, parser):
        parser.add_argument('sprint')

    def handle(self, *args, **options):
        from apps.extraction.models import AIUsage, DocumentPage, ExtractionJob
        from apps.facts.models import ExtractedFact
        from apps.sprints.models import Sprint
        try:
            sprint = Sprint.objects.select_related('institution').get(pk=options['sprint'])
        except Sprint.DoesNotExist:
            raise CommandError('No such sprint.') from None
        documents = []
        for doc in sprint.documents.order_by('created_at'):
            pages = DocumentPage.objects.filter(document=doc)
            documents.append({
                'id': str(doc.id), 'name': doc.original_filename, 'version': doc.version_number,
                'checksum': doc.checksum, 'size': getattr(doc, 'file_size', None), 'page_count': doc.page_count,
                'status': doc.status, 'processing_status': doc.processing_status,
                'superseded_at': str(doc.superseded_at) if doc.superseded_at else None,
                'pages_stored': pages.count(),
                'pages_by_source': {s: pages.filter(text_source=s).count() for s in ('text', 'ocr', 'vision', 'none')},
                'pages_by_status': {s: pages.filter(status=s).count() for s in
                                    ('ok', 'unreadable', 'ocr_failed', 'ocr_unavailable', 'vision_failed',
                                     'vision_unavailable')},
            })
        jobs = []
        for job in ExtractionJob.objects.filter(sprint=sprint).order_by('created_at'):
            row = {'id': str(job.id), 'document_id': str(job.document_id), 'status': job.status,
                   'created_at': str(job.created_at), 'completed_at': str(getattr(job, 'completed_at', '') or '')}
            for name in ('completeness', 'chunks_total', 'chunks_completed', 'continuations', 'retry_count',
                         'pages_total', 'pages_done', 'ocr_pages', 'unreadable_pages', 'vision_pages',
                         'extraction_warnings', 'attempts', 'error_message', 'ai_router', 'facts_created'):
                if hasattr(job, name):
                    value = getattr(job, name)
                    row[name] = value if isinstance(value, (str, int, float, bool, list, dict, type(None))) else str(value)
            usage = AIUsage.objects.filter(extraction_job=job)
            row['ai_usage'] = [{'provider': u['provider'], 'model': u['model'], 'stage': u['stage'], 'calls': u['n'],
                                'tokens': u['tokens']} for u in _usage(usage)]
            jobs.append(row)
        facts = [{
            'id': str(f.id), 'field_key': f.field_key, 'field_name': f.field_name, 'value': f.value,
            'value_text': getattr(f, 'value_text', ''), 'normalized_value': f.normalized_value,
            'data_type': f.data_type, 'pillar': f.pillar, 'status': f.status, 'fact_kind': f.fact_kind,
            'document_id': str(f.document_id) if f.document_id else None,
            'source_document_id': str(f.source_document_id) if f.source_document_id else None,
            'source_page': f.source_page, 'source_snippet': f.source_snippet, 'confidence': f.confidence_score,
            'extraction_method': f.extraction_method, 'reviewed_by_email': f.reviewed_by.email if f.reviewed_by_id else None,
            'verification_status': getattr(f, 'verification_status', ''), 'created_at': str(f.created_at),
        } for f in ExtractedFact.objects.filter(sprint=sprint).select_related('reviewed_by').order_by('field_key')]
        self.stdout.write(json.dumps({
            'sprint': {'id': str(sprint.id), 'code': sprint.sprint_code, 'name': sprint.name, 'status': sprint.status,
                       'institution': sprint.institution.name, 'institution_id': str(sprint.institution_id)},
            'settings': _settings_snapshot(), 'documents': documents, 'jobs': jobs, 'facts': facts,
        }, indent=1, default=str))


def _usage(queryset):
    from django.db.models import Count, Sum
    rows = (queryset.values('provider', 'model', 'stage')
            .annotate(n=Sum('request_count'), tokens=Sum('input_tokens') + Sum('output_tokens'), rows=Count('id')))
    return [{'provider': r['provider'], 'model': r['model'], 'stage': r['stage'], 'n': r['n'], 'tokens': r['tokens']}
            for r in rows]
