import mimetypes
import os

from django.utils import timezone

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


def create_document_from_file(*, sprint, file_obj, document_type, owner_role='', title='', uploaded_by=None):
    """Validate + persist a Document exactly like the manual upload endpoint
    (extension allowlist, size limit via MAX_DOCUMENT_UPLOAD_SIZE, SHA-256
    checksum dedupe-per-sprint, ocr_required flagging, status=UPLOADED,
    sprint DRAFT->COLLECTING).

    `file_obj` only needs to expose `.name` and `.size` (DRF's FileField.
    to_internal_value requirement) plus `.chunks()`/`.seek()` (used by
    compute_file_checksum) -- an HTTP multipart UploadedFile satisfies this,
    and so does `django.core.files.uploadedfile.SimpleUploadedFile` wrapping
    Drive-downloaded bytes, which is what the Drive-import task passes.

    Raises DocumentValidationError (never DRF's ValidationError) on any
    invalid input, so non-HTTP callers can catch it without needing a
    request/response cycle.
    """
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
        uploaded_by=uploaded_by,
        uploaded_at=timezone.now(),
    )
    mark_sprint_collecting(sprint)
    return document
