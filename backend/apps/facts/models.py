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
        #: Not AI evidence (apps/facts/aiqif_tagging.py): no indicator to review.
        CONTEXT = 'context', 'Context'
        PROFILE = 'profile', 'Institution profile'

    class FactKind(models.TextChoices):
        """What the fact is for (apps/facts/aiqif_tagging.py). Only AI evidence can cover an AI-QIF indicator."""
        AI_EVIDENCE = 'ai_evidence', 'AI evidence'
        CONTEXT = 'context', 'Context'
        PROFILE = 'profile', 'Institution profile'

    class ProfileField(models.TextChoices):
        """Which part of the benchmark profile a profile fact describes (assessments.BenchmarkProfile)."""
        INSTITUTION_TYPE = 'institution_type', 'Institution type'
        AUTONOMOUS_STATUS = 'autonomous_status', 'Autonomous status'
        APPROVAL_BODY = 'approval_body', 'Approval body'
        PROGRAMME = 'programme', 'Programme offered'
        OTHER = 'other', 'Other'

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
    # -- automatic AI-QIF tagging (apps/facts/aiqif_tagging.py) --------------------------------------
    #: '' = not classified yet (extracted before kinds existed; `retag_aiqif_facts` classifies it).
    fact_kind = models.CharField(max_length=20, choices=FactKind.choices, blank=True)
    #: The NAAC metric the fact reports ("2.1.2"), only when it appears in the text it came from.
    naac_metric = models.CharField(max_length=20, blank=True)
    #: Profile facts: which profile field, and the matching code from the closed lists (blank if none fits).
    profile_field = models.CharField(max_length=30, choices=ProfileField.choices, blank=True)
    profile_code = models.CharField(max_length=60, blank=True)
    #: True while the fact needs a Super Admin decision: possibly AI evidence filed as context/profile,
    #: AI evidence with no indicator, or not classified yet. Part of the expert queue.
    kind_needs_check = models.BooleanField(default=False)
    #: Set when a Super Admin decided the kind; re-extraction then keeps it.
    kind_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    kind_reviewed_at = models.DateTimeField(null=True, blank=True)
    #: What tagging left out and why ([{kind, detail}]) -- dropped tags, a discarded NAAC metric, ...
    tagging_notes = models.JSONField(default=list, blank=True)
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

    class Relationship(models.TextChoices):
        """How the fact supports the indicator (the NAAC -> AI-QIF crosswalk's vocabulary). Contextual never
        counts toward coverage."""
        DIRECT = 'direct', 'Direct'
        SUPPORTING = 'supporting', 'Supporting'
        CONTEXTUAL = 'contextual', 'Contextual'

    class Source(models.TextChoices):
        CROSSWALK = 'crosswalk', 'NAAC crosswalk'
        AI = 'ai', 'AI suggestion'
        EXPERT = 'expert', 'Added by an expert'
        #: Added because an expert confirmed this indicator for the same field before (aiqif_tagging.Precedents).
        PRECEDENT = 'precedent', 'Earlier expert decision'

    class AutoDecision(models.TextChoices):
        """Why the rules decided the tag without a person (aiqif_tagging.py); '' = they did not."""
        RULES = 'accepted_rules', 'Accepted: confident AI tag of the same criterion'
        CROSSWALK = 'accepted_crosswalk', 'Accepted: NAAC crosswalk'
        PRECEDENT = 'accepted_precedent', 'Accepted: matches an earlier expert decision'
        AI_CHECK = 'accepted_ai_check', 'Accepted: confirmed by an AI second opinion'
        REJECTED_PRECEDENT = 'rejected_precedent', 'Rejected: an expert rejected it for this field before'

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
    relationship = models.CharField(max_length=20, choices=Relationship.choices, default=Relationship.SUPPORTING)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.AI)
    #: Accepted by the rules without a person (aiqif_tagging.py): crosswalk tags, and confident AI tags of
    #: the fact's own criterion. A person's rejection still wins.
    auto_accepted = models.BooleanField(default=False)
    #: The framework / release the crosswalk tag came from ("AI-QIF v1.0").
    framework_version = models.CharField(max_length=60, blank=True)
    #: How the rules decided it without a person, and in words why (precedent, AI second opinion, ...).
    auto_decision = models.CharField(max_length=30, choices=AutoDecision.choices, blank=True)
    auto_reason = models.TextField(blank=True)
    #: Set when a Super Admin reopened the decision or edited the mapping without deciding it: the tag waits in
    #: the expert queue until confirmed or rejected again (cleared then). Earlier decisions stay in the fact's
    #: review history (aiqif_tagging.reopen_tag / edit_tag); re-extraction never removes a pending tag.
    pending_since = models.DateTimeField(null=True, blank=True)
    pending_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    pending_reason = models.TextField(blank=True)
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
        #: The fact's AI-QIF category tags were confirmed in bulk (a removed action; kept for existing history).
        AIQIF_TAGS_CONFIRMED = 'aiqif_tags_confirmed', 'AI-QIF Tags Confirmed'
        #: Expert queue (apps/facts/aiqif_tagging.py): a tag confirmed / rejected, a tag added, the kind decided.
        AIQIF_TAG_REVIEWED = 'aiqif_tag_reviewed', 'AI-QIF Tag Reviewed'
        AIQIF_TAG_ADDED = 'aiqif_tag_added', 'AI-QIF Tag Added'
        AIQIF_TAG_EDITED = 'aiqif_tag_edited', 'AI-QIF Tag Edited'
        AIQIF_TAG_REOPENED = 'aiqif_tag_reopened', 'AI-QIF Tag Review Reopened'
        FACT_KIND_CHANGED = 'fact_kind_changed', 'Fact Kind Decided'
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
    analysis_error = models.TextField(blank=True, help_text='The latest AI assessment error (kept until a success).')
    #: The submission's readable page text as first read ([{page_number, text}]), so a retried AI assessment never
    #: reads / OCRs the document again. Empty for pasted text (submitted_text is the source) and until first read.
    source_pages = models.JSONField(default=list, blank=True)
    #: AI assessment runs started (the first one plus retries), and reviewer-requested retries.
    analysis_attempts = models.PositiveSmallIntegerField(default=0)
    analysis_retry_count = models.PositiveSmallIntegerField(default=0)
    analysis_started_at = models.DateTimeField(null=True, blank=True)
    analysis_finished_at = models.DateTimeField(null=True, blank=True)
    analysis_retry_requested_at = models.DateTimeField(null=True, blank=True)
    analysis_retry_requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                                    blank=True, related_name='+')
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
        ANALYSIS_RETRY = 'analysis_retry', 'AI assessment retry requested'
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
