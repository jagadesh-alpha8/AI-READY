import mimetypes
import os

from django.utils import timezone
from django.db import transaction

from apps.sprints.models import Sprint

from .constants import OCR_REQUIRED_EXTENSIONS
from .models import Document
from .serializers import DocumentUploadSerializer


class DocumentValidationError(Exception):
    """Wraps a DocumentUploadSerializer validation failure for non-HTTP
    callers (the Drive-import Celery task) that need to catch it and decide
    what to do (skip-and-record-reason) instead of DRF's
    raise_exception=True -> 400 response path, which assumes a request/
    response cycle."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


def mark_sprint_collecting(sprint):
    if sprint.status == Sprint.Status.DRAFT:
        sprint.status = Sprint.Status.COLLECTING
        sprint.save(update_fields=['status', 'updated_at'])


def create_document_from_file(
    *, sprint, file_obj, document_type, owner_role='', title='', uploaded_by=None,
    document_type_source=Document.TypeSource.UPLOADER,
):
    """Validate + persist a Document exactly like the manual upload endpoint
    (extension allowlist, size limit via MAX_DOCUMENT_UPLOAD_SIZE, SHA-256
    checksum dedupe-per-sprint, ocr_required flagging, status=UPLOADED,
    sprint DRAFT->COLLECTING).

    `document_type_source` records who set `document_type` (the uploader, or
    the Drive importer's filename keywords) -- the AI's own category is
    saved separately once extraction classifies the content.

    `file_obj` only needs to expose `.name` and `.size` (DRF's FileField.
    to_internal_value requirement) plus `.chunks()`/`.seek()` (used by
    compute_file_checksum) -- an HTTP multipart UploadedFile satisfies this,
    and so does `django.core.files.uploadedfile.SimpleUploadedFile` wrapping
    Drive-downloaded bytes, which is what the Drive-import task passes.

    Raises DocumentValidationError (never DRF's ValidationError) on any
    invalid input, so non-HTTP callers can catch it without needing a
    request/response cycle.
    """
    # Lock the sprint while checking its checksum set and version chain. This
    # makes two concurrent uploads of the same bytes in one sprint resolve to
    # one accepted upload plus one clear duplicate error instead of racing the
    # per-sprint unique checksum constraint.
    with transaction.atomic():
        sprint = Sprint.objects.select_for_update().get(pk=sprint.pk)
        serializer = DocumentUploadSerializer(
            data={'file': file_obj, 'document_type': document_type, 'owner_role': owner_role, 'title': title},
            context={'sprint': sprint},
        )
        if not serializer.is_valid():
            raise DocumentValidationError(serializer.errors)
        data = serializer.validated_data

        ext = os.path.splitext(file_obj.name)[1].lower()
        mime_type = (
            getattr(file_obj, 'content_type', None)
            or mimetypes.guess_type(file_obj.name)[0]
            or 'application/octet-stream'
        )

        # A changed file with the same name starts the next version in THIS
        # sprint. Equal content is rejected above, regardless of filename.
        previous = (Document.objects.filter(sprint=sprint, original_filename__iexact=file_obj.name,
                                            superseded_at__isnull=True)
                    .order_by('-version_number', '-created_at').first())

        document = Document.objects.create(
            sprint=sprint,
            previous_version=previous,
            version_number=(previous.version_number + 1) if previous else 1,
            document_type=data['document_type'],
            document_type_source=document_type_source,
            title=data['title'],
            owner_role=data['owner_role'],
            original_filename=file_obj.name,
            file=file_obj,
            mime_type=mime_type,
            file_size=file_obj.size,
            checksum=data['checksum'],
            ocr_required=ext in OCR_REQUIRED_EXTENSIONS,
            status=Document.Status.UPLOADED,
            uploaded_by=uploaded_by,
            uploaded_at=timezone.now(),
        )
        if previous is not None:
            # Kept, with its facts and reviews, as the earlier version; the new one is processed afresh.
            previous.superseded_at = document.uploaded_at
            previous.save(update_fields=['superseded_at', 'updated_at'])
        mark_sprint_collecting(sprint)
    return document
