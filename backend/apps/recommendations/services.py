"""Recommendation generation.

Turns real sprint data into actionable, explainable recommendations. Every
recommendation's `description` states the specific data point that
triggered it, so nothing here is a fabricated suggestion: if the underlying
gap/fact/pillar-score data doesn't exist, no recommendation for it is
generated.

Three independent generators, each scoped to one trigger source:

1. `_generate_gap_recommendations` -- open high/blocking gaps. This covers
   every pillar's gap-driven case (infrastructure, faculty capability,
   curriculum, student readiness, research, industry, governance) as one
   generator, not six -- GapItem.pillar already carries the distinction, so
   which pillar a recommendation targets falls out of the gap's own data
   rather than six near-duplicate code paths.
2. `_generate_evidence_recommendations` -- low-confidence confirmed/corrected
   facts (the "low-confidence evidence" / "confirmed facts" sources).
3. `_generate_pillar_weakness_recommendations` -- pillars whose latest
   PillarScore is at_risk/not_started (the "CRI pillar weaknesses" source).

Regenerating is idempotent: each generator skips sources it has already
turned into a recommendation (by source_gap / supporting fact / pillar),
regardless of that recommendation's current status, so re-running
`generate` after a consultant has edited or hidden one doesn't spawn a
duplicate.
"""
from apps.facts.models import ExtractedFact
from apps.gaps.constants import GAP_PRIORITY_SCORE_PENALTY
from apps.gaps.models import GapItem
from apps.scoring.constants import PILLAR_STATUS_STRONG_THRESHOLD
from apps.scoring.models import PillarScore

from .models import Recommendation

TIMELINE_BY_PRIORITY = {
    Recommendation.Priority.BLOCKING: '0-30 days',
    Recommendation.Priority.HIGH: '30-60 days',
    Recommendation.Priority.MEDIUM: '60-90 days',
    Recommendation.Priority.OPTIONAL: '90+ days',
}

SUPPORT_OFFERING_BY_SOURCE = {
    'gap': 'Consultant-led remediation workshop',
    'evidence': 'Evidence collection & documentation support',
    'weakness': 'Pillar improvement consulting engagement',
}

#: Who owns a whole AI-QIF pillar (a pillar-weakness recommendation has no gap or fact to take an owner from).
#: Roles are the extraction's owner roles (apps/extraction/services/openai_fact_extractor.FACT_OWNER_ROLE_CHOICES).
PILLAR_OWNER_ROLE = {
    'aiqif_c1': 'iqac_coordinator',   # Institutional AI Strategy & Governance
    'aiqif_c2': 'iqac_coordinator',   # Responsible AI, Risk, Ethics & Compliance
    'aiqif_c3': 'iqac_coordinator',   # AI-Ready Curriculum & Learning
    'aiqif_c4': 'iqac_coordinator',   # Faculty & Institutional Workforce AI Capability
    'aiqif_c5': 'iqac_coordinator',   # Student AI Readiness, Skills & Employability
    'aiqif_c6': 'iqac_coordinator',   # AI Infrastructure, Data & Cybersecurity
    'aiqif_c7': 'iqac_coordinator',   # AI Research, Innovation & Ecosystem
    'aiqif_c8': 'iqac_coordinator',   # AI-Enabled Operations, Industry & Outcomes
    'aiqif_c9': 'iqac_coordinator',   # AI Assurance, Measurement & Continuous Improvement
}

#: A confirmed/corrected fact below this confidence is "low-confidence
#: evidence" worth its own recommendation, even though it already counts as
#: evidence for scoring purposes (apps.scoring.services.cri_engine).
LOW_CONFIDENCE_THRESHOLD = 0.5
#: Below this, low-confidence evidence is urgent enough to flag high priority.
LOW_CONFIDENCE_HIGH_PRIORITY_THRESHOLD = 0.3

_GAP_TRIGGER_PRIORITIES = [GapItem.Priority.BLOCKING, GapItem.Priority.HIGH]


def _derive_gap_owner_role(gap):
    """Same derivation as apps.gaps.serializers.GapItemSerializer.get_owner_role --
    GapItem has no stored owner_role field, so it's read off whichever of
    source_fact/related_document the gap is attached to."""
    if gap.source_fact_id:
        return gap.source_fact.owner_role
    if gap.related_document_id:
        return gap.related_document.owner_role
    return ''


