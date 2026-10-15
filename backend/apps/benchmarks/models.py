"""Source Library -- stage 1 of the Benchmark Intelligence system.

Mirrors the source tables of the manager's foundation schema
(`authorities`, `frameworks`, `source_documents`, `source_versions`,
`source_feeds`, `audit_events`), plus the fields the intern Source Register
collects (role, category, applicability, Drive link, file facts, QA).

Rules from the blueprint, enforced here rather than trusted to callers:
- A source version is a draft until approved. Once it is active, superseded
  or withdrawn, its content (version, dates, file, checksum) can never change
  and it can never be deleted -- a new edition is a new version that
  supersedes it.
- The audit log is append-only.
"""
import re
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Authority(models.Model):
    class Kind(models.TextChoices):
        REGULATORY = 'regulatory', 'Regulatory'
        ACCREDITATION = 'accreditation', 'Accreditation'
        RANKING = 'ranking', 'Ranking'
        STANDARDS_BODY = 'standards_body', 'Standards body'
        GOVERNMENT_POLICY = 'government_policy', 'Government policy'
        INGAGE_PROPOSED = 'ingage_proposed', 'InGage proposed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=30, choices=Kind.choices)
    official_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']
        verbose_name_plural = 'authorities'

    def __str__(self):
        return self.code


