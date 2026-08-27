import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.scoring.constants import PILLAR_CHOICES


class ExtractedFact(models.Model):
    class Status(models.TextChoices):
        EXTRACTED = 'extracted', 'Extracted'
        CONFIRMED = 'confirmed', 'Confirmed'
        CORRECTED = 'corrected', 'Corrected'
        REJECTED = 'rejected', 'Rejected'
        EVIDENCE_REQUESTED = 'evidence_requested', 'Evidence Requested'

    class DataType(models.TextChoices):
        STRING = 'string', 'String'
        NUMBER = 'number', 'Number'
        PERCENTAGE = 'percentage', 'Percentage'
        BOOLEAN = 'boolean', 'Boolean'
        DATE = 'date', 'Date'
        CURRENCY = 'currency', 'Currency'
        LIST = 'list', 'List'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='facts')
    # The document this fact was extracted from during processing (set once,
    # by the pipeline). `source_document` below is the *current* evidence
    # citation for the value, which a correction can point at a different
    # document without rewriting the extraction lineage.
    document = models.ForeignKey(
        'documents.Document', on_delete=models.SET_NULL, null=True, blank=True, related_name='extracted_facts',
    )
    field_name = models.CharField(max_length=255)
    field_key = models.CharField(max_length=150)
    # Nullable: a correction can legitimately set a fact to "unknown"/null
    # rather than a value -- see FactCorrectSerializer's explicit-null case.
    value = models.JSONField(null=True, blank=True)
    normalized_value = models.JSONField(null=True, blank=True)
    data_type = models.CharField(max_length=20, choices=DataType.choices, default=DataType.STRING)
    pillar = models.CharField(max_length=64, choices=PILLAR_CHOICES, blank=True)
    owner_role = models.CharField(max_length=50, blank=True)
    source_document = models.ForeignKey(
        'documents.Document', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    source_page = models.CharField(max_length=50, blank=True)
    source_snippet = models.TextField(blank=True)
    confidence_score = models.FloatField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    confidence_reason = models.TextField(blank=True)
    extraction_method = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EXTRACTED)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.field_key} ({self.status})'


class FactReviewHistory(models.Model):
    """One row per review action taken on a Fact -- confirm, correct, reject,
    or request-evidence. `original_value` is always the fact's value
    immediately before this action, so the full chain of history rows
    reconstructs everything a fact has ever been, all the way back to what
    was first extracted; nothing is ever overwritten or discarded.
    """
    class Action(models.TextChoices):
        CONFIRMED = 'confirmed', 'Confirmed'
        CORRECTED = 'corrected', 'Corrected'
        REJECTED = 'rejected', 'Rejected'
        EVIDENCE_REQUESTED = 'evidence_requested', 'Evidence Requested'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fact = models.ForeignKey(ExtractedFact, on_delete=models.CASCADE, related_name='review_history')
    action = models.CharField(max_length=20, choices=Action.choices)
    # Both nullable: `original_value` mirrors whatever `fact.value` was at
    # the time (itself nullable -- see ExtractedFact.value), and `new_value`
    # is unset for confirm/reject/evidence-request, or an explicit null for
    # a correction that sets the fact to "unknown".
    original_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Fact review histories'

    def __str__(self):
        return f'{self.fact_id} — {self.action}'
