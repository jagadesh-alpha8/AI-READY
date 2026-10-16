import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from .utils import document_upload_path

document_type_validator = RegexValidator(
    regex=r'^[a-z][a-z0-9_]*$',
    message='Document type must be a lowercase snake_case identifier, e.g. "naac_ssr".',
)


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        UPLOADED = 'uploaded', 'Uploaded'
        PROCESSING = 'processing', 'Processing'
        PROCESSED = 'processed', 'Processed'
        FAILED = 'failed', 'Failed'
        REJECTED = 'rejected', 'Rejected'

    class TypeSource(models.TextChoices):
        """Who set `document_type`."""
        UPLOADER = 'uploader', 'Chosen by uploader'
        FILENAME = 'filename', 'Filename keyword match'
        NONE = 'none', 'No type assigned'

    class ClassificationStatus(models.TextChoices):
        """Outcome of the AI classifier reading the document's content."""
        PENDING = 'pending', 'Not yet categorized'
        CLASSIFIED = 'classified', 'Classified'
        NEEDS_REVIEW = 'needs_review', 'Needs review'
        UNCLASSIFIED = 'unclassified', 'Unclassified'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='documents')
    # The type assigned at upload/import -- never overwritten by the AI, so
    # the original label stays auditable. Gaps, scoring and the vector store
    # keep reading this field; the AI's verdict lives in the ai_* fields.
    document_type = models.CharField(max_length=100, validators=[document_type_validator])
    document_type_source = models.CharField(
        max_length=20, choices=TypeSource.choices, default=TypeSource.UPLOADER,
    )
    # Set by the extraction pipeline's classification step, from the
    # document's content (see apps.extraction.services.openai_classifier).
    # `ai_document_type` is always a checklist slug
    # (apps.documents.constants.CHECKLIST_TYPE_LABELS) or ''; only a
    # CLASSIFIED result counts toward the Upload Data Pack checklist.
    classification_status = models.CharField(
        max_length=20, choices=ClassificationStatus.choices, default=ClassificationStatus.PENDING,
    )
    ai_document_type = models.CharField(max_length=100, blank=True)
    ai_confidence = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    ai_reasoning = models.TextField(blank=True)
    classified_at = models.DateTimeField(null=True, blank=True)
    # Set when a person decides the category (POST /documents/{id}/confirm-category):
    # classification_status/ai_document_type then hold their decision, and
    # reprocessing leaves it alone. ai_confidence/ai_reasoning/classified_at
    # stay as the AI's last verdict, for the record.
    category_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    category_confirmed_at = models.DateTimeField(null=True, blank=True)
    title = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to=document_upload_path, blank=True, null=True, max_length=500)
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=150, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    checksum = models.CharField(max_length=64, blank=True, db_index=True, help_text='SHA-256 hex digest')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    owner_role = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    quality_score = models.FloatField(null=True, blank=True)
    ocr_required = models.BooleanField(default=False)
    ocr_warnings = models.JSONField(default=list, blank=True)
    # Free-text, not an enum: fine-grained sub-stage reporting for the (not
    # yet built) extraction pipeline -- e.g. "ocr_queued", "classifying" --
    # kept separate from `status` so the pipeline can narrate progress
    # without the document ever leaving `status=processing`.
    processing_status = models.CharField(max_length=100, blank=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['sprint', 'checksum'],
                condition=~models.Q(checksum=''),
                name='unique_document_checksum_per_sprint',
            ),
        ]

    def __str__(self):
        return self.title or self.original_filename or str(self.id)

    @property
    def category_manually_confirmed(self):
        """A person, not the AI, decided this document's category."""
        return self.category_confirmed_at is not None


class DriveImportJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SCANNING = 'scanning', 'Scanning'
        DOWNLOADING = 'downloading', 'Downloading'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        # Stopped by the user mid-scan; files already imported are kept.
        CANCELLED = 'cancelled', 'Cancelled'

    ACTIVE_STATUSES = (Status.PENDING, Status.SCANNING, Status.DOWNLOADING)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='drive_import_jobs')
    drive_url = models.URLField(max_length=500)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # {"<DRIVE_IMPORT_CHECKLIST type>": {"status": "found"|"missing", "filename":
    # str|None, "document_id": str|None}, ..., "unmatched_files": [str, ...],
    # "skipped_files": [{"filename": str, "reason": str}, ...]}
    results = models.JSONField(default=dict, blank=True)
    files_scanned = models.PositiveIntegerField(default=0)
    files_imported = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'DriveImportJob({self.id}) — {self.status}'