def _generate_gap_recommendations(sprint, actor):
    already_covered = set(
        Recommendation.objects.filter(sprint=sprint, source_gap__isnull=False)
        .values_list('source_gap_id', flat=True)
    )
    gaps = sprint.gaps.filter(
        status__in=GapItem.ACTIVE_STATUSES, priority__in=_GAP_TRIGGER_PRIORITIES,
    ).exclude(id__in=already_covered)

    created = []
    for gap in gaps:
        penalty = GAP_PRIORITY_SCORE_PENALTY.get(gap.priority, 0.0)
        rec = Recommendation.objects.create(
            sprint=sprint,
            title=f'Resolve: {gap.title}',
            description=(
                f'{gap.description or gap.title} '
                f'Why: this is an unresolved {gap.get_priority_display().lower()}-priority gap in '
                f'{gap.get_pillar_display() if gap.pillar else "the sprint"}, currently reducing that '
                f"pillar's score by {penalty:g} points until resolved."
            ),
            trigger_gap=f'{gap.get_gap_type_display()}: {gap.title}',
            source_gap=gap,
            pillar=gap.pillar,
            owner_role=_derive_gap_owner_role(gap),
            priority=gap.priority,
            timeline=TIMELINE_BY_PRIORITY[gap.priority],
            expected_cri_lift=penalty,
            support_offering=SUPPORT_OFFERING_BY_SOURCE['gap'],
            created_by=actor,
        )
        if gap.source_fact_id:
            rec.supporting_facts.add(gap.source_fact_id)
        created.append(rec)
    return created


def _generate_evidence_recommendations(sprint, actor):
    already_covered = set(
        Recommendation.objects.filter(sprint=sprint, supporting_facts__isnull=False)
        .values_list('supporting_facts__id', flat=True)
    )
    facts = sprint.facts.filter(
        status__in=[ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.CORRECTED],
        confidence_score__lt=LOW_CONFIDENCE_THRESHOLD,
    ).exclude(id__in=already_covered)

    created = []
    for fact in facts:
        priority = (
            Recommendation.Priority.HIGH
            if fact.confidence_score < LOW_CONFIDENCE_HIGH_PRIORITY_THRESHOLD
            else Recommendation.Priority.MEDIUM
        )
        lift = round((LOW_CONFIDENCE_THRESHOLD - fact.confidence_score) * 10, 2)
        rec = Recommendation.objects.create(
            sprint=sprint,
            title=f'Strengthen evidence: {fact.field_name}',
            description=(
                f"The confirmed value for '{fact.field_name}' has only "
                f'{fact.confidence_score:.0%} confidence. '
                f'Why: facts below {LOW_CONFIDENCE_THRESHOLD:.0%} confidence keep this '
                f"pillar's overall evidence confidence low even though the fact is confirmed -- "
                f'stronger supporting documentation would raise both.'
            ),
            trigger_gap=f'Low Confidence: {fact.field_name} ({fact.confidence_score:.0%} confidence)',
            pillar=fact.pillar,
            owner_role=fact.owner_role,
            priority=priority,
            timeline=TIMELINE_BY_PRIORITY[priority],
            expected_cri_lift=lift,
            support_offering=SUPPORT_OFFERING_BY_SOURCE['evidence'],
            created_by=actor,
        )
        rec.supporting_facts.add(fact)
        created.append(rec)
    return created


def _pillar_specifics(sprint, pillar_key):
    """(indicators of the pillar without confirmed AI evidence [(code, name, weight)], open gap titles) -- read
    from the latest scoring run's coverage and the sprint's open gaps, so the advice names real items."""
    from apps.scoring.constants import AIQIF_INDICATORS
    run = sprint.scoring_runs.order_by('-created_at').first()
    rows = ((run.evidence_coverage or {}).get('indicators') or []) if run else []
    missing = sorted(((r['code'], AIQIF_INDICATORS.get(r['code'], ('', r['code']))[1], r.get('weight') or 0)
                      for r in rows if AIQIF_INDICATORS.get(r.get('code'), ('',))[0] == pillar_key
                      and not r.get('covered')), key=lambda m: (-m[2], m[0]))
    gaps = list(sprint.gaps.filter(pillar=pillar_key, status__in=GapItem.ACTIVE_STATUSES)
                .order_by('-created_at').values_list('title', flat=True)[:3])
    return missing, gaps


