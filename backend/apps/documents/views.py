import mimetypes
import os

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsInstitutionMember
from apps.sprints.access import get_authorized_sprint
from apps.sprints.models import Sprint

from .constants import OCR_REQUIRED_EXTENSIONS
from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer

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


def _mark_sprint_collecting(sprint):
    if sprint.status == Sprint.Status.DRAFT:
        sprint.status = Sprint.Status.COLLECTING
        sprint.save(update_fields=['status', 'updated_at'])


class SprintDocumentListView(generics.ListAPIView):
    """Read-only: documents are only ever created through the upload endpoint."""
    serializer_class = DocumentSerializer

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return Document.objects.filter(sprint_id=self.kwargs['sprint_id'])


class SprintDocumentUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=DocumentUploadSerializer, responses=DocumentSerializer)
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)
        upload = DocumentUploadSerializer(data=request.data, context={'sprint': sprint})
        upload.is_valid(raise_exception=True)
        data = upload.validated_data
        file_obj = data['file']

        ext = os.path.splitext(file_obj.name)[1].lower()
        mime_type = file_obj.content_type or mimetypes.guess_type(file_obj.name)[0] or 'application/octet-stream'

        document = Document.objects.create(
            sprint=sprint,
            document_type=data['document_type'],
            title=data['title'],
            owner_role=data['owner_role'],
            original_filename=file_obj.name,
            file=file_obj,
            mime_type=mime_type,
            file_size=file_obj.size,
            checksum=data['checksum'],
            ocr_required=ext in OCR_REQUIRED_EXTENSIONS,
            status=Document.Status.UPLOADED,
            uploaded_by=request.user,
            uploaded_at=timezone.now(),
        )
        _mark_sprint_collecting(sprint)
        return Response(DocumentSerializer(document, context={'request': request}).data, status=201)


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    lookup_field = 'pk'
    permission_classes = [CanManageDocument, IsInstitutionMember]

    def perform_destroy(self, instance):
        if instance.file:
            instance.file.delete(save=False)
        instance.delete()


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