class Framework(models.Model):
    """A body of guidance from one authority (here: authority x library category)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    authority = models.ForeignKey(Authority, on_delete=models.PROTECT, related_name='frameworks')
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=200)
    purpose = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.code


class SourceDocument(models.Model):
    class Role(models.TextChoices):
        # The four roles from the manager's brief -- keeps a market report from
        # ever being mistaken for a legal requirement.
        MANDATORY = 'mandatory', 'Mandatory'
        AUTHORITATIVE = 'authoritative_quality_framework', 'Authoritative quality framework'
        GOOD_PRACTICE = 'good_practice_standard', 'Good-practice standard'
        INTELLIGENCE = 'intelligence_signal', 'Intelligence signal'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    framework = models.ForeignKey(Framework, on_delete=models.PROTECT, related_name='documents')
    source_code = models.CharField(max_length=40, unique=True)
    title = models.CharField(max_length=500)
    official_url = models.URLField(max_length=1000, blank=True, help_text='Official page listing the document.')
    licensed_content = models.BooleanField(default=False)
    owner_team = models.CharField(max_length=100, blank=True)
    review_cadence_months = models.PositiveSmallIntegerField(default=12, validators=[MinValueValidator(1)])
    # Source Register extras
    category = models.CharField(max_length=60, blank=True)
    source_role = models.CharField(max_length=40, choices=Role.choices, blank=True,
                                   help_text='Suggested by the collector; confirmed by the benchmark owner.')
    document_type = models.CharField(max_length=40, blank=True)
    applies_to = models.CharField(max_length=300, blank=True)
    programme_scope = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source_code']

    def __str__(self):
        return f'{self.source_code} - {self.title[:60]}'


_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def _validate_sha256(value):
    if value and not _SHA256.match(value):
        raise ValidationError('SHA-256 must be 64 lowercase hex characters.')


class SourceVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        SUPERSEDED = 'superseded', 'Superseded'
        WITHDRAWN = 'withdrawn', 'Withdrawn'

    class Collection(models.TextChoices):
        TO_FIND = 'to_find', 'To find'
        DOWNLOADED = 'downloaded', 'Downloaded'
        LINK_ONLY = 'link_only', 'Found - link only'
        BLOCKED = 'blocked', 'Blocked - portal/login'
        LICENSED = 'licensed_link_only', 'Licensed - link only'
        NOT_AVAILABLE = 'not_available', 'Not available'

    #: Content of an approved version -- frozen once it leaves draft.
    FROZEN_FIELDS = ('document_id', 'version_label', 'issued_on', 'effective_from', 'file_uri',
                     'checksum_sha256', 'direct_url', 'drive_url', 'supersedes_id')
    #: Allowed status moves after draft (draft -> anything is free).
    TRANSITIONS = {Status.ACTIVE: {Status.SUPERSEDED, Status.WITHDRAWN}, Status.SUPERSEDED: set(),
                   Status.WITHDRAWN: set()}
    UNVERSIONED = 'unversioned'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name='versions')
    version_label = models.CharField(max_length=120)
    issued_on = models.DateField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    file_uri = models.CharField(max_length=500, blank=True, help_text='Immutable copy in app storage (stage 1 step 3).')
    checksum_sha256 = models.CharField(max_length=64, blank=True, validators=[_validate_sha256])
    supersedes = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='superseded_by')
    extracted_at = models.DateTimeField(null=True, blank=True)
    # Source Register extras
    direct_url = models.URLField(max_length=1000, blank=True)
    drive_url = models.URLField(max_length=1000, blank=True)
    file_size_kb = models.PositiveIntegerField(null=True, blank=True)
    pages = models.PositiveIntegerField(null=True, blank=True)
    collection_status = models.CharField(max_length=30, choices=Collection.choices, default=Collection.TO_FIND)
    reported_status = models.CharField(max_length=40, blank=True, help_text="Collector's reading, e.g. Current.")
    collected_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    register_row_id = models.CharField(max_length=20, blank=True)
    review_flags = models.JSONField(default=list, blank=True, help_text='Problems found on import, to resolve before approval.')

    class Intake(models.TextChoices):
        NOT_RUN = 'not_run', 'Not run'
        VERIFIED = 'verified', 'Verified (checksum matches the register)'
        COMPUTED = 'computed', 'Stored (no checksum in the register to compare)'
        MISMATCH = 'mismatch', 'Checksum mismatch'
        FAILED = 'failed', 'Failed'
        SKIPPED = 'skipped', 'Skipped'

    # File intake (stage 1 step 3): the stored copy and how it was checked.
    intake_status = models.CharField(max_length=20, choices=Intake.choices, default=Intake.NOT_RUN)
    intake_note = models.TextField(blank=True)
    intake_at = models.DateTimeField(null=True, blank=True)

    class Extraction(models.TextChoices):
        IDLE = 'idle', 'Not started'
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Drafting requirements'
        DONE = 'done', 'Drafts ready for review'
        FAILED = 'failed', 'Failed'

    # Requirement drafting (stage 2).
    extraction_status = models.CharField(max_length=20, choices=Extraction.choices, default=Extraction.IDLE)
    extraction_note = models.TextField(blank=True)

    approved_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['document__source_code', '-issued_on', 'version_label']
        constraints = [models.UniqueConstraint(fields=['document', 'version_label'], name='unique_source_version')]

    def __str__(self):
        return f'{self.document.source_code} @ {self.version_label}'

    @property
    def is_locked(self):
        return self.status != self.Status.DRAFT

    def save(self, *args, **kwargs):
        if self.checksum_sha256:
            self.checksum_sha256 = self.checksum_sha256.lower()
        if self.pk:
            old = SourceVersion.objects.filter(pk=self.pk).first()
            if old is not None and old.is_locked:
                changed = [f for f in self.FROZEN_FIELDS if getattr(old, f) != getattr(self, f)]
                if changed:
                    raise ValidationError(f'{old} is {old.status}: {", ".join(changed)} cannot change. '
                                          'Add a new version that supersedes it.')
                if old.status != self.status and self.status not in self.TRANSITIONS[old.status]:
                    raise ValidationError(f'{old} cannot move from {old.status} to {self.status}.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_locked:
            raise ValidationError(f'{self} is {self.status} and cannot be deleted.')
        return super().delete(*args, **kwargs)


class SourceFeed(models.Model):
    """An official page the daily watcher will check (stage 4). Created disabled:
    a feed is monitored only after someone approves it."""
    class FeedType(models.TextChoices):
        WEB_PAGE = 'web_page', 'Web page'
        RSS = 'rss', 'RSS'
        API = 'api', 'API'
        DOCUMENT_INDEX = 'document_index', 'Document index'
        MANUAL_UPLOAD = 'manual_upload', 'Manual upload'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(SourceDocument, on_delete=models.CASCADE, related_name='feeds')
    feed_type = models.CharField(max_length=20, choices=FeedType.choices)
    endpoint_url = models.URLField(max_length=1000)
    polling_schedule = models.CharField(max_length=40, default='0 2 * * *')
    enabled = models.BooleanField(default=False)
    authority_trust_score = models.DecimalField(max_digits=5, decimal_places=2, default=100,
                                                validators=[MinValueValidator(0)])
    last_success_at = models.DateTimeField(null=True, blank=True)
    # Daily watcher (stage 4)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_result = models.CharField(max_length=20, blank=True, help_text='unchanged / changed / baseline / failed / skipped')
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document__source_code']
        constraints = [models.UniqueConstraint(fields=['document', 'endpoint_url'], name='unique_source_feed')]

    def __str__(self):
        return f'{self.document.source_code} feed ({self.feed_type})'


class SourceAuditEvent(models.Model):
    """Append-only history of every change to the source library."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.CharField(max_length=150)
    action = models.CharField(max_length=60)
    object_type = models.CharField(max_length=60)
    object_id = models.CharField(max_length=60)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk and SourceAuditEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError('Audit events are append-only.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Audit events are append-only.')


