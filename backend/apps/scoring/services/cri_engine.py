"""The CRI (Campus Readiness Index) scoring engine.

Computes each sprint's eight pillar scores, and the overall weighted CRI,
from real `ExtractedFact`/`GapItem` records against the configurable
`Pillar`/`PillarCriterion` rubric -- never from a hardcoded number. Given the
same fact/gap data and the same Pillar/PillarCriterion configuration, this
always produces the same result: every intermediate step below is a plain,
order-independent aggregation (sums and averages) over a queryset, with no
randomness, wall-clock dependence, or external call anywhere in the
calculation itself.

Nine steps, each its own function so the engine is explainable step by step
rather than one opaque black box:

1. `_confirmed_facts_for_criterion` -- read confirmed/corrected facts.
2. `_unresolved_gaps_for_pillar`    -- read unresolved (open/in_progress) gaps.
3. `_evaluate_criterion`            -- evaluate one pillar criterion.
4. `_evaluate_pillar`               -- combine a pillar's criteria into its score.
5. `run_scoring_engine`             -- combine pillar scores into the weighted overall CRI.
6. `_evaluate_pillar` / `run_scoring_engine` -- evidence confidence, at both levels.
7. `_persist_pillar_scores` / `run_scoring_engine` -- store the results.
8. `_compute_calculation_version`   -- record the calculation version.
9. `build_score_snapshot`           -- return explainable scoring details.
"""
import hashlib

from django.db.models import Case, FloatField, Prefetch, Sum, Value, When
from django.utils import timezone

from apps.documents.models import Document
from apps.facts.models import ExtractedFact
from apps.gaps.constants import GAP_PRIORITY_SCORE_PENALTY
from apps.gaps.models import GapItem

from ..constants import (
    PILLAR_STATUS_DEVELOPING_THRESHOLD,
    PILLAR_STATUS_STRONG_THRESHOLD,
    SCORING_ENGINE_VERSION,
)
from ..models import Pillar, PillarCriterion, PillarScore, ScoringRun

_GAP_PENALTY_CASE = Case(
    *[When(priority=priority, then=Value(penalty)) for priority, penalty in GAP_PRIORITY_SCORE_PENALTY.items()],
    default=Value(0.0),
    output_field=FloatField(),
)

_EVIDENCE_STATUSES = [ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.CORRECTED]


def _confirmed_facts_for_criterion(sprint, pillar, criterion):
    """Step 1: read confirmed/corrected facts backing one criterion."""
    facts = sprint.facts.filter(pillar=pillar.key, status__in=_EVIDENCE_STATUSES)
    if criterion.fact_field_keys:
        facts = facts.filter(field_key__in=criterion.fact_field_keys)
    return list(facts)


def _unresolved_gaps_for_pillar(sprint, pillar):
    """Step 2: read unresolved (open/in_progress) gaps tagged to a pillar."""
    return sprint.gaps.filter(pillar=pillar.key, status__in=GapItem.ACTIVE_STATUSES)


def _evaluate_criterion(sprint, pillar, criterion):
    """Step 3: evaluate one pillar criterion against its real evidence.

    A criterion's fulfilment is the average confidence of the facts backing
    it, expressed as a 0-100 score -- honestly 0 if no qualifying fact has
    been confirmed/corrected yet, never a placeholder or invented value.
    """
    facts = _confirmed_facts_for_criterion(sprint, pillar, criterion)
    avg_confidence = (sum(f.confidence_score for f in facts) / len(facts)) if facts else 0.0
    return {
        'criterion': criterion,
        'score': avg_confidence * 100,
        'confidence': avg_confidence,
        'fact_ids': {f.id for f in facts},
    }


def _classify_pillar_status(*, evidence_count, blocking_gap_count, raw_score):
    """Fixed status rubric (apps.scoring.constants) applied in a fixed
    order: no evidence at all always means 'not_started' regardless of
    score; an unresolved blocking gap always means 'at_risk' regardless of
    how high the score is otherwise -- a pillar can't be "strong" while a
    blocking gap against it is still open."""
    if evidence_count == 0:
        return PillarScore.Status.NOT_STARTED
    if blocking_gap_count > 0 or raw_score < PILLAR_STATUS_DEVELOPING_THRESHOLD:
        return PillarScore.Status.AT_RISK
    if raw_score < PILLAR_STATUS_STRONG_THRESHOLD:
        return PillarScore.Status.DEVELOPING
    return PillarScore.Status.STRONG


