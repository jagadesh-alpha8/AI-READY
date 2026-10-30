"""Immutable extraction snapshots and independent-run comparisons, without inference."""
from collections import Counter
import hashlib
import json

from apps.facts.catalogue import VERSION, canonical_type, identity


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def protocol():
    from .services.openai_fact_extractor import SYSTEM_PROMPT, FACT_EXTRACTION_SCHEMA
    from .services.document_analysis import SYSTEM_PROMPT as ANALYSIS_PROMPT, ANALYSIS_SCHEMA
    from django.conf import settings
    return {'version': 'extraction-protocol-0.1', 'catalogue_version': VERSION,
            'prompt_hash': digest(SYSTEM_PROMPT), 'schema_hash': digest(FACT_EXTRACTION_SCHEMA),
            'analysis_prompt_hash': digest(ANALYSIS_PROMPT), 'analysis_schema_hash': digest(ANALYSIS_SCHEMA),
            'temperature': settings.AI_TEMPERATURE, 'seed': settings.AI_SEED,
            'mode': settings.AI_PROCESSING_MODE, 'configured_model': settings.AI_MODEL}


def freeze(job, facts):
    from .models import DocumentPage, ExtractionSnapshot, AIUsage
    import pymupdf
    document = job.document
    pages = list(DocumentPage.objects.filter(document=document).order_by('page_number').values(
        'page_number', 'text', 'text_source', 'status'))
    inputs = {'checksum': document.checksum, 'filename': document.original_filename,
              'pages_hash': digest(pages), 'protocol': protocol(),
              'reader_version': pymupdf.VersionBind,
              'chunks': list(job.chunks.order_by('index').values('index', 'page_numbers', 'content_hash'))}
    payload = {'format_version': 'extraction-observations-0.1', 'inputs': inputs,
               'input_hash': digest(inputs), 'extraction_job_id': str(job.pk), 'completeness': job.completeness,
               'facts': facts, 'models': list(AIUsage.objects.filter(extraction_job=job).order_by(
                   'provider', 'model').values('provider', 'model').distinct())}
    ExtractionSnapshot.objects.get_or_create(job=job, content_hash=digest(payload), defaults={
        'document': document, 'payload': payload})


def compare(first, second):
    if first.get('format_version') != 'extraction-observations-0.1' or second.get('format_version') != first['format_version']:
        raise ValueError('Both files must be extraction-observations-0.1 snapshots.')
    if not first.get('extraction_job_id') or first.get('extraction_job_id') == second.get('extraction_job_id'):
        raise ValueError('Independent extraction agreement requires different extraction jobs, not a replay of one job.')
    if first['input_hash'] != second['input_hash'] or digest(first['inputs']) != first['input_hash'] or digest(second['inputs']) != second['input_hash']:
        raise ValueError('Compare only identical source, reader output, prompt, schema and catalogue inputs.')
    if first.get('completeness') != 'complete' or second.get('completeness') != 'complete':
        raise ValueError('Independent-run agreement requires two complete extractions.')
    a, b = {identity(f) for f in first['facts']}, {identity(f) for f in second['facts']}
    categories = lambda rows: dict(sorted(Counter(canonical_type(f['field_key']) or 'additional_observation' for f in rows).items()))
    return {'first_facts': len(first['facts']), 'second_facts': len(second['facts']),
            'shared_observations': len(a & b), 'only_first': sorted(a - b), 'only_second': sorted(b - a),
            'observation_jaccard': len(a & b) / len(a | b) if a | b else None,
            'categories_first': categories(first['facts']), 'categories_second': categories(second['facts']),
            'same_models': first.get('models') == second.get('models'),
            'note': 'Agreement is not accuracy. Empty outputs do not establish agreement. '
                    'Use independent jobs; reusing completed chunks measures replay, not independent extraction.'}
