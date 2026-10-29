"""What one extraction job is doing right now, in words the AI Processing Monitor shows -- from the job row's own
fields only (status, step, page / chunk counters, last attempt). Pipeline progress and document completeness
are kept apart: a job that reached its last stage but skipped pages or chunks is "partial", never "completed".

    queued              pending: in the queue, waiting for a free worker
    reading_pages       pages being read (text layer / OCR), with pages done / total and OCR pages
    classifying         the first AI request: what the document is (+ its first chunk's facts)
    extracting_facts    AI fact extraction, with chunks done / total
    finishing           mapping, gaps, conflicts, review workspace
    continuing          a large document: this attempt's share of chunks is saved, the next starts now
    retrying            a recoverable error; the next attempt is scheduled (next_retry_at)
    waiting_for_router  multi-router mode: every router is out of credit / tried; checked again later
    completed           finished and everything was read
    partial             finished, but pages or chunks were not read (see extraction_warnings)
    failed / stopped
"""
from urllib.parse import urlsplit

from django.conf import settings

from ..models import ExtractionJob

S, Step = ExtractionJob.Status, ExtractionJob.Step

LABELS = {
    'queued': 'Queued, waiting for a worker',
    'reading_pages': 'Reading pages',
    'classifying': 'Classifying the document',
    'extracting_facts': 'Extracting facts',
    'finishing': 'Finishing',
    'continuing': 'Continuing with the rest of the document',
    'retrying': 'Retrying',
    'waiting_for_router': 'Waiting for an AI router',
    'completed': 'Completed',
    'partial': 'Partial: some pages or chunks were not read',
    'failed': 'Failed',
    'stopped': 'Stopped',
}


def phase(job):
    if job.status == S.CANCELLED:
        return 'stopped'
    if job.status == S.FAILED:
        return 'failed'
    if job.status == S.COMPLETED:
        return 'partial' if job.completeness == ExtractionJob.Completeness.PARTIAL else 'completed'
    last = ((job.attempts or [{}])[-1] or {}).get('outcome')
    if job.status == S.RETRYING:
        return {'waiting': 'waiting_for_router', 'continued': 'continuing'}.get(last, 'retrying')
    reading = job.pages_total and job.pages_done < job.pages_total
    if job.status == S.PENDING:
        return 'reading_pages' if job.current_step == Step.READING_PAGES and job.heartbeat_at else 'queued'
    # running
    if reading or job.current_step in ('', Step.CLASSIFYING_DOCUMENTS) and not job.pages_total:
        return 'reading_pages'
    if job.current_step in (Step.CLASSIFYING_DOCUMENTS, Step.READING_PAGES):
        return 'classifying'
    if job.current_step == Step.EXTRACTING_FACTS:
        return 'extracting_facts'
    return 'finishing'


def phase_label(job, name=None):
    name = name or phase(job)
    label = LABELS[name]
    if name == 'reading_pages' and job.pages_total:
        label += f' {job.pages_done} of {job.pages_total}'
        parts = []
        if job.ocr_pages:
            parts.append(f'{job.ocr_pages} by OCR')
        if getattr(job, 'vision_pages', 0):
            parts.append(f'{job.vision_pages} by vision')
        if parts:
            label += f' ({" + ".join(parts)})'
    elif name == 'extracting_facts' and job.chunks_total:
        label += f': {job.chunks_completed} of {job.chunks_total} chunks'
    elif name == 'continuing' and job.chunks_total:
        label += f' ({job.chunks_completed} of {job.chunks_total} chunks done)'
    elif name == 'finishing' and job.current_step:
        label += f': {job.get_current_step_display()}'
    elif name == 'partial' and job.chunks_total and job.chunks_completed < job.chunks_total:
        label += f' ({job.chunks_completed} of {job.chunks_total} chunks read)'
    return label


def provider_label(job):
    """Where this job's AI calls go, without any key: 'single provider: api.openai.com, gpt-4o' or
    'router2 (localhost:20229), qwen'. Single-provider mode is not a router, and never shown as 'no router'."""
    from config.ai_processing_mode import MULTI_ROUTER
    from .processing_status import router_model
    from .router_pool import processing_mode

    if processing_mode() == MULTI_ROUTER:
        return f'{job.ai_router or "router pool"}, {router_model() or "model not set"}'
    endpoint = urlsplit(settings.AI_BASE_URL).netloc if settings.AI_BASE_URL else 'provider API'
    model = settings.AI_MODEL or settings.OPENAI_EXTRACTION_MODEL or 'provider default model'
    return f'single provider: {endpoint}, {model}'
