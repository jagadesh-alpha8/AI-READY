import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.scoring.constants import AIQIF_INDICATOR_CHOICES, PILLAR_CHOICES


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

    class AIQIFMappingStatus(models.TextChoices):
        """Where the fact's AI-QIF category tags (`aiqif_mappings`) stand."""
        PENDING = 'pending', 'Not yet mapped'
        MAPPED = 'mapped', 'Mapped'
        NEEDS_REVIEW = 'needs_review', 'Needs review'
        UNMAPPED = 'unmapped', 'Unmapped'

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
    # Who is expected to review it and by when (apps/facts/ownership.py). `owner_role` is the role
    # responsible; the assignee is one person of that role (or an Institution Admin). Assigning never
    # widens who may act -- that stays the ownership rule.
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_facts',
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    # The fact's AI-QIF category tags live in FactAIQIFMapping; this is their
    # summary: MAPPED (at least one confident indicator), NEEDS_REVIEW (only
    # low-confidence ones), UNMAPPED (the AI found no clear indicator),
    # PENDING (extracted before mapping existed). Category only -- unlike
    # `pillar`, nothing in CRI scoring reads it.
    aiqif_mapping_status = models.CharField(
        max_length=20, choices=AIQIFMappingStatus.choices, default=AIQIFMappingStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.field_key} ({self.status})'


class FactAIQIFMapping(models.Model):
    """One AI-QIF key indicator a fact is evidence for, with why and how
    sure. A fact can support several indicators (one row each), or none.

    A category tag only: it says what the fact is about, never how mature
    the institution is. The Raw CRI scores `ExtractedFact.pillar`/`field_key`
    and never reads it. AI-QIF evidence coverage (scoring/services/coverage.py)
    counts a tag only once a reviewer has confirmed it (`review_status`) on a
    confirmed/corrected fact -- the AI's own `status` never counts.
    The fact's source document, page and quote stay on the fact itself."""

    class Status(models.TextChoices):
        MAPPED = 'mapped', 'Mapped'
        NEEDS_REVIEW = 'needs_review', 'Needs review'

    class ReviewStatus(models.TextChoices):
        UNREVIEWED = 'unreviewed', 'Not reviewed'
        CONFIRMED = 'confirmed', 'Confirmed by a reviewer'
        REJECTED = 'rejected', 'Rejected by a reviewer'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fact = models.ForeignKey(ExtractedFact, on_delete=models.CASCADE, related_name='aiqif_mappings')
    # Always the criterion the indicator belongs to (AIQIF_INDICATORS).
    criterion = models.CharField(max_length=64, choices=PILLAR_CHOICES)
    indicator_code = models.CharField(max_length=20, choices=AIQIF_INDICATOR_CHOICES)
    reason = models.TextField()
    confidence = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    status = models.CharField(max_length=20, choices=Status.choices)
    # A person's decision on the tag (the AI's `status` is only its confidence).
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.UNREVIEWED)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-confidence', 'indicator_code']
        constraints = [
            models.UniqueConstraint(fields=['fact', 'indicator_code'], name='unique_aiqif_indicator_per_fact'),
        ]

    def __str__(self):
        return f'{self.fact_id} -> {self.indicator_code} ({self.status})'


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
        #: An evidence request was withdrawn and the fact's earlier status restored (EvidenceRequest).
        REQUEST_WITHDRAWN = 'request_withdrawn', 'Evidence Request Withdrawn'
        #: The fact's AI-QIF category tags were confirmed in bulk (apps/facts/tag_review.py); the fact is unchanged.
        AIQIF_TAGS_CONFIRMED = 'aiqif_tags_confirmed', 'AI-QIF Tags Confirmed'
        #: Assigned / reassigned / unassigned; new_value = {"from", "to", "due_date"} (ownership.assign).
        ASSIGNED = 'assigned', 'Assigned'

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