def _pillar_description(pillar, pillar_score, missing, gaps, lift):
    parts = [f'{pillar.name} is {pillar_score.get_status_display().lower()} at {pillar_score.raw_score:g}/100 '
             f'({pillar_score.evidence_count} evidence item(s), {pillar_score.gap_count} unresolved gap(s)).']
    if missing:
        named = '; '.join(f'{code.replace("AIQIF-", "")} {name}' for code, name, _w in missing[:4])
        more = f' and {len(missing) - 4} more' if len(missing) > 4 else ''
        parts.append(f'No confirmed AI evidence yet for: {named}{more}.')
        parts.append(f'Start with {missing[0][0].replace("AIQIF-", "")} {missing[0][1]}: provide documents that '
                     'show it in practice (policy, records, outcomes) and confirm the facts read from them.')
    if gaps:
        parts.append('Open gaps to close: ' + '; '.join(f'"{t}"' for t in gaps) + '.')
    parts.append(f'Why: the pillar is below the strong threshold of {PILLAR_STATUS_STRONG_THRESHOLD:g}, capping the '
                 f'overall CRI; doing this could raise it by up to {lift:g} points.')
    return ' '.join(parts)


def _generate_pillar_weakness_recommendations(sprint, actor):
    """Note: deliberately leaves `source_gap`/`supporting_facts` unset --
    that "no linked record" shape is itself the dedup signal below (a
    gap/evidence recommendation always has one or the other set), so a
    second `generate` call doesn't re-flag a pillar this already covered.
    """
    already_covered = set(
        Recommendation.objects.filter(
            sprint=sprint, source_gap__isnull=True, supporting_facts__isnull=True,
        ).values_list('pillar', flat=True)
    )
    # Pillar recommendations made before owners were assigned get their pillar's owner (fills blanks only).
    for key, role in PILLAR_OWNER_ROLE.items():
        Recommendation.objects.filter(sprint=sprint, pillar=key, owner_role='', source_gap__isnull=True,
                                      supporting_facts__isnull=True).update(owner_role=role)
    weak_scores = PillarScore.objects.filter(
        sprint=sprint, status__in=[PillarScore.Status.AT_RISK, PillarScore.Status.NOT_STARTED],
        pillar__is_active=True,
    ).exclude(pillar__key__in=already_covered).select_related('pillar')

    created = []
    for pillar_score in weak_scores:
        pillar = pillar_score.pillar
        priority = (
            Recommendation.Priority.BLOCKING
            if pillar_score.status == PillarScore.Status.AT_RISK
            else Recommendation.Priority.HIGH
        )
        lift = round(pillar.weight * max(0.0, PILLAR_STATUS_STRONG_THRESHOLD - pillar_score.raw_score), 2)
        missing, gaps = _pillar_specifics(sprint, pillar.key)
        rec = Recommendation.objects.create(
            sprint=sprint,
            title=(f'Strengthen {pillar.name}: evidence for {missing[0][1]}' if missing
                   else f'Strengthen {pillar.name}')[:255],
            description=_pillar_description(pillar, pillar_score, missing, gaps, lift),
            owner_role=PILLAR_OWNER_ROLE.get(pillar.key, ''),
            trigger_gap=f'Pillar Weakness: {pillar.name} ({pillar_score.get_status_display()})',
            pillar=pillar.key,
            priority=priority,
            timeline=TIMELINE_BY_PRIORITY[priority],
            expected_cri_lift=lift,
            support_offering=SUPPORT_OFFERING_BY_SOURCE['weakness'],
            created_by=actor,
        )
        created.append(rec)
    return created


def generate_recommendations_for_sprint(sprint, *, triggered_by=None):
    """Run all three generators for one sprint and return its full, current
    recommendation set (existing rows included, not just the newly created
    ones) -- what GET/POST .../recommendations/ serialize."""
    actor = triggered_by if (triggered_by and triggered_by.is_authenticated) else None
    _generate_gap_recommendations(sprint, actor)
    _generate_evidence_recommendations(sprint, actor)
    _generate_pillar_weakness_recommendations(sprint, actor)
    return sprint.recommendations.all()
