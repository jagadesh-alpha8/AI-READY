import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

from .rendering import render_docx_bytes, render_pdf_bytes
from .services import build_report_data

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def generate_report_task(self, report_id):
    """Build one report's data + PDF/DOCX files.

    No retries: unlike apps.extraction.tasks.run_extraction_job (which
    drives an inherently flaky OCR/extraction pipeline over external
    documents), this reads already-persisted, already-validated sprint data
    and renders it -- a failure here is a real bug to surface immediately,
    not a transient condition worth retrying blindly.
    """
    from .models import Report

    try:
        report = Report.objects.select_related('sprint', 'sprint__institution').get(id=report_id)
    except Report.DoesNotExist:
        logger.error('reports.task.missing_report report_id=%s', report_id)
        return None

    report.status = Report.Status.GENERATING
    report.save(update_fields=['status', 'updated_at'])
    logger.info('reports.task.generating report_id=%s sprint_id=%s', report.id, report.sprint_id)

    try:
        data = build_report_data(report.sprint)
        report.report_data = data
        report.executive_summary = data['executive_summary']
        report.overall_cri = data['overall_cri']
        report.confidence_score = data['confidence_score']

        pdf_bytes = render_pdf_bytes(report)
        docx_bytes = render_docx_bytes(report)
    except Exception as exc:
        logger.exception('reports.task.failed report_id=%s', report.id)
        report.status = Report.Status.FAILED
        report.report_data = {**report.report_data, 'error': str(exc)}
        report.save(update_fields=['status', 'report_data', 'updated_at'])
        return None

    report.pdf_file.save(f'{report.id}_v{report.version}.pdf', ContentFile(pdf_bytes), save=False)
    report.docx_file.save(f'{report.id}_v{report.version}.docx', ContentFile(docx_bytes), save=False)
    report.status = Report.Status.READY
    report.generated_at = timezone.now()
    report.save(update_fields=[
        'status', 'report_data', 'executive_summary', 'overall_cri', 'confidence_score',
        'pdf_file', 'docx_file', 'generated_at', 'updated_at',
    ])
    logger.info('reports.task.ready report_id=%s', report.id)

    _advance_sprint_if_ready(report.sprint)
    return str(report.id)


def _advance_sprint_if_ready(sprint):
    from apps.sprints.models import Sprint

    # A report can be generated at any baseline stage (see
    # apps.reports.services.build_report_data's baseline_status labeling --
    # "preliminary"/"provisional"/"approved" reports are all valid), but the
    # sprint itself only auto-advances to REPORT_READY once its baseline has
    # actually been decided (BASELINE_APPROVED covers both a full and a
    # provisional approval -- apps.scoring.services.baseline sets the same
    # sprint status for both, distinguishing them via Baseline.status
    # instead). Generating a report earlier (e.g. still at SCORING) still
    # works and still produces a real file -- it just doesn't skip the
    # baseline-approval stage of the pipeline by itself.
    if sprint.status == Sprint.Status.BASELINE_APPROVED:
        sprint.status = Sprint.Status.REPORT_READY
        sprint.save(update_fields=['status', 'updated_at'])