class EvidenceRequest(models.Model):
    """A reviewer's request for evidence behind one fact, from request to an explicit resolution.

    Lifecycle (apps/facts/evidence_requests.py; every step is an EvidenceRequestEvent):
    open -> submitted (the assigned user linked a document) -> accepted / accepted_corrected
    (the reviewer confirmed or corrected the fact with that citation) or returned / open (the
    evidence was rejected); withdrawn at any point before resolution. Only a reviewer's decision
    resolves a request -- never an upload, an extraction or the AI. Only the fact's own
    confirmed/corrected status feeds the CRI, at the next recalculation."""

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        SUBMITTED = 'submitted', 'Evidence submitted'
        PROCESSING = 'processing', 'Evidence processing'
        READY_FOR_REVIEW = 'ready_for_review', 'Ready for review'
        RETURNED = 'returned', 'Returned for more evidence'
        ACCEPTED = 'accepted', 'Accepted (fact confirmed)'
        ACCEPTED_CORRECTED = 'accepted_corrected', 'Accepted with correction'
        WITHDRAWN = 'withdrawn', 'Withdrawn'

    UNRESOLVED = (Status.OPEN, Status.SUBMITTED, Status.PROCESSING, Status.READY_FOR_REVIEW, Status.RETURNED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='evidence_requests')
    fact = models.ForeignKey(ExtractedFact, on_delete=models.CASCADE, related_name='evidence_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                     related_name='+')
    #: The fact's owner role when requested -- a hint for choosing a person, never the assignee itself.
    suggested_owner_role = models.CharField(max_length=50, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='assigned_evidence_requests')
    description = models.TextField(help_text='What evidence is needed and why.')
    evidence_needed = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    #: The fact's status before the request, restored if the request is withdrawn.
    fact_status_before = models.CharField(max_length=20, choices=ExtractedFact.Status.choices)
    resolution_note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['fact'], condition=models.Q(
                status__in=['open', 'submitted', 'processing', 'ready_for_review', 'returned']),
                                    name='one_unresolved_evidence_request_per_fact'),
        ]

    def __str__(self):
        return f'Evidence for {self.fact_id} ({self.status})'

    @property
    def is_resolved(self):
        return self.status not in self.UNRESOLVED


class EvidenceRequestDocument(models.Model):
    """One document or text submission for a request, its AI triage, and the reviewer's decision."""

    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'Awaiting review'
        ACCEPTED = 'accepted', 'Accepted'
        RETURNED = 'returned', 'Returned for more evidence'
        REJECTED = 'rejected', 'Rejected'

    class AnalysisStatus(models.TextChoices):
        PENDING = 'pending', 'Submitted'
        PROCESSING = 'processing', 'Processing'
        READY = 'ready', 'Ready for review'
        FAILED = 'failed', 'Processing failed'

    class AnalysisOutcome(models.TextChoices):
        SUPPORTS = 'supports', 'Supports the fact'
        CONTRADICTS = 'contradicts', 'Contradicts the fact'
        DOES_NOT_ADDRESS = 'does_not_address', 'Does not address the fact'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(EvidenceRequest, on_delete=models.CASCADE, related_name='evidence')
    document = models.ForeignKey('documents.Document', on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='evidence_links')
    submitted_text = models.TextField(blank=True)
    source_context = models.TextField(blank=True)
    uploaded_for_request = models.BooleanField(default=False)
    source_page = models.CharField(max_length=50, blank=True)
    source_snippet = models.TextField(blank=True)
    note = models.TextField(blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                     related_name='+')
    analysis_status = models.CharField(max_length=20, choices=AnalysisStatus.choices,
                                       default=AnalysisStatus.PENDING)
    analysis_outcome = models.CharField(max_length=24, choices=AnalysisOutcome.choices, blank=True)
    analysis_summary = models.TextField(blank=True)
    analysis_quote = models.TextField(blank=True)
    analysis_page_number = models.PositiveIntegerField(null=True, blank=True)
    analysis_document_reference = models.CharField(max_length=255, blank=True)
    analysis_suggested_value = models.JSONField(null=True, blank=True)
    analysis_confidence = models.FloatField(null=True, blank=True,
                                            validators=[MinValueValidator(0), MaxValueValidator(1)])
    analysis_error = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    review_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(
                check=(models.Q(document__isnull=False, submitted_text='') |
                           (models.Q(document__isnull=True) & ~models.Q(submitted_text=''))),
                name='evidence_request_document_or_text',
            ),
        ]


class EvidenceRequestEvent(models.Model):
    """Append-only audit trail of one evidence request -- never edited or deleted."""

    class Action(models.TextChoices):
        CREATED = 'created', 'Requested'
        ASSIGNED = 'assigned', 'Assigned'
        COMMENTED = 'commented', 'Comment'
        EVIDENCE_SUBMITTED = 'evidence_submitted', 'Evidence submitted'
        ANALYSIS_STARTED = 'analysis_started', 'AI assessment started'
        ANALYSIS_COMPLETED = 'analysis_completed', 'AI assessment completed'
        ANALYSIS_FAILED = 'analysis_failed', 'AI assessment failed'
        EVIDENCE_RETURNED = 'evidence_returned', 'Evidence returned for more'
        EVIDENCE_REJECTED = 'evidence_rejected', 'Evidence rejected'
        FACT_UPDATED = 'fact_updated', 'Fact updated from accepted evidence'
        GAPS_RESOLVED = 'gaps_resolved', 'Related gaps resolved'
        ACCEPTED = 'accepted', 'Accepted, fact confirmed'
        ACCEPTED_CORRECTED = 'accepted_corrected', 'Accepted with correction'
        WITHDRAWN = 'withdrawn', 'Withdrawn'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(EvidenceRequest, on_delete=models.CASCADE, related_name='events')
    action = models.CharField(max_length=24, choices=Action.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    note = models.TextField(blank=True)
    #: Action details, e.g. {"from": user, "to": user}, {"document_id": ...}, {"status": "returned"}.
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
