import uuid

from django.conf import settings
from django.core.validators import RegexValidator
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=100, validators=[document_type_validator])
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
