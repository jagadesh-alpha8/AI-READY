"""Stage 5: connecting colleges to the benchmark library.

institution profile -> assessment cycle (on the current PUBLISHED release)
  -> applicable benchmarks (from the release's frozen applicability rules)
  -> evidence requests (the release's frozen evidence rules) -> college uploads
  -> InGage evidence review (five quality scores + decision)
  -> four separate scores per benchmark -> scorecard -> finalize (frozen)

Schema tables: institutions/programmes (as a profile next to the existing
Institution), assessment_cycles, applicable_benchmarks, evidence_items,
evidence_reviews, scoring_models, benchmark_score_rules, benchmark_assessments.
"""
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.benchmarks.models import (
    AUTONOMOUS_STATUSES, Benchmark, BenchmarkRelease, BenchmarkReleaseItem, EvidenceType, InstitutionType,
    MaturityDefinition, ProgrammeType,
)

PCT = [MinValueValidator(0), MaxValueValidator(100)]
LEVELS = MaturityDefinition.Level


class BenchmarkProfile(models.Model):
    """What the applicability rules need to know about a college (schema: institutions)."""
    institution = models.OneToOneField('institutions.Institution', on_delete=models.CASCADE, primary_key=True,
                                       related_name='benchmark_profile')
    institution_type = models.ForeignKey(InstitutionType, on_delete=models.PROTECT, related_name='+')
    autonomous_status = models.CharField(max_length=30, choices=AUTONOMOUS_STATUSES, blank=True)
    approval_bodies = models.JSONField(default=list, blank=True, help_text='e.g. ["AICTE", "NBA"]')
    jurisdiction = models.CharField(max_length=60, default='India')
    updated_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)


class Programme(models.Model):
    """schema: programmes."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey('institutions.Institution', on_delete=models.CASCADE,
                                    related_name='benchmark_programmes')
    programme_type = models.ForeignKey(ProgrammeType, on_delete=models.PROTECT, related_name='+')
    name = models.CharField(max_length=200)
    approval_body = models.CharField(max_length=40, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']


class ScoringModel(models.Model):
    """schema: scoring_models. The composite formula is versioned data, not code."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=150)
    formula_version = models.CharField(max_length=20)
    description = models.TextField()
    active = models.BooleanField(default=False)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} ({self.formula_version})'


