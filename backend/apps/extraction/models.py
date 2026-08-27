import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ExtractionJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        RETRYING = 'retrying', 'Retrying'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    #: The seven fixed processing stages every job moves through, in order.
    class Step(models.TextChoices):
        CLASSIFYING_DOCUMENTS = 'classifying_documents', 'Classifying Documents'
        READING_PAGES = 'reading_pages', 'Reading Pages'
        EXTRACTING_FACTS = 'extracting_facts', 'Extracting Facts'
        MAPPING_AUDIT_FIELDS = 'mapping_audit_fields', 'Mapping Audit Fields'
        DETECTING_GAPS = 'detecting_gaps', 'Detecting Gaps'
        CHECKING_CONFLICTS = 'checking_conflicts', 'Checking Conflicts'
        PREPARING_REVIEW_WORKSPACE = 'preparing_review_workspace', 'Preparing Review Workspace'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='extraction_jobs')
    document = models.ForeignKey(
        'documents.Document', on_delete=models.CASCADE, related_name='extraction_jobs',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    current_step = models.CharField(max_length=40, choices=Step.choices, blank=True)
    progress_percentage = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    celery_task_id = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'ExtractionJob({self.id}) — {self.status}'
