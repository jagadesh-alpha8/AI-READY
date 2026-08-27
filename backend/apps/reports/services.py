"""Report data collection.

`build_report_data` assembles the AIOS Discovery Report's 11 structured
sections entirely from real, already-persisted sprint data -- institution,
sprint, documents, facts, gaps, CRI scores (via
apps.scoring.services.build_score_snapshot, not recomputed here), and
recommendations. Nothing here invents content: an empty source produces an
honest empty section (e.g. "no open data gaps"), never placeholder text.

Kept independent of Celery/the Report model on purpose (see
apps.reports.tasks.generate_report_task, which is the only caller) so this
can be unit tested directly against a sprint without touching the task
queue.
"""
from django.db.models import Max
from django.utils import timezone

from apps.gaps.models import GapItem
from apps.institutions.serializers import InstitutionSerializer
from apps.recommendations.models import Recommendation
from apps.scoring.constants import PILLAR_LABELS
from apps.scoring.models import Baseline
from apps.scoring.services import build_score_snapshot

#: A hidden recommendation was explicitly dismissed by a consultant and
#: shouldn't resurface in a published report.
_REPORT_VISIBLE_RECOMMENDATION_STATUSES = [
    Recommendation.Status.DRAFT, Recommendation.Status.ACCEPTED,
    Recommendation.Status.EDITED, Recommendation.Status.COMPLETED,
]
_NEAR_TERM_PRIORITIES = [Recommendation.Priority.BLOCKING, Recommendation.Priority.HIGH]
_LONGER_TERM_PRIORITIES = [Recommendation.Priority.MEDIUM, Recommendation.Priority.OPTIONAL]
_PRIORITY_ORDER = {
    Recommendation.Priority.BLOCKING: 4, Recommendation.Priority.HIGH: 3,
    Recommendation.Priority.MEDIUM: 2, Recommendation.Priority.OPTIONAL: 1,
}
_GAP_PRIORITY_ORDER = {
    GapItem.Priority.BLOCKING: 4, GapItem.Priority.HIGH: 3,
    GapItem.Priority.MEDIUM: 2, GapItem.Priority.OPTIONAL: 1,
}


def next_report_version(sprint):
    """1 for a sprint's first report, then one past whatever the highest
    existing version is -- never reused, even if a row were ever deleted."""
    current_max = sprint.reports.aggregate(Max('version'))['version__max'] or 0
    return current_max + 1


def _build_executive_summary(sprint, score):
    strong = len(score['strengths'])
    weak = len(score['weaknesses'])
    metrics = score['evidence_metrics']
    calculated_at = score['calculated_at'] or timezone.now()
    return (
        f"As of {calculated_at:%d %b %Y}, {sprint.institution.name} scored "
        f"{score['overall_cri']:.1f}/100 on the Campus Readiness Index (CRI), with "
        f"{score['overall_confidence']:.0%} evidence confidence. "
        f"{strong} of 8 pillars are strong and {weak} need attention. "
        f"{metrics['confirmed_facts'] + metrics['corrected_facts']} facts have been confirmed across "
        f"{metrics['documents_processed']} processed documents, with {metrics['unresolved_gaps']} data "
        f"gaps still open."
    )


def _pillar_scorecards(pillar_scores):
    return [
        {
            'pillar': p.pillar.key, 'label': p.pillar.name, 'weight': p.pillar.weight,
            'raw_score': p.raw_score, 'weighted_score': p.weighted_score,
            'confidence_score': p.confidence_score, 'status': p.status,
            'evidence_count': p.evidence_count, 'gap_count': p.gap_count,
        }
        for p in pillar_scores
    ]


def _pillar_summary_list(pillar_scores):
    return [
        {'pillar': p.pillar.key, 'label': p.pillar.name, 'raw_score': p.raw_score, 'status': p.status}
        for p in pillar_scores
    ]


def _missing_data_appendix(sprint):
    gaps = list(sprint.gaps.filter(status__in=GapItem.ACTIVE_STATUSES))
    gaps.sort(key=lambda g: (-_GAP_PRIORITY_ORDER.get(g.priority, 0), g.pillar))
    return [
        {
            'id': str(g.id), 'gap_type': g.gap_type, 'title': g.title, 'description': g.description,
            'pillar': g.pillar, 'pillar_label': PILLAR_LABELS.get(g.pillar, ''), 'priority': g.priority,
            'created_at': g.created_at,
        }
        for g in gaps
    ]


def _recommendation_payload(rec):
    return {
        'id': str(rec.id), 'title': rec.title, 'description': rec.description, 'pillar': rec.pillar,
        'pillar_label': PILLAR_LABELS.get(rec.pillar, ''), 'owner_role': rec.owner_role,
        'priority': rec.priority, 'timeline': rec.timeline, 'expected_cri_lift': rec.expected_cri_lift,
        'support_offering': rec.support_offering, 'status': rec.status,
    }