# -- Stage 2: from documents to requirements ----------------------------------

class SourceSection(models.Model):
    """A run of pages of one source version's text, the unit the AI reads."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(SourceVersion, on_delete=models.CASCADE, related_name='sections')
    ordinal = models.PositiveIntegerField()
    heading = models.CharField(max_length=300, blank=True)
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['version', 'ordinal']
        constraints = [models.UniqueConstraint(fields=['version', 'ordinal'], name='unique_section_ordinal')]

    def __str__(self):
        return f'{self.version} section {self.ordinal} (pp. {self.page_start}-{self.page_end})'


class RequirementKind(models.TextChoices):
    # requirement_kind in the foundation schema
    MANDATORY = 'mandatory', 'Mandatory'
    RECOMMENDED = 'recommended', 'Recommended'
    GUIDANCE = 'guidance', 'Guidance'
    PROPOSED = 'proposed', 'Proposed'


class RequirementCandidate(models.Model):
    """An AI-drafted requirement. Never active: an expert accepts (possibly
    edited) or rejects it; only an accepted one becomes a Requirement."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending review'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(SourceVersion, on_delete=models.CASCADE, related_name='requirement_candidates')
    section = models.ForeignKey(SourceSection, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidates')
    statement = models.TextField()
    kind = models.CharField(max_length=20, choices=RequirementKind.choices)
    page = models.PositiveIntegerField(null=True, blank=True)
    source_quote = models.TextField(help_text='Exact words from the source this was drafted from.')
    confidence = models.FloatField(default=0)
    rationale = models.TextField(blank=True)
    model = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['version', 'page', 'created_at']

    def __str__(self):
        return f'{self.version} candidate: {self.statement[:60]}'


class Requirement(models.Model):
    """One testable obligation / recommendation / guidance statement, approved
    by an expert, traced to the exact source version, page and words."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=60, unique=True)
    version = models.ForeignKey(SourceVersion, on_delete=models.PROTECT, related_name='requirements')
    section = models.ForeignKey(SourceSection, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    statement = models.TextField()
    kind = models.CharField(max_length=20, choices=RequirementKind.choices)
    page = models.PositiveIntegerField(null=True, blank=True)
    source_quote = models.TextField()
    created_from = models.OneToOneField(RequirementCandidate, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='requirement')
    approved_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='+')
    approved_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code}: {self.statement[:60]}'


# -- Stage 3: the benchmark catalogue ------------------------------------------

class Pillar(models.Model):
    """Top-level grouping of the catalogue (P01-P10 in the Source Pack). Not in
    the foundation schema, which only has capabilities.domain; kept as its own
    table so pillar coverage and weights have a home."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200)
    coverage = models.TextField(blank=True)
    catalogue_status = models.CharField(max_length=200, blank=True)
    weight = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True,
                                 help_text='Provisional weight out of 1000 (AI-QIF criterion weight).')

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} {self.name}'


