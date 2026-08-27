import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Pillar(models.Model):
    """One of the eight fixed CRI pillars, as a configurable database row
    rather than a hardcoded weight table -- an admin can retune a weight, add
    a description, or (temporarily) deactivate a pillar from scoring without
    a code change or deploy. `key` is the same slug used as the `pillar`
    CharField value on ExtractedFact/GapItem/Recommendation elsewhere in the
    project (see apps.scoring.constants.PILLAR_CHOICES), so those rows join
    to this table by string equality, not a foreign key.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    #: This pillar's share of the overall CRI, 0-1. The engine does not
    #: assume active weights sum to exactly 1.0 -- see
    #: cri_engine.run_scoring_engine's docstring on what happens if they
    #: don't (an intentional, honest choice, not an oversight).
    weight = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    display_order = models.PositiveSmallIntegerField(default=0)
    #: Excluded from scoring runs (contributes 0 to overall_cri) but its
    #: historical PillarScore/ScoringRun rows are kept -- same
    #: soft-deactivate-don't-delete posture as GapItem.ACTIVE_STATUSES.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'key']

    def __str__(self):
        return self.name


class PillarCriterion(models.Model):
    """A named, weighted check within a pillar that the engine evaluates
    against real ExtractedFact evidence -- this is what makes "evaluate
    pillar criteria" (see cri_engine.py) a real, configurable step instead of
    a single opaque per-pillar average. `fact_field_keys` scopes the
    criterion to specific ExtractedFact.field_key values; left empty, it
    matches every confirmed/corrected fact tagged to the pillar, which is
    how each pillar is seeded by default (one generic criterion) -- more
    specific criteria can be added later, entirely as a data change, without
    touching the engine.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pillar = models.ForeignKey(Pillar, on_delete=models.CASCADE, related_name='criteria')
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    #: This criterion's share of its pillar's raw_score, 0-1. Normalized
    #: against the sum of *active* criteria weights at evaluation time, so a
    #: partially-configured pillar (weights not summing to 1) still scores
    #: sanely instead of silently under-counting.
    weight = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    fact_field_keys = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('pillar', 'key')
        ordering = ['pillar', 'key']

    def __str__(self):
        return f'{self.pillar.key}:{self.key}'


class PillarScore(models.Model):
    """The current (latest-computed) score for one pillar of one sprint.
    Overwritten in place each time the engine runs for that sprint/pillar --
    ScoringRun.pillar_snapshot is where the history of past values lives.
    """
    class Status(models.TextChoices):
        NOT_STARTED = 'not_started', 'Not Started'
        AT_RISK = 'at_risk', 'At Risk'
        DEVELOPING = 'developing', 'Developing'
        STRONG = 'strong', 'Strong'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='pillar_scores')
    pillar = models.ForeignKey(Pillar, on_delete=models.CASCADE, related_name='scores')
    #: 0-100, this pillar's own evaluation before its weight is applied.
    raw_score = models.FloatField(default=0)
    #: raw_score * pillar.weight -- this pillar's contribution to overall_cri.
    weighted_score = models.FloatField(default=0)
    #: 0-1, the evidence confidence backing raw_score (distinct from the
    #: score itself: a pillar can have a high score built on thin evidence).
    confidence_score = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    evidence_count = models.PositiveIntegerField(default=0)
    gap_count = models.PositiveIntegerField(default=0)
    calculation_version = models.CharField(max_length=64, blank=True)
    calculated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('sprint', 'pillar')
        ordering = ['pillar__display_order', 'pillar__key']

    def __str__(self):
        return f'{self.sprint_id} — {self.pillar.key}: {self.raw_score}'


class ScoringRun(models.Model):
    """One execution of the CRI scoring engine for a sprint -- the audit
    trail GET .../score/history/ reads from. `pillar_snapshot` freezes what
    each pillar looked like at that moment (PillarScore rows themselves get
    overwritten by the next run, so without this, history would lose all
    pillar-level detail past the most recent run).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='scoring_runs')
    calculation_version = models.CharField(max_length=64)
    overall_cri = models.FloatField(default=0)
    overall_confidence = models.FloatField(default=0)
    evidence_count = models.PositiveIntegerField(default=0)
    gap_count = models.PositiveIntegerField(default=0)
    pillar_snapshot = models.JSONField(default=list, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'ScoringRun({self.sprint_id}) — {self.overall_cri}/100 @ {self.created_at:%Y-%m-%d %H:%M}'


class Baseline(models.Model):
    """One approval decision-cycle for a sprint's CRI baseline, pinned to
    the exact `ScoringRun` it was decided against.

    Bootstrapped (created, status=PENDING) the first time
    `GET .../baseline/` is called for a sprint that has been scored --
    mirrors how `apps.scoring.services.cri_engine.build_score_snapshot`
    bootstraps a `ScoringRun` on first read. Append-only in spirit like
    every other decision record in this project (`FactReviewHistory`,
    `GapItem`'s resolution fields): once a `Baseline` reaches APPROVED it is
    never modified again (`apps.scoring.services.baseline` enforces this) --
    "never overwrite historical approved baseline data" is satisfied simply
    by pointing `scoring_run` at a specific, already-immutable `ScoringRun`
    row (later scoring runs create new rows, never update old ones) and by
    refusing any further action once this row is APPROVED. A returned
    baseline is not reused or edited either: a fresh sprint pass through
    REVIEWING -> SCORING and a new `GET .../baseline/` call creates a new
    `Baseline` row for the next decision cycle, so the full history of every
    attempt stays queryable via `Sprint.baselines`.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        PROVISIONAL = 'provisional', 'Provisional'
        RETURNED = 'returned', 'Returned'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey('sprints.Sprint', on_delete=models.CASCADE, related_name='baselines')
    #: The exact ScoringRun this baseline decision was made against --
    #: immutable once set, and never repointed at a later run (see class
    #: docstring). ScoringRun.pillar_snapshot is what a report generated
    #: against an approved baseline reads instead of live-recomputing.
    scoring_run = models.ForeignKey(
        'scoring.ScoringRun', on_delete=models.PROTECT, related_name='baselines',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    #: Free-text rationale attached to whichever decision was last made on
    #: this row (approve / approve-provisional / return) -- the *reason*,
    #: distinct from `BaselineDecisionHistory`, which is the append-only
    #: log of every decision made across every Baseline row for this sprint.
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Baseline({self.sprint_id}) — {self.status} @ {self.created_at:%Y-%m-%d %H:%M}'


class BaselineDecisionHistory(models.Model):
    """Append-only audit trail of every baseline decision for a sprint --
    one row per submit/approve/approve-provisional/return action, across
    every `Baseline` row that sprint has ever had. Same "never discard, just
    keep appending" posture as `apps.facts.models.FactReviewHistory`.
    """
    class Action(models.TextChoices):
        SUBMITTED = 'submitted', 'Submitted'
        APPROVED = 'approved', 'Approved'
        APPROVED_PROVISIONAL = 'approved_provisional', 'Approved Provisionally'
        RETURNED = 'returned', 'Returned for Correction'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    baseline = models.ForeignKey(Baseline, on_delete=models.CASCADE, related_name='history')
    action = models.CharField(max_length=24, choices=Action.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Baseline decision histories'

    def __str__(self):
        return f'{self.baseline_id} — {self.action}'
