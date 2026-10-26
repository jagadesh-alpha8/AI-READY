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
        from .evidence_analysis import _fail, readable_error
        logger.warning('evidence.task.failed evidence_id=%s error=%s', link.id, readable_error(exc))
        logger.debug('evidence.task.failed evidence_id=%s', link.id, exc_info=True)
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


@shared_task(acks_late=True, ignore_result=True)
def retry_evidence_assessment(evidence_id):
    """One reviewer-requested retry of a failed AI assessment (evidence_requests.request_assessment_retry). It reuses
    the submission's saved page text or pasted text -- no document read, OCR or extraction when the text was read
    before -- and never retries by itself: a failure is recorded for the reviewer, who may retry again."""
    link = EvidenceRequestDocument.objects.select_related('request__fact', 'request__sprint', 'document').filter(
        pk=evidence_id, analysis_status=EvidenceRequestDocument.AnalysisStatus.PENDING,
    ).first()
    if link is None:  # already picked up, decided or gone: nothing to do (a repeated delivery is harmless)
        return None
    return _run_with_router(link, lambda: analyze_submission(link))


@shared_task(acks_late=True)
def run_aiqif_auto_check(sprint_id):
    """The AI second opinion on a sprint's waiting AI-QIF tags (aiqif_tagging.auto_check_sprint), on a router
    slot in multi-router mode, then a CRI recalculation so coverage follows."""
    from apps.scoring.services import run_scoring_engine
    from apps.sprints.models import Sprint

    from .aiqif_tagging import auto_check_sprint
    sprint = Sprint.objects.filter(pk=sprint_id).first()
    if sprint is None:
        return None
    pool = lease = None
    try:
        pool = get_router_pool()
        if pool is not None:
            lease = pool.acquire()
        with use_lease(lease):
            result = auto_check_sprint(sprint, ai=True)
        run_scoring_engine(sprint)
        logger.info('aiqif.auto_check sprint=%s result=%s', sprint_id, result)
        return result
    except Exception:
        logger.exception('aiqif.auto_check_failed sprint=%s', sprint_id)
        return None
    finally:
        if lease is not None:
            pool.release(lease)