def _evaluate_pillar(sprint, pillar):
    """Step 4 (+6): combine a pillar's active criteria into its raw score,
    weighted score, and evidence confidence; steps 1-2 are read here.

    raw_score is the criteria's weighted-average fulfilment (0-100), reduced
    by the same fixed per-priority penalty used elsewhere in the project
    (apps.gaps.constants.GAP_PRIORITY_SCORE_PENALTY) for each of the
    pillar's still-unresolved gaps -- an unresolved gap against a pillar
    should cost it points, the same business rule CRI scoring has used
    since the gap-management work, just now applied per-pillar inside the
    configurable engine instead of as a flat post-hoc subtraction.

    A pillar with no active criteria configured yet (nothing seeded, or an
    admin deactivated all of them) has no way to be evaluated -- it scores
    an honest 0 with 'not_started' status rather than fabricating a value.
    """
    criteria = getattr(pillar, 'active_criteria', None)
    if criteria is None:
        criteria = list(pillar.criteria.filter(is_active=True).order_by('key'))

    evidence_fact_ids = set()
    if criteria:
        total_weight = sum(c.weight for c in criteria) or 1.0
        weighted_score_sum = 0.0
        weighted_confidence_sum = 0.0
        for criterion in criteria:
            evaluation = _evaluate_criterion(sprint, pillar, criterion)
            weighted_score_sum += evaluation['score'] * criterion.weight
            weighted_confidence_sum += evaluation['confidence'] * criterion.weight
            evidence_fact_ids |= evaluation['fact_ids']
        criteria_score = weighted_score_sum / total_weight
        criteria_confidence = weighted_confidence_sum / total_weight
    else:
        criteria_score = 0.0
        criteria_confidence = 0.0

    unresolved_gaps = _unresolved_gaps_for_pillar(sprint, pillar)
    gap_count = unresolved_gaps.count()
    blocking_gap_count = unresolved_gaps.filter(priority=GapItem.Priority.BLOCKING).count()
    gap_penalty = unresolved_gaps.aggregate(total=Sum(_GAP_PENALTY_CASE))['total'] or 0.0

    raw_score = round(max(0.0, min(100.0, criteria_score - gap_penalty)), 2)
    weighted_score = round(raw_score * pillar.weight, 2)
    confidence_score = round(max(0.0, min(1.0, criteria_confidence)), 4)
    evidence_count = len(evidence_fact_ids)

    status = _classify_pillar_status(
        evidence_count=evidence_count, blocking_gap_count=blocking_gap_count, raw_score=raw_score,
    )

    return {
        'pillar': pillar,
        'raw_score': raw_score,
        'weighted_score': weighted_score,
        'confidence_score': confidence_score,
        'status': status,
        'evidence_count': evidence_count,
        'gap_count': gap_count,
    }


def _compute_calculation_version(pillars):
    """Step 8: record the calculation version.

    `SCORING_ENGINE_VERSION` identifies the *algorithm* (bumped by hand when
    the calculation logic itself changes); appended to it is a short hash of
    the active Pillar/PillarCriterion weights actually used for this run --
    so if an admin retunes a weight in the database, the very next run gets
    a different calculation_version automatically, correctly flagging that
    older PillarScore/ScoringRun rows were computed under a different
    configuration, with no extra bookkeeping required.
    """
    parts = []
    for pillar in pillars:
        criteria = getattr(pillar, 'active_criteria', None)
        if criteria is None:
            criteria = list(pillar.criteria.filter(is_active=True).order_by('key'))
        criteria_signature = ';'.join(f'{c.key}:{c.weight}:{sorted(c.fact_field_keys)}' for c in criteria)
        parts.append(f'{pillar.key}:{pillar.weight}[{criteria_signature}]')
    fingerprint = hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:12]
    return f'{SCORING_ENGINE_VERSION}+{fingerprint}'


def _persist_pillar_scores(sprint, pillar_results, calculation_version, calculated_at):
    """Step 7 (pillar half): store each pillar's result, overwriting
    whatever this sprint/pillar's PillarScore previously held."""
    for result in pillar_results:
        PillarScore.objects.update_or_create(
            sprint=sprint, pillar=result['pillar'],
            defaults={
                'raw_score': result['raw_score'],
                'weighted_score': result['weighted_score'],
                'confidence_score': result['confidence_score'],
                'status': result['status'],
                'evidence_count': result['evidence_count'],
                'gap_count': result['gap_count'],
                'calculation_version': calculation_version,
                'calculated_at': calculated_at,
            },
        )


def _serialize_pillar_snapshot(pillar_results):
    return [
        {
            'pillar': result['pillar'].key,
            'label': result['pillar'].name,
            'weight': result['pillar'].weight,
            'raw_score': result['raw_score'],
            'weighted_score': result['weighted_score'],
            'confidence_score': result['confidence_score'],
            'status': result['status'],
            'evidence_count': result['evidence_count'],
            'gap_count': result['gap_count'],
        }
        for result in pillar_results
    ]