class EvidenceType(models.Model):
    """EV-01 ... EV-12: families of evidence an institution can submit."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=150)
    validation_method = models.TextField()
    examples = models.TextField(blank=True)
    assessment_use = models.TextField(blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} {self.name}'


class Capability(models.Model):
    """The institutional ability a benchmark assesses (schema: capabilities)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=200)
    domain = models.CharField(max_length=200, help_text='The pillar it belongs to.')
    definition = models.TextField()

    class Meta:
        ordering = ['code']
        verbose_name_plural = 'capabilities'

    def __str__(self):
        return self.code


class Benchmark(models.Model):
    """One assessment unit (schema: benchmarks). Draft until a release publishes it."""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        SUPERSEDED = 'superseded', 'Superseded'
        WITHDRAWN = 'withdrawn', 'Withdrawn'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    benchmark_code = models.CharField(max_length=20, unique=True)
    capability = models.ForeignKey(Capability, on_delete=models.PROTECT, related_name='benchmarks')
    pillar = models.ForeignKey(Pillar, on_delete=models.PROTECT, related_name='benchmarks')
    title = models.CharField(max_length=300)
    benchmark_kind = models.CharField(max_length=20, choices=RequirementKind.choices,
                                      help_text='mandatory = backed by mandatory/authoritative sources; '
                                                'proposed = InGage proposal (needs an expert owner + release approval).')
    benchmark_class = models.CharField(max_length=120, blank=True, help_text='As written in the Source Pack.')
    version_label = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    target_guidance = models.TextField(blank=True)
    applicability = models.TextField(blank=True, help_text='Institution types, as written in the Source Pack.')
    source_basis = models.TextField(blank=True, help_text='Sources named in the Source Pack (not yet linked requirements).')
    scoring_dimensions = models.CharField(max_length=200, blank=True)
    activation_status = models.TextField(blank=True)
    expert_owner = models.CharField(max_length=150, blank=True)
    framework = models.ForeignKey(Framework, on_delete=models.PROTECT, null=True, blank=True, related_name='benchmarks',
                                  help_text='The benchmark framework this was imported from (e.g. AI-QIF v1.0).')
    weight = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True,
                                 help_text='Provisional weight out of 1000 (AI-QIF key indicator weight).')
    naac_crosswalk = models.JSONField(default=list, blank=True,
                                      help_text='NAAC metrics whose evidence can support this benchmark '
                                                '[{metric, requirement, relationship}]. Supporting only, never proof.')
    evidence_types = models.ManyToManyField(EvidenceType, blank=True, related_name='benchmarks')
    requirements = models.ManyToManyField(Requirement, through='BenchmarkRequirement', blank=True,
                                          related_name='benchmarks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['benchmark_code']

    def __str__(self):
        return f'{self.benchmark_code} {self.title}'


class BenchmarkRequirement(models.Model):
    """Which approved requirements a benchmark interprets (schema: benchmark_requirements)."""
    class Relationship(models.TextChoices):
        PRIMARY = 'primary', 'Primary'
        SUPPORTING = 'supporting', 'Supporting'
        CROSSWALK = 'crosswalk', 'Crosswalk'

    benchmark = models.ForeignKey(Benchmark, on_delete=models.CASCADE, related_name='requirement_links')
    requirement = models.ForeignKey(Requirement, on_delete=models.PROTECT, related_name='benchmark_links')
    relationship = models.CharField(max_length=20, choices=Relationship.choices)
    note = models.TextField(blank=True)
    linked_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    linked_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ['benchmark__benchmark_code', 'relationship', 'requirement__code']
        constraints = [models.UniqueConstraint(fields=['benchmark', 'requirement'], name='unique_benchmark_requirement')]

    def __str__(self):
        return f'{self.benchmark.benchmark_code} <- {self.requirement.code} ({self.relationship})'


class MaturityDefinition(models.Model):
    class Level(models.TextChoices):
        L3 = 'L3', 'L3 Foundational'
        L2 = 'L2', 'L2 Good / Recommended'
        L1 = 'L1', 'L1 Advanced / Aspirational'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    benchmark = models.ForeignKey(Benchmark, on_delete=models.CASCADE, related_name='maturity_levels')
    level = models.CharField(max_length=2, choices=Level.choices)
    definition = models.TextField()
    measurement_rule = models.TextField(blank=True)
    is_placeholder = models.BooleanField(
        default=False, help_text='Generic template text shared by many benchmarks -- not a real definition yet.')
    # The prototype's BenchmarkLevel fields (manager's design), each a list of short statements.
    observable_requirements = models.JSONField(default=list, blank=True)
    minimum_evidence = models.JSONField(default=list, blank=True)
    outcome_expectations = models.JSONField(default=list, blank=True)
    non_examples = models.JSONField(default=list, blank=True, help_text='What explicitly does NOT count for this level.')
    requires_manual_review = models.BooleanField(default=False)
    edited_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['benchmark', '-level']  # L3, L2, L1
        constraints = [models.UniqueConstraint(fields=['benchmark', 'level'], name='unique_benchmark_level')]

    def __str__(self):
        return f'{self.benchmark.benchmark_code} {self.level}'


# -- Stage 3.4: evidence rules ---------------------------------------------------------

class EvidenceRule(models.Model):
    """What evidence proves a benchmark level or a requirement.

    Exactly one target: a requirement (foundation schema: requirement_evidence_rules)
    or a benchmark, optionally for one maturity level (the prototype's
    BenchmarkEvidenceRequirement). A benchmark rule with no level applies to all levels.
    """
    class Validation(models.TextChoices):
        # the prototype's ValidationMethod
        AUTO_EXTRACT = 'auto_extract', 'Automatic extraction'
        MANUAL_REVIEW = 'manual_review', 'Manual review'
        SYSTEM_INTEGRATION = 'system_integration', 'System integration'
        AI_ASSISTED_REVIEW = 'ai_assisted_review', 'AI-assisted review'

    class Privacy(models.TextChoices):
        PUBLIC = 'public', 'Public'
        INTERNAL = 'internal', 'Internal'
        CONFIDENTIAL = 'confidential', 'Confidential'
        RESTRICTED = 'restricted', 'Restricted'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requirement = models.ForeignKey(Requirement, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='evidence_rules')
    benchmark = models.ForeignKey(Benchmark, on_delete=models.CASCADE, null=True, blank=True,
                                  related_name='evidence_rules')
    level = models.CharField(max_length=2, choices=MaturityDefinition.Level.choices, blank=True,
                             help_text='Benchmark rules only; blank = every level.')
    evidence_type = models.ForeignKey(EvidenceType, on_delete=models.PROTECT, related_name='rules')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    mandatory = models.BooleanField(default=True)
    minimum_count = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    minimum_currency_months = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Evidence older than this many months does not count (blank = no limit).')
    scope_rule = models.TextField(blank=True, help_text='Which units / programmes / period the evidence must cover.')
    validation_method = models.CharField(max_length=30, choices=Validation.choices, default=Validation.MANUAL_REVIEW)
    privacy_classification = models.CharField(max_length=20, choices=Privacy.choices, default=Privacy.INTERNAL)
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['benchmark__benchmark_code', 'requirement__code', '-level', 'evidence_type__code', 'title']
        constraints = [
            models.CheckConstraint(
                check=(models.Q(requirement__isnull=False, benchmark__isnull=True, level='')
                       | models.Q(requirement__isnull=True, benchmark__isnull=False)),
                name='evidence_rule_one_target'),
            # schema: UNIQUE (requirement_id, evidence_type_id)
            models.UniqueConstraint(fields=['requirement', 'evidence_type'], condition=models.Q(requirement__isnull=False),
                                    name='unique_requirement_evidence_type'),
        ]

    def __str__(self):
        target = self.requirement.code if self.requirement_id else f'{self.benchmark.benchmark_code} {self.level or "all"}'
        return f'{target}: {self.evidence_type.code} {self.title}'


# -- Stage 3.5: applicability ----------------------------------------------------------

class InstitutionType(models.Model):
    """schema: institution_types (seeded: university, engineering, polytechnic, arts_science, iti, health_sciences)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ProgrammeType(models.Model):
    """schema: programme_types."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=150)
    sector = models.CharField(max_length=60)

    class Meta:
        ordering = ['sector', 'name']

    def __str__(self):
        return self.name


#: schema: autonomous_status (free text there; a closed list here so rules can match it).
AUTONOMOUS_STATUSES = [('university', 'University'), ('autonomous', 'Autonomous college'),
                       ('affiliated', 'Affiliated college'), ('constituent', 'Constituent college'),
                       ('standalone', 'Standalone / state-board institution')]
APPROVAL_BODIES = ['UGC', 'AICTE', 'NAAC', 'NBA', 'NIRF', 'DGT', 'NCVET', 'NMC', 'DCI', 'INC', 'PCI', 'State board']


class ApplicabilityRule(models.Model):
    """When a benchmark (or a requirement -- schema: requirement_applicability) applies.

    A condition left empty matches everyone. Rules are tried in priority order
    (lowest first); the first whose conditions all match decides the result and
    gives the reason. No rules at all = "requires review", never "applies".
    """
    class Result(models.TextChoices):
        # the prototype's ApplicabilityResult
        APPLIES = 'applies', 'Applies'
        DOES_NOT_APPLY = 'does_not_apply', 'Does not apply'
        OPTIONAL = 'optional', 'Optional'
        REQUIRES_REVIEW = 'requires_review', 'Requires review'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    benchmark = models.ForeignKey(Benchmark, on_delete=models.CASCADE, null=True, blank=True,
                                  related_name='applicability_rules')
    requirement = models.ForeignKey(Requirement, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='applicability_rules')
    result = models.CharField(max_length=20, choices=Result.choices, default=Result.APPLIES)
    priority = models.PositiveSmallIntegerField(default=100, help_text='Lower runs first.')
    institution_types = models.ManyToManyField(InstitutionType, blank=True, related_name='+')
    autonomous_statuses = models.JSONField(default=list, blank=True)
    programme_types = models.ManyToManyField(ProgrammeType, blank=True, related_name='+',
                                             help_text='Matches if the institution offers at least one of these.')
    approval_bodies = models.JSONField(default=list, blank=True, help_text='Matches if the institution holds at least one.')
    jurisdiction = models.CharField(max_length=80, blank=True, default='India', help_text='Blank = any.')
    reason = models.TextField(blank=True, help_text='Plain-language reason shown with the result.')
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'created_at']
        constraints = [models.CheckConstraint(
            check=(models.Q(benchmark__isnull=False, requirement__isnull=True)
                   | models.Q(benchmark__isnull=True, requirement__isnull=False)),
            name='applicability_rule_one_target')]

    def __str__(self):
        target = self.benchmark.benchmark_code if self.benchmark_id else self.requirement.code
        return f'{target}: {self.result} (p{self.priority})'


