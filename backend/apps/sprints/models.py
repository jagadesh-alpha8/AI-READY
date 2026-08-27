import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Sprint(models.Model):
    class SprintMode(models.TextChoices):
        QUICK_CRI = 'quick_cri', 'Quick CRI'
        VERIFIED_CRI = 'verified_cri', 'Verified CRI'
        FULL_DIGITAL_TWIN = 'full_digital_twin', 'Full Digital Twin'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        COLLECTING = 'collecting', 'Collecting'
        PROCESSING = 'processing', 'Processing'
        REVIEWING = 'reviewing', 'Reviewing'
        SCORING = 'scoring', 'Scoring'
        # Between SCORING and REPORT_READY: a ScoringRun exists and is
        # awaiting a baseline decision (apps.scoring.models.Baseline) --
        # see apps.scoring.services.baseline. BASELINE_PENDING is entered
        # automatically the first time GET .../baseline/ is called for a
        # sprint at SCORING (mirrors how GET .../score/ bootstraps a
        # ScoringRun); BASELINE_APPROVED is entered once that baseline is
        # approved or provisionally approved. "Return for correction" sends
        # the sprint back to REVIEWING rather than a new status, so the
        # existing fact/gap review screens handle it unmodified.
        BASELINE_PENDING = 'baseline_pending', 'Baseline Pending'
        BASELINE_APPROVED = 'baseline_approved', 'Baseline Approved'
        REPORT_READY = 'report_ready', 'Report Ready'
        COMPLETED = 'completed', 'Completed'
        ARCHIVED = 'archived', 'Archived'

    #: Directed graph of legal status transitions. A sprint may always be
    #: archived from any non-terminal state; otherwise it can only move to
    #: the next stage of the pipeline. `archived` is terminal.
    #:
    #: BASELINE_PENDING -> REVIEWING is the "return for correction" path
    #: (apps.scoring.views.SprintBaselineReturnView): once a baseline is
    #: returned, the sprint re-enters the same review loop as a first-pass
    #: sprint, and a fresh scoring run + baseline submission is required to
    #: reach BASELINE_APPROVED again. BASELINE_APPROVED has no path back to
    #: REVIEWING/SCORING -- an approved baseline is locked (see
    #: apps.scoring.models.Baseline's docstring); the only way out of it is
    #: forward to REPORT_READY or sideways to ARCHIVED.
    ALLOWED_TRANSITIONS = {
        Status.DRAFT: {Status.COLLECTING, Status.ARCHIVED},
        Status.COLLECTING: {Status.PROCESSING, Status.ARCHIVED},
        Status.PROCESSING: {Status.REVIEWING, Status.ARCHIVED},
        Status.REVIEWING: {Status.SCORING, Status.ARCHIVED},
        Status.SCORING: {Status.BASELINE_PENDING, Status.ARCHIVED},
        Status.BASELINE_PENDING: {Status.BASELINE_APPROVED, Status.REVIEWING, Status.ARCHIVED},
        Status.BASELINE_APPROVED: {Status.REPORT_READY, Status.ARCHIVED},
        Status.REPORT_READY: {Status.COMPLETED, Status.ARCHIVED},
        Status.COMPLETED: {Status.ARCHIVED},
        Status.ARCHIVED: set(),
    }

    #: Once a baseline has been approved (fully or provisionally), its
    #: ScoringRun is locked -- apps.scoring.views.SprintScoreView.post
    #: refuses to recalculate for a sprint in any of these statuses, so an
    #: approved baseline's numbers can never silently drift out from under
    #: a report generated against it. A return-for-correction sends the
    #: sprint back to REVIEWING (out of this set), where rescoring is
    #: expected again ahead of the next baseline submission.
    BASELINE_LOCKED_STATUSES = {Status.BASELINE_APPROVED, Status.REPORT_READY, Status.COMPLETED}

    #: Real, deterministic completion milestones tied to pipeline stage --
    #: applied automatically on a status change the caller doesn't also
    #: supply an explicit completion_percentage for (see the serializer).
    STATUS_COMPLETION_MILESTONES = {
        Status.DRAFT: 0,
        Status.COLLECTING: 15,
        Status.PROCESSING: 35,
        Status.REVIEWING: 55,
        Status.SCORING: 75,
        Status.BASELINE_PENDING: 80,
        Status.BASELINE_APPROVED: 85,
        Status.REPORT_READY: 90,
        Status.COMPLETED: 100,
        Status.ARCHIVED: 100,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        'institutions.Institution', on_delete=models.CASCADE, related_name='sprints',
    )
    name = models.CharField(max_length=255, blank=True)
    sprint_code = models.CharField(max_length=32, unique=True, blank=True)
    mode = models.CharField(max_length=32, choices=SprintMode.choices, default=SprintMode.VERIFIED_CRI)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    #: Free-text (e.g. "2026-27"), not a real academic-calendar model -- just
    #: the institution's own label for which year this sprint covers.
    academic_year = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    target_completion_date = models.DateField(null=True, blank=True)
    completion_percentage = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    # Denormalized from apps.scoring.PillarScore/ScoringRun so the
    # dashboard/overview can read a sprint's headline numbers without an
    # extra join; kept in sync by
    # apps.scoring.services.cri_engine.run_scoring_engine. Null until first
    # scored.
    overall_cri = models.FloatField(null=True, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_sprints',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.sprint_code or f'{self.institution.name} sprint'

    def save(self, *args, **kwargs):
        if not self.sprint_code:
            self.sprint_code = f'SPR-{str(self.id)[:8].upper()}'
        super().save(*args, **kwargs)