def run_scoring_engine(sprint, *, triggered_by=None):
    """Run all nine steps for one sprint: evaluate every active pillar,
    combine them into the weighted overall CRI and evidence confidence
    (steps 5-6), persist the results (step 7), and record a ScoringRun audit
    row (steps 7-9) for GET .../score/history/.

    Deterministic: calling this twice in a row with no data changes between
    calls produces bit-identical raw_score/weighted_score/confidence_score
    values and the same calculation_version, because every input is either a
    plain DB aggregation or configuration read at the start of the run.

    If the active pillars' weights don't sum to exactly 1.0 (a transient
    state while someone is mid-reconfiguration, or a deliberate choice to
    under- or over-weight the total), overall_cri is simply the sum of each
    pillar's own weighted_score -- it is *not* renormalized against the
    actual weight total. A deactivated pillar contributes zero rather than
    having its weight redistributed to the rest; that's the honest reading
    of "this pillar isn't part of scoring right now," not a bug.
    """
    pillars = list(
        Pillar.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch(
                'criteria',
                queryset=PillarCriterion.objects.filter(is_active=True).order_by('key'),
                to_attr='active_criteria',
            ),
        )
        .order_by('display_order', 'key'),
    )

    calculation_version = _compute_calculation_version(pillars)
    calculated_at = timezone.now()

    pillar_results = [_evaluate_pillar(sprint, pillar) for pillar in pillars]

    overall_cri = round(min(100.0, max(0.0, sum(r['weighted_score'] for r in pillar_results))), 2)
    overall_confidence = round(
        min(1.0, max(0.0, sum(r['confidence_score'] * r['pillar'].weight for r in pillar_results))), 4,
    )

    _persist_pillar_scores(sprint, pillar_results, calculation_version, calculated_at)

    scoring_run = ScoringRun.objects.create(
        sprint=sprint,
        calculation_version=calculation_version,
        overall_cri=overall_cri,
        overall_confidence=overall_confidence,
        evidence_count=sum(r['evidence_count'] for r in pillar_results),
        gap_count=sum(r['gap_count'] for r in pillar_results),
        pillar_snapshot=_serialize_pillar_snapshot(pillar_results),
        triggered_by=triggered_by if (triggered_by and triggered_by.is_authenticated) else None,
    )

    sprint.overall_cri = overall_cri
    sprint.confidence_score = overall_confidence
    sprint.save(update_fields=['overall_cri', 'confidence_score', 'updated_at'])

    return scoring_run


def build_score_snapshot(sprint, *, bootstrap=True):
    """Step 9: return explainable scoring details for the current state of
    a sprint -- what GET/POST .../score/ serialize.

    Pillar scores/status/overall_cri/overall_confidence reflect the most
    recent scoring run. With `bootstrap=True` (the default, used by GET/POST
    .../score/), a sprint that has never been scored gets one run of the
    engine on the spot, so the endpoint never 404s or returns nulls for a
    sprint with real fact/gap data just because nobody has explicitly
    triggered a recalculation yet. With `bootstrap=False` (used by the
    read-only sprint overview, which shouldn't have the side effect of
    persisting new PillarScore/ScoringRun rows just because someone loaded a
    dashboard), an unscored sprint returns `None` instead. Evidence metrics
    and the unresolved-blocking-gaps list are read live from current data
    rather than frozen at the last run, so they stay accurate even if a gap
    gets resolved between scoring runs.
    """
    pillar_scores = list(
        PillarScore.objects.filter(sprint=sprint).select_related('pillar').order_by(
            'pillar__display_order', 'pillar__key',
        ),
    )
    if not pillar_scores:
        if not bootstrap:
            return None
        run_scoring_engine(sprint)
        pillar_scores = list(
            PillarScore.objects.filter(sprint=sprint).select_related('pillar').order_by(
                'pillar__display_order', 'pillar__key',
            ),
        )

    strengths = sorted(
        (p for p in pillar_scores if p.status == PillarScore.Status.STRONG),
        key=lambda p: p.raw_score, reverse=True,
    )
    weaknesses = sorted(
        (p for p in pillar_scores if p.status in (PillarScore.Status.AT_RISK, PillarScore.Status.NOT_STARTED)),
        key=lambda p: p.raw_score,
    )

    unresolved_blocking_gaps = sprint.gaps.filter(
        status__in=GapItem.ACTIVE_STATUSES, priority=GapItem.Priority.BLOCKING,
    ).order_by('-created_at')

    evidence_metrics = {
        'confirmed_facts': sprint.facts.filter(status=ExtractedFact.Status.CONFIRMED).count(),
        'corrected_facts': sprint.facts.filter(status=ExtractedFact.Status.CORRECTED).count(),
        'total_extracted_facts': sprint.facts.count(),
        'documents_processed': sprint.documents.filter(status=Document.Status.PROCESSED).count(),
        'unresolved_gaps': sprint.gaps.filter(status__in=GapItem.ACTIVE_STATUSES).count(),
    }

    return {
        'sprint': sprint,
        'overall_cri': sprint.overall_cri or 0.0,
        'overall_confidence': sprint.confidence_score or 0.0,
        'calculation_version': pillar_scores[0].calculation_version if pillar_scores else '',
        'calculated_at': max((p.calculated_at for p in pillar_scores), default=None),
        'pillar_scores': pillar_scores,
        'strengths': strengths,
        'weaknesses': weaknesses,
        'evidence_metrics': evidence_metrics,
        'unresolved_blocking_gaps': unresolved_blocking_gaps,
    }
