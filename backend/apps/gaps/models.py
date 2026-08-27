import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.scoring.constants import PILLAR_CHOICES


class GapItem(models.Model):
    class GapType(models.TextChoices):
        MISSING_DOCUMENT = 'missing_document', 'Missing Document'
        UNCONFIRMED_FACT = 'unconfirmed_fact', 'Unconfirmed Fact'
        CONFLICT = 'conflict', 'Conflict'
        STALE_DATA = 'stale_data', 'Stale Data'
        LOW_CONFIDENCE = 'low_confidence', 'Low Confidence'

    class Priority(models.TextChoices):
        BLOCKING = 'blocking', 'Blocking'
        HIGH = 'high', 'High'
        MEDIUM = 'medium', 'Medium'
        OPTIONAL = 'optional', 'Optional'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        UNAVAILABLE = 'unavailable', 'Unavailable'
        SKIPPED = 'skipped', 'Skipped'

    #: Statuses a gap can still meaningfully act on -- used both by the
    #: uniqueness constraints below (a resolved/skipped gap doesn't block a
    #: fresh one from being raised later if the same issue recurs) and by
    #: apps.gaps.services' own dedup checks.
    ACTIVE_STATUSES = [Status.OPEN, Status.IN_PROGRESS]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='gaps')
    gap_type = models.CharField(max_length=32, choices=GapType.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    pillar = models.CharField(max_length=64, choices=PILLAR_CHOICES, blank=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    # Exactly one of these two is normally set (missing_document gaps set
    # neither -- there's no document row to point at yet); which one (or
    # neither) determines how apps.gaps.services dedupes this gap type.
    source_fact = models.ForeignKey(
        'facts.ExtractedFact', on_delete=models.SET_NULL, null=True, blank=True, related_name='gaps',
    )
    related_document = models.ForeignKey(
        'documents.Document', on_delete=models.SET_NULL, null=True, blank=True, related_name='gaps',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    # -- conflict-type-specific fields ---------------------------------------
    # Populated only for gap_type=CONFLICT (apps.extraction.services.
    # conflict_checker.OpenAIConflictChecker). `source_fact` above doubles as
    # "fact A" for a conflict; these are "fact B" plus an immutable snapshot
    # of both values *as they stood when the conflict was detected* -- a
    # reviewer correcting either fact afterward must not silently rewrite
    # what this conflict record originally compared (same "never overwrite
    # history" posture as apps.facts.models.FactReviewHistory).
    conflict_fact_b = models.ForeignKey(
        'facts.ExtractedFact', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    conflict_value_a = models.JSONField(null=True, blank=True)
    conflict_value_b = models.JSONField(null=True, blank=True)
    #: The AI's (or fallback's) confidence that this is a genuine conflict,
    #: not just two facts that happen not to match -- see conflict_checker.py.
    conflict_confidence = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    resolution = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # unconfirmed_fact / low_confidence (always fact-scoped), and
            # conflict (fact-scoped by its lowest-confidence representative).
            models.UniqueConstraint(
                fields=['gap_type', 'source_fact'],
                condition=models.Q(source_fact__isnull=False, status__in=['open', 'in_progress']),
                name='unique_active_gap_per_fact_and_type',
            ),
            # stale_data (document-scoped, no source_fact).
            models.UniqueConstraint(
                fields=['gap_type', 'related_document'],
                condition=models.Q(
                    related_document__isnull=False, source_fact__isnull=True,
                    status__in=['open', 'in_progress'],
                ),
                name='unique_active_gap_per_document_and_type',
            ),
            # missing_document (neither fact nor document exists to scope by
            # -- title is the deterministic key, e.g. "Missing <label>").
            models.UniqueConstraint(
                fields=['sprint', 'gap_type', 'title'],
                condition=models.Q(
                    source_fact__isnull=True, related_document__isnull=True,
                    status__in=['open', 'in_progress'],
                ),
                name='unique_active_gap_per_sprint_type_title',
            ),
        ]

    def __str__(self):
        return f'{self.title} ({self.status})'
