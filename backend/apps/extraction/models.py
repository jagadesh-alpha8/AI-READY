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
    # Which AI router ran the latest attempt, e.g. 'router2 (localhost:20229)'
    # -- only set when AI_ROUTER_URLS lists several (see router_pool.py).
    ai_router = models.CharField(max_length=100, blank=True)

    class Completeness(models.TextChoices):
        #: Run before completeness was recorded -- not checked.
        UNKNOWN = '', 'Not recorded'
        COMPLETE = 'complete', 'Complete'
        #: A text chunk failed or was skipped, pages were unreadable, or the file could not be read.
        PARTIAL = 'partial', 'Partial'

    #: How much of the document the latest completed attempt actually read (services/completeness.py).
    completeness = models.CharField(max_length=10, choices=Completeness.choices, blank=True, default='')
    #: [{kind: chunk_failed|chunks_skipped|unreadable_pages|unsupported_format, detail, ...}]
    extraction_warnings = models.JSONField(default=list, blank=True)
    chunks_total = models.PositiveIntegerField(default=0)
    chunks_completed = models.PositiveIntegerField(default=0)
    #: Every attempt at this job, oldest first (tasks.py): [{at, router, outcome, detail}]. outcome: running,
    #: completed, failed, retrying, out_of_credit (the router's provider is out of quota -> failover),
    #: waiting (no router left), stopped, reset (processed again). Each attempt's AI calls are billed.
    attempts = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # One live run per document, enforced by the database too: two clicks (or two coordinators)
            # at the same moment can't queue the same document twice.
            models.UniqueConstraint(
                fields=['document'], condition=models.Q(status__in=['pending', 'running', 'retrying']),
                name='one_active_extraction_job_per_document',
            ),
        ]

    def __str__(self):
        return f'ExtractionJob({self.id}) — {self.status}'


class AIUsage(models.Model):
    """One AI API call and what it cost -- the basis for knowing (and billing)
    what each sprint / institution uses.

    Recorded by the AI clients for every call made during extraction (see
    apps.extraction.usage). The links use SET_NULL so the usage history
    survives deleting a job, document or sprint: it's a billing record.
    `cost_usd` is computed when the call is made (apps.extraction.pricing),
    and is NULL when the model has no configured price.
    """

    class Stage(models.TextChoices):
        CLASSIFICATION = 'classification', 'Classification'
        #: One request that both classified the document and extracted the first chunk's facts
        #: (services/document_analysis.py). Its tokens are not split between the two.
        DOCUMENT_ANALYSIS = 'document_analysis', 'Document analysis (classification + facts)'
        FACT_EXTRACTION = 'fact_extraction', 'Fact extraction'
        CONFLICT_CHECK = 'conflict_check', 'Conflict check'
        EVIDENCE_ASSESSMENT = 'evidence_assessment', 'Evidence assessment'
        OTHER = 'other', 'Other'

    class Source(models.TextChoices):
        #: Written automatically from the AI provider's response -- exact.
        RECORDED = 'recorded', 'Recorded'
        #: Copied from a provider / router dashboard (e.g. 9Router) for usage
        #: from before recording existed. Totals only; see `note`.
        IMPORTED = 'imported', 'Imported'
        #: Calculated from document text when no real figures exist.
        ESTIMATED = 'estimated', 'Estimated'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        'institutions.Institution', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_usage',
    )
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_usage')
    document = models.ForeignKey(
        'documents.Document', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_usage',
    )
    extraction_job = models.ForeignKey(
        ExtractionJob, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_usage',
    )
    stage = models.CharField(max_length=30, choices=Stage.choices, default=Stage.OTHER)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.RECORDED)
    #: API requests this row stands for: 1 for a recorded call, the dashboard's
    #: request count for an imported total.
    request_count = models.PositiveIntegerField(default=1)
    #: Where imported/estimated figures came from and what they cover.
    note = models.TextField(blank=True)
    provider = models.CharField(max_length=30, blank=True)  # anthropic / openai / openai_compatible
    model = models.CharField(max_length=150, blank=True)
    #: Uncached input tokens (cache reads/writes are counted separately).
    input_tokens = models.PositiveIntegerField(default=0)
    #: All billed output, including any thinking/reasoning tokens.
    output_tokens = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    cache_write_tokens = models.PositiveIntegerField(default=0)
    #: Informational: the part of output_tokens spent on reasoning, when reported.
    reasoning_tokens = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['sprint', 'created_at']), models.Index(fields=['institution', 'created_at'])]

    def __str__(self):
        return f'AIUsage({self.model}, in={self.input_tokens}, out={self.output_tokens}, ${self.cost_usd})'