# -- Stage 3.6: releases ----------------------------------------------------------------

class BenchmarkRelease(models.Model):
    """schema: benchmark_releases. A complete, versioned set of benchmarks.

    draft -> review -> approved -> published -> retired. Only the current
    published release may be used for new scorecards; a newer publish retires
    it, but its frozen item snapshots are kept forever (historical scores never
    change).
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        REVIEW = 'review', 'In review'
        APPROVED = 'approved', 'Approved'
        PUBLISHED = 'published', 'Published'
        RETIRED = 'retired', 'Retired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    release_label = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    release_notes = models.TextField(blank=True)
    based_on = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, related_name='+')
    submitted_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    published_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, help_text='SHA-256 over all item snapshots, set on publish.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.release_label} ({self.status})'


class BenchmarkReleaseItem(models.Model):
    """schema: benchmark_release_items (+ 'unchanged' for carried-forward items, and the frozen snapshot)."""
    class ChangeType(models.TextChoices):
        ADDED = 'added', 'Added'
        UPDATED = 'updated', 'Updated'
        RETIRED = 'retired', 'Retired'
        UNCHANGED = 'unchanged', 'Unchanged (carried forward)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    release = models.ForeignKey(BenchmarkRelease, on_delete=models.CASCADE, related_name='items')
    benchmark = models.ForeignKey(Benchmark, on_delete=models.PROTECT, related_name='release_items')
    change_type = models.CharField(max_length=20, choices=ChangeType.choices)
    impact_summary = models.TextField(blank=True)
    snapshot = models.JSONField(null=True, blank=True, help_text='Frozen benchmark content, set on publish.')
    snapshot_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['benchmark__benchmark_code']
        constraints = [models.UniqueConstraint(fields=['release', 'benchmark'], name='unique_release_benchmark')]

    def save(self, *args, **kwargs):
        if self.pk and self.release.status in (BenchmarkRelease.Status.PUBLISHED, BenchmarkRelease.Status.RETIRED):
            raise ValidationError('Items of a published release can never change.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.release.status != BenchmarkRelease.Status.DRAFT:
            raise ValidationError('Items can only be removed from a draft release.')
        return super().delete(*args, **kwargs)


# -- Stage 4: daily watcher ----------------------------------------------------------------

class SourceSnapshot(models.Model):
    """schema: source_snapshots. One retrieved state of a feed, stored once per distinct content."""
    class Extraction(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETE = 'complete', 'Complete'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feed = models.ForeignKey(SourceFeed, on_delete=models.CASCADE, related_name='snapshots')
    fetched_at = models.DateTimeField(auto_now_add=True)
    canonical_url = models.URLField(max_length=1000)
    content_hash = models.CharField(max_length=64, help_text='SHA-256 of the normalized content that is compared.')
    content_uri = models.CharField(max_length=500, blank=True, help_text='Raw response, stored in media/source_snapshots.')
    http_metadata = models.JSONField(default=dict, blank=True)
    normalized = models.JSONField(default=dict, blank=True,
                                  help_text='What is compared: {"links": [[text, url], ...]} or {"text_lines": [...]}')
    extraction_status = models.CharField(max_length=20, choices=Extraction.choices, default=Extraction.COMPLETE)

    class Meta:
        ordering = ['-fetched_at']
        constraints = [models.UniqueConstraint(fields=['feed', 'content_hash'], name='unique_feed_snapshot')]


class SourceChangeEvent(models.Model):
    """schema: source_change_events. A detected change, waiting for a person to decide."""
    class Kind(models.TextChoices):
        NEW_DOCUMENT = 'new_document', 'New document listed'
        NEW_VERSION = 'new_version', 'New version of the file'
        CONTENT_CHANGE = 'content_change', 'Page content changed'
        WITHDRAWAL = 'withdrawal', 'Removed / withdrawn'
        ACCESS_CHANGE = 'access_change', 'Access changed'

    class Status(models.TextChoices):
        TRIAGED = 'triaged', 'New'
        IGNORED = 'ignored', 'Ignored'
        UNDER_REVIEW = 'under_review', 'Under review'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name='change_events')
    feed = models.ForeignKey(SourceFeed, on_delete=models.SET_NULL, null=True, related_name='change_events')
    previous_snapshot = models.ForeignKey(SourceSnapshot, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    current_snapshot = models.ForeignKey(SourceSnapshot, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                         help_text='Empty for an access change (nothing could be retrieved).')
    change_kind = models.CharField(max_length=20, choices=Kind.choices)
    materiality_score = models.DecimalField(max_digits=5, decimal_places=2,
                                            validators=[MinValueValidator(0)])
    summary = models.TextField()
    details = models.JSONField(default=dict, blank=True, help_text='Added / removed links or lines, HTTP status ...')
    impact = models.JSONField(default=dict, blank=True, help_text='Affected requirements, benchmarks, releases.')
    detected_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAGED)
    reviewed_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-detected_at']


class WatcherRun(models.Model):
    """schema: watcher_runs. One daily (or manual) pass over the enabled feeds."""
    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        COMPLETE = 'complete', 'Complete'
        PARTIAL_FAILURE = 'partial_failure', 'Partial failure'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    trigger = models.CharField(max_length=40, default='schedule', help_text='schedule / manual / <user email>')
    feeds_checked = models.PositiveIntegerField(default=0)
    changes_detected = models.PositiveIntegerField(default=0)
    candidates_created = models.PositiveIntegerField(default=0)
    failure_detail = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-started_at']


# -- Stage 4b: candidates from watcher changes -----------------------------------------

class BenchmarkCandidate(models.Model):
    """schema: benchmark_candidates. A proposed change to the library, kept apart
    from approved data until domain experts approve it. Created by the watcher
    from a material change event, or by staff. Never edits a benchmark itself:
    an approved candidate lets staff reopen the benchmark as a new draft, which
    then goes through the normal readiness + release approval."""
    class Type(models.TextChoices):
        UPDATE_BENCHMARK = 'update_benchmark', 'Update a benchmark'
        NEW_BENCHMARK = 'new_benchmark', 'New benchmark'
        RETIRE_BENCHMARK = 'retire_benchmark', 'Retire a benchmark'
        SOURCE_UPDATE = 'source_update', 'Review a source change'

    class Status(models.TextChoices):
        RESEARCH = 'research', 'Research'
        REVIEW = 'review', 'In expert review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        PUBLISHED = 'published', 'Published in a release'

    class Role(models.TextChoices):
        ACCREDITATION = 'accreditation', 'Accreditation'
        ACADEMIC = 'academic', 'Academic'
        LEGAL = 'legal', 'Legal'
        AI_GOVERNANCE = 'ai_governance', 'AI governance'
        CYBERSECURITY = 'cybersecurity', 'Cybersecurity'
        PRODUCT = 'product', 'Product'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    change_event = models.ForeignKey(SourceChangeEvent, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='candidates')
    source_document = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='benchmark_candidates')
    benchmark = models.ForeignKey(Benchmark, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='candidates', help_text='The benchmark to update / retire.')
    capability = models.ForeignKey(Capability, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    candidate_type = models.CharField(max_length=20, choices=Type.choices)
    title = models.CharField(max_length=300)
    proposed_kind = models.CharField(max_length=20, choices=RequirementKind.choices, default=RequirementKind.MANDATORY)
    source_rationale = models.TextField()
    proposed_maturity = models.JSONField(default=dict, blank=True)
    proposed_evidence_rules = models.JSONField(default=list, blank=True)
    emergence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    feasibility_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    duplication_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    required_roles = models.JSONField(default=list, help_text='Expert roles that must each approve.')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RESEARCH)
    created_by = models.CharField(max_length=150, help_text='User email, or "watcher".')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_candidate_type_display()}: {self.title[:60]}'


class CandidateReview(models.Model):
    """schema: candidate_reviews. Append-only: a reviewer can review again, the
    latest review per role counts."""
    class Decision(models.TextChoices):
        APPROVE = 'approve', 'Approve'
        REJECT = 'reject', 'Reject'
        NEEDS_RESEARCH = 'needs_research', 'Needs research'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(BenchmarkCandidate, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='+')
    reviewer_role = models.CharField(max_length=20, choices=BenchmarkCandidate.Role.choices)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reviewed_at']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Candidate reviews are append-only; add a new review instead.')
        super().save(*args, **kwargs)
