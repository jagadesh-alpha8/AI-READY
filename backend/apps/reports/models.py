import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from .utils import report_docx_upload_path, report_pdf_upload_path


class Report(models.Model):
    """One generated AIOS Discovery Report for a sprint.

    Versioned rather than overwritten: `generate_report_for_sprint`
    (apps.reports.services) always inserts a new row with the next
    `version` number for that sprint, so a historical report stays exactly
    as it was even after the sprint's underlying data changes and someone
    regenerates. `report_data` is the full structured document (the 11
    sections in apps.reports.services.build_report_data); executive_summary/
    overall_cri/confidence_score are pulled out as their own columns purely
    so the common "list reports" / "show headline numbers" case doesn't need
    to unpack that JSON blob.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        GENERATING = 'generating', 'Generating'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='reports')
    #: Sequential per sprint (1, 2, 3, ...) -- assigned once at creation
    #: (see services.create_report_for_sprint) and never reused.
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    executive_summary = models.TextField(blank=True)
    overall_cri = models.FloatField(default=0)
    confidence_score = models.FloatField(default=0)
    generated_at = models.DateTimeField(null=True, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    pdf_file = models.FileField(upload_to=report_pdf_upload_path, blank=True, null=True, max_length=500)
    docx_file = models.FileField(upload_to=report_docx_upload_path, blank=True, null=True, max_length=500)
    #: The full structured report (all 11 sections) -- see
    #: apps.reports.services.build_report_data for its exact shape.
    report_data = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-version']
        constraints = [
            models.UniqueConstraint(fields=['sprint', 'version'], name='unique_report_version_per_sprint'),
        ]

    def __str__(self):
        return f'Report({self.sprint_id}) v{self.version} — {self.status}'