class BenchmarkScoreRule(models.Model):
    """schema: benchmark_score_rules. Weights approved by the benchmark owner; must add up to 1."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    benchmark = models.ForeignKey(Benchmark, on_delete=models.CASCADE, related_name='score_rules')
    scoring_model = models.ForeignKey(ScoringModel, on_delete=models.PROTECT, related_name='rules')
    compliance_weight = models.DecimalField(max_digits=5, decimal_places=4, validators=[MinValueValidator(0), MaxValueValidator(1)])
    maturity_weight = models.DecimalField(max_digits=5, decimal_places=4, validators=[MinValueValidator(0), MaxValueValidator(1)])
    evidence_weight = models.DecimalField(max_digits=5, decimal_places=4, validators=[MinValueValidator(0), MaxValueValidator(1)])
    outcome_weight = models.DecimalField(max_digits=5, decimal_places=4, validators=[MinValueValidator(0), MaxValueValidator(1)])
    approved_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='+')
    approved_at = models.DateTimeField()
    note = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['benchmark', 'scoring_model'], name='unique_score_rule')]

    def weights(self):
        return {'compliance': self.compliance_weight, 'maturity': self.maturity_weight,
                'evidence_confidence': self.evidence_weight, 'outcome': self.outcome_weight}

    def clean(self):
        if sum(self.weights().values()) != 1:
            raise ValidationError('The four weights must add up to 1.')


class AssessmentCycle(models.Model):
    """schema: assessment_cycles. Always tied to one published release."""
    class Status(models.TextChoices):
        NOT_STARTED = 'not_started', 'Not started'      # benchmarks chosen, evidence not requested yet
        IN_PROGRESS = 'in_progress', 'Collecting evidence'
        SUBMITTED = 'submitted', 'Submitted by college'
        REVIEWED = 'reviewed', 'Scored'
        FINALIZED = 'finalized', 'Finalized'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey('institutions.Institution', on_delete=models.CASCADE, related_name='assessment_cycles')
    name = models.CharField(max_length=200)
    opens_on = models.DateField()
    closes_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    release = models.ForeignKey(BenchmarkRelease, on_delete=models.PROTECT, related_name='assessment_cycles')
    profile_snapshot = models.JSONField(default=dict, help_text='The profile used to decide applicability.')
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    finalized_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.release.release_label})'


class ApplicableBenchmark(models.Model):
    """schema: applicable_benchmarks."""
    class SelectedBy(models.TextChoices):
        RULES_ENGINE = 'rules_engine', 'Rules engine'
        REVIEWER = 'reviewer', 'Reviewer'
        INSTITUTION = 'institution', 'Institution'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle = models.ForeignKey(AssessmentCycle, on_delete=models.CASCADE, related_name='benchmarks')
    benchmark = models.ForeignKey(Benchmark, on_delete=models.PROTECT, related_name='+')
    release_item = models.ForeignKey(BenchmarkReleaseItem, on_delete=models.PROTECT, related_name='+',
                                     help_text='Its frozen snapshot is what the college is assessed against.')
    applicability_result = models.CharField(max_length=20)
    applicability_reason = models.JSONField(default=dict)
    included = models.BooleanField(null=True, help_text='Empty = a reviewer still has to decide.')
    target_level = models.CharField(max_length=2, choices=LEVELS.choices, default=LEVELS.L2)
    selected_by = models.CharField(max_length=20, choices=SelectedBy.choices, default=SelectedBy.RULES_ENGINE)
    decision_note = models.TextField(blank=True)

    class Meta:
        ordering = ['benchmark__benchmark_code']
        constraints = [models.UniqueConstraint(fields=['cycle', 'benchmark'], name='unique_cycle_benchmark')]

    @property
    def snapshot(self):
        return self.release_item.snapshot


def _evidence_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f'assessment_evidence/{instance.cycle_id}/{uuid.uuid4().hex}{ext}'


class EvidenceItem(models.Model):
    """schema: evidence_items. One piece of proof for one evidence request."""
    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'Waiting for review'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        NEEDS_INFORMATION = 'needs_information', 'More information needed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle = models.ForeignKey(AssessmentCycle, on_delete=models.CASCADE, related_name='evidence')
    applicable = models.ForeignKey(ApplicableBenchmark, on_delete=models.CASCADE, related_name='evidence')
    rule_key = models.CharField(max_length=300, help_text='Which evidence request (from the release snapshot) this answers.')
    evidence_type = models.ForeignKey(EvidenceType, on_delete=models.PROTECT, related_name='+')
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to=_evidence_path, blank=True, max_length=500)
    original_filename = models.CharField(max_length=255, blank=True)
    file_sha256 = models.CharField(max_length=64, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    # Reuse of a document the college already uploaded in an AI Readiness Audit
    # sprint (apps.documents) -- the file is served from there, not copied.
    sprint_document = models.ForeignKey('documents.Document', on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='benchmark_evidence')
    issued_on = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    submitted_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class EvidenceReview(models.Model):
    """schema: evidence_reviews. Append-only; the latest review decides the item's status."""
    class Decision(models.TextChoices):
        ACCEPTED = 'accepted', 'Accept'
        REJECTED = 'rejected', 'Reject'
        NEEDS_INFORMATION = 'needs_information', 'Ask for more information'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='+')
    relevance_score = models.DecimalField(max_digits=5, decimal_places=2, validators=PCT)
    completeness_score = models.DecimalField(max_digits=5, decimal_places=2, validators=PCT)
    currency_score = models.DecimalField(max_digits=5, decimal_places=2, validators=PCT)
    authenticity_score = models.DecimalField(max_digits=5, decimal_places=2, validators=PCT)
    scope_score = models.DecimalField(max_digits=5, decimal_places=2, validators=PCT)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reviewed_at']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Evidence reviews are append-only; add a new review instead.')
        super().save(*args, **kwargs)

    def quality(self):
        parts = [self.relevance_score, self.completeness_score, self.currency_score, self.authenticity_score,
                 self.scope_score]
        return sum(parts) / len(parts)


