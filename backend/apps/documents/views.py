import logging
import os

from celery.exceptions import Retry as CeleryRetry
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import CanContribute, IsInstitutionMember
from apps.sprints.access import get_authorized_sprint

from .models import Document, DriveImportJob
from .serializers import (
    DocumentCategoryConfirmSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
    DriveImportJobCreateSerializer,
    DriveImportJobSerializer,
)
from .services import DocumentValidationError, create_document_from_file
from .tasks import run_drive_import_job

logger = logging.getLogger(__name__)

#: Roles that may manage (edit/delete) a document someone else uploaded.
#: Anyone who isn't a read-only viewer can still edit their *own* upload;
#: deleting someone else's requires one of these roles.
DOCUMENT_MANAGE_ROLES = {
    User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.INSTITUTION_ADMIN, User.Role.IQAC_COORDINATOR,
}


class CanManageDocument(BasePermission):
    message = 'You do not have permission to modify this document.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        is_owner = obj.uploaded_by_id == user.id
        if request.method == 'DELETE':
            return is_owner or user.role in DOCUMENT_MANAGE_ROLES
        return is_owner or user.role != User.Role.VIEWER


class SprintDocumentListView(generics.ListAPIView):
    """Read-only: documents are only ever created through the upload endpoint."""
    serializer_class = DocumentSerializer

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return Document.objects.filter(sprint_id=self.kwargs['sprint_id']).select_related('category_confirmed_by')


class SprintDocumentUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [CanContribute]

    @extend_schema(request=DocumentUploadSerializer, responses=DocumentSerializer)
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        try:
            document = create_document_from_file(
                sprint=sprint,
                file_obj=request.data.get('file'),
                document_type=request.data.get('document_type', ''),
                owner_role=request.data.get('owner_role', ''),
                title=request.data.get('title', ''),
                uploaded_by=request.user,
            )
        except DocumentValidationError as exc:
            raise DRFValidationError(exc.errors)
        return Response(DocumentSerializer(document, context={'request': request}).data, status=201)


class SprintDriveImportJobListCreateView(generics.ListCreateAPIView):
    """Google Drive Link data source for Screen 2 "Upload Data Pack": scans a
    publicly link-shared Drive folder, classifies its files against the
    required checklist, and imports matches through the same
    create_document_from_file() path as a manual upload -- see
    apps.documents.tasks.run_drive_import_job."""
    permission_classes = [CanContribute]
    serializer_class = DriveImportJobSerializer

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return DriveImportJob.objects.filter(sprint_id=self.kwargs['sprint_id'])

    @extend_schema(request=DriveImportJobCreateSerializer, responses=DriveImportJobSerializer)
    def create(self, request, *args, **kwargs):
        sprint = get_authorized_sprint(request.user, self.kwargs['sprint_id'])
        body = DriveImportJobCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        job = DriveImportJob.objects.create(
            sprint=sprint, drive_url=body.validated_data['drive_url'], created_by=request.user,
        )
        try:
            result = run_drive_import_job.delay(str(job.id))
            job.celery_task_id = result.id
            job.save(update_fields=['celery_task_id'])
            # With CELERY_TASK_ALWAYS_EAGER, the line above just ran the task
            # inline against a separately-fetched row -- reload so the
            # response reflects what actually happened.
            job.refresh_from_db()
        except CeleryRetry:
            # Only reachable with CELERY_TASK_ALWAYS_EAGER (tests), where
            # .delay() runs the task inline and it already recorded the
            # retry before raising this.
            job.refresh_from_db()
        except Exception as exc:
            logger.error('documents.drive_import.dispatch.broker_unreachable job_id=%s error=%s', job.id, exc)
            job.status = DriveImportJob.Status.FAILED
            job.error_message = f'Could not reach the Celery broker: {exc}'
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        return Response(DriveImportJobSerializer(job).data, status=201)


class SprintDriveImportJobStopView(APIView):
    """POST: stop a running Drive import. The worker checks between files,
    so documents already imported stay; nothing further is imported."""
    permission_classes = [CanContribute]

    @extend_schema(request=None, responses=DriveImportJobSerializer)
    def post(self, request, sprint_id, job_id):
        get_authorized_sprint(request.user, sprint_id)
        job = get_object_or_404(DriveImportJob, id=job_id, sprint_id=sprint_id)
        now = timezone.now()
        stopped = DriveImportJob.objects.filter(
            id=job.id, status__in=DriveImportJob.ACTIVE_STATUSES,
        ).update(status=DriveImportJob.Status.CANCELLED, completed_at=now, updated_at=now)
        if not stopped:
            raise DRFValidationError({'detail': f'This import is already {job.status}; there is nothing to stop.'})
        logger.info('documents.drive_import.stop_requested job_id=%s user=%s', job.id, request.user.id)
        job.refresh_from_db()
        return Response(DriveImportJobSerializer(job).data)


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    lookup_field = 'pk'
    permission_classes = [CanManageDocument, IsInstitutionMember]

    def perform_destroy(self, instance):
        # Evidence submitted for an evidence request stays (it is part of that request's audit trail).
        if instance.evidence_links.exists():
            raise DRFValidationError({'detail': 'This document was submitted as evidence for an evidence request '
                                                'and cannot be deleted.'})
        if instance.file:
            instance.file.delete(save=False)
        instance.delete()


class DocumentConfirmCategoryView(APIView):
    """POST {"category": "<checklist slug>" | null}: a person settles the
    document's category -- resolving "Needs review" / "Unclassified", or
    overriding the AI. Sets classification_status (classified, or unclassified
    for null) and ai_document_type, and records who and when; the AI's own
    ai_confidence/ai_reasoning are kept as its last verdict. Reprocessing
    leaves a confirmed category alone (ExtractionPipeline._apply_classification).
    Who may: anyone but a viewer, in the document's institution -- the same as
    editing it."""
    permission_classes = [CanContribute, CanManageDocument, IsInstitutionMember]

    @extend_schema(request=DocumentCategoryConfirmSerializer, responses=DocumentSerializer)
    def post(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(request, document)
        body = DocumentCategoryConfirmSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        category = body.validated_data['category']

        Status = Document.ClassificationStatus
        document.classification_status = Status.CLASSIFIED if category else Status.UNCLASSIFIED
        document.ai_document_type = category or ''
        document.category_confirmed_by = request.user
        document.category_confirmed_at = timezone.now()
        document.save(update_fields=[
            'classification_status', 'ai_document_type', 'category_confirmed_by', 'category_confirmed_at',
            'updated_at',
        ])
        logger.info(
            'documents.category_confirmed document_id=%s category=%s user=%s',
            document.id, category, request.user.id,
        )
        # A reviewed document is what settles a "missing document" gap for its type and a "stale data"
        # gap on an older one (apps.gaps.services.after_document_review).
        from apps.gaps.services import after_document_review
        after_document_review(document, user=request.user)
        return Response(DocumentSerializer(document, context={'request': request}).data)


class DocumentDownloadView(APIView):
    """Streams the file through Django's storage backend, gated on the same
    institution-membership check as everything else -- never a raw,
    unauthenticated media URL."""
    permission_classes = [IsInstitutionMember]

    @extend_schema(responses={200: OpenApiResponse(OpenApiTypes.BINARY, description='The document file.')})
    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(request, document)
        if not document.file:
            raise NotFound('This document has no stored file to download.')
        return FileResponse(
            document.file.open('rb'),
            as_attachment=True,
            filename=document.original_filename or os.path.basename(document.file.name),
            content_type=document.mime_type or 'application/octet-stream',
        )
