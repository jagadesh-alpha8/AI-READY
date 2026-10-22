"""Background AI assessment of text submissions and already-processed documents."""
import logging

from celery import shared_task
from django.conf import settings

from apps.extraction.services.router_pool import get_router_pool, use_lease
from apps.extraction.services.pdf_reader import PDFPageReader

from .evidence_analysis import analyze_submission
from .models import EvidenceRequestDocument

logger = logging.getLogger(__name__)


def _run_with_router(link, callback):
    pool = None
    lease = None
    try:
        pool = get_router_pool()
        if pool is not None:
            lease = pool.acquire()
        with use_lease(lease):
            return callback()
    except Exception as exc:
        logger.exception('evidence.task.failed evidence_id=%s', link.id)
        from .evidence_analysis import _fail
        return _fail(link, str(exc))
    finally:
        if lease is not None:
            pool.release(lease)


@shared_task(bind=True, max_retries=settings.EXTRACTION_MAX_RETRIES, acks_late=True)
def analyze_text_evidence_submission(self, evidence_id):
    link = EvidenceRequestDocument.objects.select_related('request__fact', 'request__sprint').filter(
        pk=evidence_id, document__isnull=True,
    ).first()
    if link is None:
        return None
    return _run_with_router(link, lambda: analyze_submission(link))


@shared_task(bind=True, max_retries=settings.EXTRACTION_MAX_RETRIES, acks_late=True)
def analyze_existing_document_evidence(self, evidence_id):
    link = EvidenceRequestDocument.objects.select_related('request__fact', 'request__sprint', 'document').filter(
        pk=evidence_id, document__isnull=False,
    ).first()
    if link is None:
        return None

    def read_and_analyze():
        pages = PDFPageReader().read_pages(link.document)
        return analyze_submission(link, pages=pages)

    return _run_with_router(link, read_and_analyze)