class BenchmarkAssessment(models.Model):
    """schema: benchmark_assessments. Four separate scores; the composite only with approved weights."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicable = models.OneToOneField(ApplicableBenchmark, on_delete=models.CASCADE, related_name='assessment')
    computed_level = models.CharField(max_length=2, choices=LEVELS.choices, blank=True)
    level_override = models.CharField(max_length=2, choices=LEVELS.choices, blank=True)
    override_note = models.TextField(blank=True)
    current_level = models.CharField(max_length=2, choices=LEVELS.choices, blank=True)
    compliance_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=PCT)
    maturity_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=PCT)
    evidence_confidence_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=PCT)
    outcome_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=PCT,
                                        help_text='Entered by the assessor from measured results.')
    outcome_note = models.TextField(blank=True)
    composite_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=PCT)
    scoring_model = models.ForeignKey(ScoringModel, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    weights = models.JSONField(default=dict, blank=True, help_text='The weights used, copied at scoring time.')
    detail = models.JSONField(default=dict, blank=True, help_text='Why each score is what it is.')
    assessor_notes = models.TextField(blank=True)
    scored_at = models.DateTimeField(null=True, blank=True)
    scored_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')


# -- Stage 6: gaps and the improvement plan ---------------------------------------------

class TransformationTemplate(models.Model):
    """schema: transformation_templates. An approved, reusable way to close one
    kind of gap on one benchmark (the expert's playbook). Used when a plan is
    generated; without one the plan falls back to the unmet evidence requests."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    benchmark = models.ForeignKey(Benchmark, on_delete=models.CASCADE, related_name='transformation_templates')
    gap_type = models.CharField(max_length=20, choices=[
        ('compliance', 'Compliance'), ('capability', 'Capability'), ('evidence', 'Evidence'),
        ('outcome', 'Outcome'), ('dependency', 'Dependency')])
    title = models.CharField(max_length=300)
    intervention = models.TextField(help_text='What the institution should do.')
    expected_evidence = models.TextField(help_text='What will prove it was done.')
    expected_outcome = models.TextField(help_text='The measurable result expected.')
    tasks = models.JSONField(default=list, blank=True, help_text='Optional task titles, in order.')
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['benchmark__benchmark_code', 'gap_type', 'title']
        constraints = [models.UniqueConstraint(fields=['benchmark', 'gap_type'], name='unique_template_per_gap_type')]


class AssessmentGap(models.Model):
    """schema: gaps. One typed shortfall found in a finalized benchmark assessment."""
    class Type(models.TextChoices):
        COMPLIANCE = 'compliance', 'Compliance'
        CAPABILITY = 'capability', 'Capability'
        EVIDENCE = 'evidence', 'Evidence'
        OUTCOME = 'outcome', 'Outcome'
        DEPENDENCY = 'dependency', 'Dependency'

    class Severity(models.TextChoices):
        CRITICAL = 'critical', 'Critical'
        HIGH = 'high', 'High'
        MEDIUM = 'medium', 'Medium'
        LOW = 'low', 'Low'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        PLANNED = 'planned', 'Planned'
        IN_PROGRESS = 'in_progress', 'In progress'
        VALIDATED = 'validated', 'Validated by evidence'
        CLOSED = 'closed', 'Closed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(BenchmarkAssessment, on_delete=models.CASCADE, related_name='gaps')
    gap_type = models.CharField(max_length=20, choices=Type.choices)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=Severity.choices)
    root_cause = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    closing_evidence = models.ForeignKey(EvidenceItem, on_delete=models.PROTECT, null=True, blank=True,
                                         related_name='closed_gaps',
                                         help_text='The accepted evidence that shows the gap is closed.')
    validated_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    validated_at = models.DateTimeField(null=True, blank=True)
    validation_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['assessment__applicable__benchmark__benchmark_code', 'gap_type']
        constraints = [models.UniqueConstraint(fields=['assessment', 'gap_type'], name='unique_gap_per_type')]


class Initiative(models.Model):
    """schema: initiatives. The work that closes a gap."""
    class Status(models.TextChoices):
        PLANNED = 'planned', 'Planned'
        ACTIVE = 'active', 'Active'
        BLOCKED = 'blocked', 'Blocked'
        COMPLETE = 'complete', 'Complete'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle = models.ForeignKey(AssessmentCycle, on_delete=models.CASCADE, related_name='initiatives')
    gap = models.ForeignKey(AssessmentGap, on_delete=models.CASCADE, null=True, blank=True, related_name='initiatives')
    template = models.ForeignKey(TransformationTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    expected_evidence = models.TextField(blank=True)
    expected_outcome = models.TextField(blank=True)
    owner = models.CharField(max_length=150, blank=True, help_text='Person or role responsible.')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    target_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['target_date', 'title']


class Task(models.Model):
    """schema: tasks."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    initiative = models.ForeignKey(Initiative, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=300)
    owner = models.CharField(max_length=150, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Initiative.Status.choices, default=Initiative.Status.PLANNED)
    evidence_due = models.CharField(max_length=300, blank=True, help_text='The evidence this task should produce.')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'due_date']
