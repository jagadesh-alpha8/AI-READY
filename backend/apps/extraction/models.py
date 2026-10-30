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

    #: Set by the worker running this job at every checkpoint (each step, page batch and chunk). A RUNNING job
    #: whose heartbeat is older than EXTRACTION_STALE_SECONDS lost its worker: only then may another worker
    #: claim it (tasks._claim), and the periodic recovery re-queue it (services/recovery.py).
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    #: The Celery worker (hostname) of the current attempt.
    worker = models.CharField(max_length=200, blank=True)
    #: When the job was last handed to the broker (views.dispatch_job / recovery).
    dispatched_at = models.DateTimeField(null=True, blank=True)
    #: Continuations of this run (a large document finished over several bounded attempts; tasks.py).
    continuations = models.PositiveIntegerField(default=0)
    #: When a scheduled retry is due (status retrying) -- shown on the monitor.
    next_retry_at = models.DateTimeField(null=True, blank=True)
    #: Live reading progress, from the document's DocumentPage rows.
    pages_total = models.PositiveIntegerField(default=0)
    pages_done = models.PositiveIntegerField(default=0)
    ocr_pages = models.PositiveIntegerField(default=0)
    vision_pages = models.PositiveIntegerField(default=0)
    unreadable_pages = models.PositiveIntegerField(default=0)

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


class DocumentPage(models.Model):
    """How one page of one document version was read (services/pdf_reader.py), kept so a retry re-reads only
    the pages that failed: a page read from its text layer, or OCR'd successfully, is reused as it is; an
    unreadable page (or one whose OCR failed) is tried again. A document file never changes after upload (a
    new file is a new Document version), so a page's text stays valid for the document's lifetime."""

    class Source(models.TextChoices):
        TEXT = 'text', 'PDF text layer'
        OCR = 'ocr', 'OCR'
        VISION = 'vision', 'Vision fallback'
        NONE = 'none', 'No readable text'

    class Status(models.TextChoices):
        OK = 'ok', 'Read'
        #: OCR ran and found nothing readable (blank, photo-only or illegible).
        UNREADABLE = 'unreadable', 'Unreadable'
        #: The OCR engine raised an error on this page.
        OCR_FAILED = 'ocr_failed', 'OCR failed'
        #: The page needs OCR but none is installed / enabled on this server.
        OCR_UNAVAILABLE = 'ocr_unavailable', 'OCR not available'
        #: Vision fallback failed on this page.
        VISION_FAILED = 'vision_failed', 'Vision fallback failed'
        #: Vision fallback not supported by model or provider.
        VISION_UNAVAILABLE = 'vision_unavailable', 'Vision fallback unavailable'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='page_reads')
    page_number = models.PositiveIntegerField()
    #: The page's text before document-wide cleaning (header/footer removal runs again on every read).
    text = models.TextField(blank=True)
    text_source = models.CharField(max_length=10, choices=Source.choices, default=Source.TEXT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OK)
    #: Mean recognition confidence of the OCR lines kept (0-1); null when OCR was not used or gave none.
    ocr_confidence = models.FloatField(null=True, blank=True)
    ocr_attempts = models.PositiveSmallIntegerField(default=0)
    warning = models.TextField(blank=True)
    #: Tables found on the page: [{index, header: [..], rows: [[..]], bbox}] (PyMuPDF find_tables).
    tables = models.JSONField(default=list, blank=True)

    # Detailed OCR and Vision status tracking
    ocr_status = models.CharField(max_length=20, blank=True)
    ocr_error = models.TextField(blank=True)
    vision_status = models.CharField(max_length=20, blank=True)
    vision_error = models.TextField(blank=True)
    vision_attempts = models.PositiveSmallIntegerField(default=0)
    vision_facts = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['document', 'page_number']
        constraints = [models.UniqueConstraint(fields=['document', 'page_number'], name='one_read_per_document_page')]

    @property
    def reusable(self):
        return self.status == self.Status.OK


class ExtractionChunk(models.Model):
    """One text chunk of a job's document and what the AI returned for it (validated facts), so a retry or
    a continuation reuses every chunk already done and sends only the missing / failed ones to the AI.
    Identified by the hash of the exact text sent: if a page's text changes (e.g. a page is OCR'd on retry),
    the chunk is new and is extracted again."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(ExtractionJob, on_delete=models.CASCADE, related_name='chunks')
    index = models.PositiveIntegerField()
    page_start = models.PositiveIntegerField(default=0)
    page_end = models.PositiveIntegerField(default=0)
    page_numbers = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    #: Facts validated by OpenAIFactExtractor._validate_fact, ready for the pipeline's idempotent persistence.
    facts = models.JSONField(default=list, blank=True)
    #: Chunk 1 only, when its request also classified the document (services/document_analysis.py).
    classification = models.JSONField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['job', 'index']
        constraints = [models.UniqueConstraint(fields=['job', 'content_hash'], name='one_chunk_per_job_text')]


class ExtractionSnapshotQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError('Extraction snapshots cannot be updated.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValueError('Extraction snapshots cannot be updated.')


class ExtractionSnapshot(models.Model):
    """Append-only observations before mutable fact review; retries never overwrite a snapshot."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objects = ExtractionSnapshotQuerySet.as_manager()
    job = models.ForeignKey(ExtractionJob, on_delete=models.CASCADE, related_name='observation_snapshots')
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='extraction_snapshots')
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('Extraction snapshots are append-only.')
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [models.UniqueConstraint(fields=['job', 'content_hash'], name='one_extraction_snapshot_content')]


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
        VISION_FALLBACK = 'vision_fallback', 'Page vision fallback'
        CONFLICT_CHECK = 'conflict_check', 'Conflict check'
        EVIDENCE_ASSESSMENT = 'evidence_assessment', 'Evidence assessment'
        CAPABILITY_RECOMMENDATIONS = 'capability_recommendations', 'Capability recommendations'
        #: The AI second opinion on AI-QIF tags left for an expert (apps/facts/aiqif_tagging.ai_check_pending).
        AIQIF_CHECK = 'aiqif_check', 'AI-QIF tag check'
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
    recommendation_snapshot = models.ForeignKey('scoring.RecommendationSnapshot', on_delete=models.PROTECT, null=True, blank=True, related_name='ai_usage')
    capability_run = models.ForeignKey(
        'scoring.CapabilityRun', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_usage',
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