def _action_plan(recommendations, priorities):
    """Buckets real Recommendation rows by their own `timeline` field --
    not a separately invented plan, just a filtered/grouped view of the
    same recommendations the CRI/recommendation engines already produced."""
    selected = sorted(
        (r for r in recommendations if r.priority in priorities),
        key=lambda r: (-_PRIORITY_ORDER.get(r.priority, 0), -r.expected_cri_lift),
    )
    buckets = {}
    for rec in selected:
        buckets.setdefault(rec.timeline or 'Unscheduled', []).append(_recommendation_payload(rec))
    return [{'timeline': timeline, 'items': items} for timeline, items in buckets.items()]


def _how_ingage_can_help(recommendations):
    """Rolls up the `support_offering` values already present on real,
    visible recommendations -- not invented sales copy."""
    offerings = {}
    for rec in recommendations:
        if not rec.support_offering:
            continue
        entry = offerings.setdefault(
            rec.support_offering, {'offering': rec.support_offering, 'recommendation_count': 0, 'pillars': set()},
        )
        entry['recommendation_count'] += 1
        if rec.pillar:
            entry['pillars'].add(rec.pillar)
    return [
        {**entry, 'pillars': sorted(entry['pillars'])}
        for entry in sorted(offerings.values(), key=lambda e: -e['recommendation_count'])
    ]


def _baseline_summary(sprint):
    """The sprint's latest baseline decision-cycle, labeled for the report
    header (see apps.reports.rendering / ReportPreviewExport.tsx, which
    both need to show whether this report's numbers are still preliminary,
    provisionally approved, or fully approved). `None` if no baseline has
    ever been submitted for this sprint yet -- a report generated before
    Screen 8 is visited at all is still a real, honest report, just an
    explicitly preliminary one. Safe to read PillarScore/ScoringRun live
    elsewhere in this function even for an approved baseline: once a
    baseline is approved or provisional, apps.scoring.views.SprintScoreView
    refuses further recalculation for that sprint (see
    Sprint.BASELINE_LOCKED_STATUSES), so its PillarScore rows can no longer
    change out from under the ScoringRun the baseline is pinned to.
    """
    baseline = sprint.baselines.order_by('-created_at').first()
    if baseline is None:
        return {'status': 'preliminary', 'baseline_id': None, 'approved_by': '', 'approved_at': None}

    label = {
        Baseline.Status.APPROVED: 'approved',
        Baseline.Status.PROVISIONAL: 'provisional',
    }.get(baseline.status, 'preliminary')

    return {
        'status': label,
        'baseline_id': str(baseline.id),
        'approved_by': baseline.approved_by.get_full_name() if baseline.approved_by else '',
        'approved_at': baseline.approved_at,
    }


def build_report_data(sprint):
    """Collect the sprint's real institution/sprint/document/fact/gap/
    score/recommendation data into the report's 11 structured sections.

    Uses `build_score_snapshot(sprint, bootstrap=True)`: a sprint that has
    never been explicitly scored still gets a real, freshly-computed CRI
    (the same behaviour as GET .../score/) rather than the report showing
    all zeros just because nobody triggered scoring first.
    """
    score = build_score_snapshot(sprint, bootstrap=True)
    recommendations = list(sprint.recommendations.filter(status__in=_REPORT_VISIBLE_RECOMMENDATION_STATUSES))

    return {
        'institution': InstitutionSerializer(sprint.institution).data,
        'sprint': {
            'id': str(sprint.id), 'sprint_code': sprint.sprint_code, 'name': sprint.name,
            'mode': sprint.mode, 'status': sprint.status,
        },
        'generated_at': timezone.now(),
        'baseline': _baseline_summary(sprint),
        'executive_summary': _build_executive_summary(sprint, score),
        'overall_cri': score['overall_cri'],
        'confidence_score': score['overall_confidence'],
        'pillar_scorecards': _pillar_scorecards(score['pillar_scores']),
        'strengths': _pillar_summary_list(score['strengths']),
        'areas_for_improvement': _pillar_summary_list(score['weaknesses']),
        'missing_data_appendix': _missing_data_appendix(sprint),
        'recommendations': [_recommendation_payload(r) for r in recommendations],
        'ninety_day_action_plan': _action_plan(recommendations, _NEAR_TERM_PRIORITIES),
        'twelve_month_roadmap': _action_plan(recommendations, _LONGER_TERM_PRIORITIES),
        'how_ingage_can_help': _how_ingage_can_help(recommendations),
        'evidence_metrics': score['evidence_metrics'],
    }
