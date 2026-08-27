import logging

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanManageSprint, IsInstitutionMember
from apps.sprints.access import get_authorized_sprint

from .models import Report
from .serializers import ReportListSerializer, ReportSerializer
from .services import next_report_version
from .tasks import generate_report_task

logger = logging.getLogger(__name__)


def _create_and_dispatch_report(request, sprint_id):
    """Creates the next-versioned Report row and dispatches generation --
    shared by the dedicated .../generate/ endpoint and the list endpoint's
    POST (kept working for the existing, unmodified frontend, which posts
    to the plain .../reports URL)."""
    sprint = get_authorized_sprint(request.user, sprint_id)
    report = Report.objects.create(
        sprint=sprint, version=next_report_version(sprint),
        generated_by=request.user if request.user.is_authenticated else None,
    )
    try:
        generate_report_task.delay(str(report.id))
        # With CELERY_TASK_ALWAYS_EAGER (tests, or a synchronous worker
        # setup), `.delay()` runs the task inline against a separately
        # fetched row -- reload so the response reflects what actually
        # happened, not this stale in-memory copy from right after create().
        report.refresh_from_db()
    except Exception as exc:
        logger.error('reports.dispatch.broker_unreachable report_id=%s error=%s', report.id, exc)
        report.status = Report.Status.FAILED
        report.report_data = {'error': f'Could not reach the Celery broker: {exc}'}
        report.save(update_fields=['status', 'report_data', 'updated_at'])
    return Response(ReportSerializer(report).data, status=202)


class SprintReportListView(APIView):
    """GET the sprint's report history (version-descending). POST also
    triggers generation here, in addition to the dedicated .../generate/
    endpoint below, since that's the URL the existing, unmodified
    frontend's ReportPreviewExport.tsx already posts to."""
    permission_classes = [CanManageSprint]

    @extend_schema(responses=ReportListSerializer(many=True))
    def get(self, request, sprint_id):
        get_authorized_sprint(request.user, sprint_id)
        reports = Report.objects.filter(sprint_id=sprint_id)
        return Response(ReportListSerializer(reports, many=True).data)

    @extend_schema(request=None, responses=ReportSerializer)
    def post(self, request, sprint_id):
        return _create_and_dispatch_report(request, sprint_id)


class SprintReportGenerateView(APIView):
    """POST /sprints/{sprint_id}/reports/generate/ -- creates a new report
    at the sprint's next version number and dispatches generation
    asynchronously via Celery. The response's `status` (draft/generating in
    a real deployment, likely already ready/failed under
    CELERY_TASK_ALWAYS_EAGER) is what a caller polls GET
    .../reports/{id}/ to track."""
    permission_classes = [CanManageSprint]

    @extend_schema(request=None, responses=ReportSerializer)
    def post(self, request, sprint_id):
        return _create_and_dispatch_report(request, sprint_id)


class ReportDetailView(generics.RetrieveAPIView):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    lookup_field = 'pk'
    permission_classes = [IsInstitutionMember]


class ReportDownloadView(APIView):
    """Streams the report's rendered PDF (default) or DOCX (?file=docx)
    file, gated on the same institution-membership check as document
    downloads (apps.documents.views.DocumentDownloadView) -- never a raw,
    unauthenticated media URL.

    Deliberately `?file=` rather than `?format=`: DRF reserves `format` as
    its own content-negotiation query parameter (URL_FORMAT_OVERRIDE), so
    `?format=docx` would be intercepted by DRF's renderer selection before
    ever reaching this view instead of picking the DOCX file.
    """
    permission_classes = [IsInstitutionMember]

    @extend_schema(responses={200: OpenApiResponse(OpenApiTypes.BINARY, description='The rendered PDF/DOCX file.')})
    def get(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        self.check_object_permissions(request, report)

        file_format = request.query_params.get('file', 'pdf').lower()
        if file_format not in ('pdf', 'docx'):
            raise NotFound("file must be 'pdf' or 'docx'.")
        file_field = report.pdf_file if file_format == 'pdf' else report.docx_file

        if report.status != Report.Status.READY or not file_field:
            raise NotFound('This report is not ready for download yet.')

        content_type = (
            'application/pdf' if file_format == 'pdf'
            else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        return FileResponse(
            file_field.open('rb'), as_attachment=True,
            filename=f'{report.sprint.sprint_code}_report_v{report.version}.{file_format}',
            content_type=content_type,
        )
