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
from apps.scoring.services import build_score_snapshot, run_scoring_engine

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
        f"{strong} of {len(score['pillar_scores'])} pillars are strong and {weak} need attention. "
        f"{metrics['confirmed_facts'] + metrics['corrected_facts']} facts have been confirmed across "
        f"{metrics['documents_processed']} processed documents, with {metrics['unresolved_gaps']} data "
        f"gaps still open."
    )


_SCORECARD_KEYS = ('pillar', 'label', 'weight', 'raw_score', 'weighted_score', 'confidence_score', 'status',
                   'evidence_count', 'gap_count')


def _pillar_scorecards(pillar_scores):
    """From a ScoringRun.pillar_snapshot (list of dicts with these keys)."""
    return [{k: p.get(k) for k in _SCORECARD_KEYS} for p in pillar_scores]


def _pillar_summary_list(pillar_scores):
    return [{k: p.get(k) for k in ('pillar', 'label', 'raw_score', 'status')} for p in pillar_scores]


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
    elsewhere: the CRI can be recalculated after a decision, but the
    baseline stays pinned to its own (never edited) ScoringRun -- see
    _cri_source for how a report compares its fresh score against it.
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


_STRONG = 'strong'
_WEAK = ('at_risk', 'not_started')


def _decided_baseline(sprint):
    return (sprint.baselines.filter(status__in=[Baseline.Status.APPROVED, Baseline.Status.PROVISIONAL])
            .select_related('scoring_run', 'approved_by').order_by('-created_at').first())


def _same_score(a, b):
    """Same CRI, confidence and per-pillar scores (keys and raw scores)."""
    pillars = lambda run: sorted((p['pillar'], p['raw_score']) for p in run.pillar_snapshot or [])  # noqa: E731
    return (a.overall_cri == b.overall_cri and round(a.overall_confidence, 4) == round(b.overall_confidence, 4)
            and pillars(a) == pillars(b))


def _cri_source(sprint, run):
    """Which score this report uses, and how it relates to the approved baseline."""
    source = {
        'scoring_run_id': str(run.id), 'calculation_version': run.calculation_version,
        'calculated_at': run.created_at, 'recalculated': True,
        'baseline_status': None, 'baseline_scoring_run_id': None, 'baseline_cri': None,
        'differs_from_baseline': False,
    }
    baseline = _decided_baseline(sprint)
    if baseline is None:
        source['note'] = (f'CRI recalculated for this report ({run.overall_cri:.1f}). '
                          'No baseline has been approved yet, so it is preliminary.')
        return source
    same = _same_score(run, baseline.scoring_run)
    who = baseline.approved_by.get_full_name() if baseline.approved_by else 'InGage'
    when = f' on {baseline.approved_at:%d %b %Y}' if baseline.approved_at else ''
    source.update({
        'baseline_status': baseline.status, 'baseline_scoring_run_id': str(baseline.scoring_run_id),
        'baseline_cri': baseline.scoring_run.overall_cri, 'differs_from_baseline': not same,
        'note': (f'CRI recalculated for this report ({run.overall_cri:.1f}); it matches the '
                 f'{baseline.get_status_display().lower()} baseline approved by {who}{when}.') if same else
                (f'This report uses a recalculated CRI ({run.overall_cri:.1f}) that differs from the '
                 f'{baseline.get_status_display().lower()} baseline ({baseline.scoring_run.overall_cri:.1f}, '
                 f'approved by {who}{when}). The approved baseline is unchanged.'),
    })
    return source


def _score_from_run(sprint, run):
    """The report's score, taken from the run's frozen snapshot (not the live tables)."""
    pillars = list(run.pillar_snapshot or [])
    live = build_score_snapshot(sprint, bootstrap=False) or {}
    return {
        'overall_cri': run.overall_cri, 'overall_confidence': run.overall_confidence,
        'calculated_at': run.created_at, 'calculation_version': run.calculation_version,
        'pillar_scores': pillars,
        'strengths': sorted((p for p in pillars if p['status'] == _STRONG), key=lambda p: p['raw_score'], reverse=True),
        'weaknesses': sorted((p for p in pillars if p['status'] in _WEAK), key=lambda p: p['raw_score']),
        'evidence_metrics': live.get('evidence_metrics') or dict.fromkeys(
            ('confirmed_facts', 'corrected_facts', 'total_extracted_facts', 'documents_processed', 'unresolved_gaps'), 0),
    }


def build_report_data(sprint, scoring_run=None):
    """Collect the sprint's real institution/sprint/document/fact/gap/
    score/recommendation data into the report's structured sections.

    The CRI is recalculated first (a new ScoringRun from the latest
    confirmed facts, open gaps and active scoring configuration) unless a
    run is passed in, and the report's scores are read from that run's
    frozen snapshot -- so each report keeps its own CRI, and earlier runs,
    reports and an approved baseline's run are never touched. Raises if
    scoring fails (the caller marks the report failed).
    """
    run = scoring_run or run_scoring_engine(sprint)
    score = _score_from_run(sprint, run)
    recommendations = list(sprint.recommendations.filter(status__in=_REPORT_VISIBLE_RECOMMENDATION_STATUSES))

    return {
        'institution': InstitutionSerializer(sprint.institution).data,
        'sprint': {
            'id': str(sprint.id), 'sprint_code': sprint.sprint_code, 'name': sprint.name,
            'mode': sprint.mode, 'status': sprint.status,
        },
        'generated_at': timezone.now(),
        'baseline': _baseline_summary(sprint),
        'cri_source': _cri_source(sprint, run),
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
