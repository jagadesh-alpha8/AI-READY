"""Stage 6: gaps and the improvement plan, from a FINALIZED assessment.

Gaps (one per type per benchmark, from the frozen scores -- nothing is guessed):
  capability  level reached is below the target level
              severity: no level on a mandatory benchmark -> critical;
                        2+ levels short -> high; 1 level short -> medium
  compliance  compliance score below 100 (mandatory foundational requests unmet)
              severity: mandatory benchmark -> critical (<50) / high; recommended -> medium; else low
  evidence    evidence confidence below 60 although evidence was accepted
              (the proof exists but is weak, partial or out of date) -> medium
  outcome     outcome score below 70 -> high (<50) / medium
  dependency  added by staff when one benchmark is blocked by another

Each gap gets an initiative: from the benchmark's approved transformation
template for that gap type when one exists, otherwise one task per unmet
mandatory evidence request up to the target level. Target dates follow
severity (critical 30 days, high 60, medium 90, low 180) from finalization.

A gap is only "validated" by linking ACCEPTED evidence for the same
benchmark at the same college (guide: never close a gap without accepted
evidence); only a validated gap can be closed.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.benchmarks.models import SourceAuditEvent

from .models import (
    AssessmentCycle, AssessmentGap, BenchmarkAssessment, EvidenceItem, Initiative, Task, TransformationTemplate,
)

Gap = AssessmentGap
LEVEL_RANK = {'': 0, 'L3': 1, 'L2': 2, 'L1': 3}
DAYS = {'critical': 30, 'high': 60, 'medium': 90, 'low': 180}
EVIDENCE_CONFIDENCE_FLOOR = 60
OUTCOME_FLOOR = 70


class PlanError(Exception):
    pass


def _audit(user, action, obj, after=None, reason=''):
    SourceAuditEvent.objects.create(actor=user.email, action=action, object_type=type(obj).__name__,
                                    object_id=str(obj.pk), after=after, reason=reason)


def _gaps_for(a):
    """[(type, severity, description, root_cause, unmet_requests)] for one assessment."""
    ab = a.applicable
    snap = ab.snapshot
    kind = snap.get('kind') or ''
    code = ab.benchmark.benchmark_code
    target, reached = ab.target_level, a.current_level or ''
    rows = (a.detail or {}).get('requests') or []
    unmet = [r for r in rows if r.get('mandatory') and not r.get('met')
             and LEVEL_RANK.get(r.get('level') or 'L3', 1) <= LEVEL_RANK.get(target, 2)]
    out = []
    short = LEVEL_RANK.get(target, 2) - LEVEL_RANK.get(reached, 0)
    if short > 0:
        sev = ('critical' if not reached and kind == 'mandatory' else 'high' if short >= 2 else 'medium')
        out.append((Gap.Type.CAPABILITY, sev,
                    f'{code}: reached {reached or "no level"}, target {target}.',
                    '; '.join((a.detail or {}).get('level_notes') or []), unmet))
    if a.compliance_score is not None and a.compliance_score < 100:
        sev = ('critical' if a.compliance_score < 50 else 'high') if kind == 'mandatory' else \
            'medium' if kind == 'recommended' else 'low'
        out.append((Gap.Type.COMPLIANCE, sev, f'{code}: compliance {a.compliance_score} of 100.',
                    (a.detail or {}).get('compliance', ''),
                    [r for r in unmet if (r.get('level') or 'L3') == 'L3']))
    accepted = EvidenceItem.objects.filter(applicable=ab, status=EvidenceItem.Status.ACCEPTED).exists()
    if accepted and a.evidence_confidence_score is not None and a.evidence_confidence_score < EVIDENCE_CONFIDENCE_FLOOR:
        out.append((Gap.Type.EVIDENCE, 'medium',
                    f'{code}: evidence confidence {a.evidence_confidence_score} — the proof is weak, partial or old.',
                    (a.detail or {}).get('evidence_confidence', ''), []))
    if a.outcome_score is not None and a.outcome_score < OUTCOME_FLOOR:
        out.append((Gap.Type.OUTCOME, 'high' if a.outcome_score < 50 else 'medium',
                    f'{code}: outcome {a.outcome_score} of 100.', a.outcome_note, []))
    return out


def generate_plan(cycle, user):
    if cycle.status != AssessmentCycle.Status.FINALIZED:
        raise PlanError('The improvement plan is made from a finalized assessment.')
    if AssessmentGap.objects.filter(assessment__applicable__cycle=cycle).exists():
        raise PlanError('This assessment already has a plan.')
    start = (cycle.finalized_at or timezone.now()).date()
    made = {'gaps': 0, 'initiatives': 0, 'tasks': 0}
    assessments = BenchmarkAssessment.objects.filter(applicable__cycle=cycle, applicable__included=True) \
        .select_related('applicable__benchmark', 'applicable__release_item')
    with transaction.atomic():
        for a in assessments:
            bench = a.applicable.benchmark
            templates = {t.gap_type: t for t in TransformationTemplate.objects.filter(benchmark=bench)}
            for gtype, sev, desc, cause, unmet in _gaps_for(a):
                gap = AssessmentGap.objects.create(assessment=a, gap_type=gtype, severity=sev, description=desc,
                                                   root_cause=cause[:2000])
                made['gaps'] += 1
                due = start + timedelta(days=DAYS[sev])
                t = templates.get(gtype)
                if t:
                    ini = Initiative.objects.create(
                        cycle=cycle, gap=gap, template=t, title=t.title, description=t.intervention,
                        expected_evidence=t.expected_evidence, expected_outcome=t.expected_outcome, target_date=due)
                    titles = t.tasks or [f'Do: {t.intervention[:280]}', f'Collect: {t.expected_evidence[:280]}']
                    tasks = [(x, '') for x in titles]
                else:
                    ini = Initiative.objects.create(
                        cycle=cycle, gap=gap, title=f'Close the {gap.get_gap_type_display().lower()} gap on '
                                                    f'{bench.benchmark_code}'[:300],
                        description=desc, target_date=due,
                        expected_evidence='; '.join(r['title'] for r in unmet)[:2000])
                    tasks = [(f'Provide: {r["title"]} ({r.get("level") or "any level"})', r['title']) for r in unmet] \
                        or [(f'Agree the actions to close: {desc}', '')]
                made['initiatives'] += 1
                for i, (title, ev) in enumerate(tasks):
                    Task.objects.create(initiative=ini, title=title[:300], evidence_due=ev[:300], order=i,
                                        due_date=due)
                    made['tasks'] += 1
        _audit(user, 'assessment.plan_generated', cycle, after=made)
    return made


def set_gap_status(gap, user, status, root_cause=None):
    allowed = {Gap.Status.OPEN, Gap.Status.PLANNED, Gap.Status.IN_PROGRESS}
    if status == Gap.Status.CLOSED:
        if gap.status != Gap.Status.VALIDATED:
            raise PlanError('A gap can only be closed after accepted evidence has validated it.')
    elif status not in allowed:
        raise PlanError(f'status must be one of {sorted(allowed | {Gap.Status.CLOSED})}; '
                        'use "validate" with accepted evidence first.')
    if gap.status in (Gap.Status.VALIDATED, Gap.Status.CLOSED) and status in allowed:
        raise PlanError('This gap was validated by evidence; it cannot be reopened here.')
    before = gap.status
    gap.status = status
    if root_cause is not None:
        gap.root_cause = root_cause
    gap.save()
    _audit(user, 'assessment.gap_status', gap, after={'from': before, 'to': status})
    return gap


def validate_gap(gap, user, evidence_item, note=''):
    """Link accepted evidence (same college, same benchmark, any cycle) as the proof."""
    ab = gap.assessment.applicable
    if evidence_item.status != EvidenceItem.Status.ACCEPTED:
        raise PlanError('Only accepted evidence can close a gap.')
    if (evidence_item.cycle.institution_id != ab.cycle.institution_id
            or evidence_item.applicable.benchmark_id != ab.benchmark_id):
        raise PlanError('The evidence must be for the same college and the same benchmark.')
    if not (note or '').strip():
        raise PlanError('Say how this evidence shows the gap is closed.')
    gap.status, gap.closing_evidence = Gap.Status.VALIDATED, evidence_item
    gap.validated_by, gap.validated_at, gap.validation_note = user, timezone.now(), note.strip()
    gap.save()
    _audit(user, 'assessment.gap_validated', gap, after={'evidence': str(evidence_item.pk)}, reason=note)
    return gap


INITIATIVE_FIELDS = ('title', 'description', 'owner', 'status', 'target_date')
TASK_FIELDS = ('title', 'owner', 'status', 'due_date', 'evidence_due')


def _apply(obj, data, fields, user, action):
    from datetime import date
    changed = {}
    for f in fields:
        if f not in data:
            continue
        v = data[f]
        if f == 'status' and v not in Initiative.Status.values:
            raise PlanError(f'status must be one of {Initiative.Status.values}.')
        if f in ('target_date', 'due_date'):
            try:
                v = date.fromisoformat(v) if v else None
            except ValueError:
                raise PlanError(f'{f} must be a date like 2026-12-31.')
        if f in ('title',) and not str(v).strip():
            raise PlanError('Title cannot be empty.')
        setattr(obj, f, v.strip() if isinstance(v, str) else v)
        changed[f] = str(v)[:200]
    obj.save()
    _audit(user, action, obj, after=changed)
    return obj


def update_initiative(ini, user, data):
    return _apply(ini, data, INITIATIVE_FIELDS, user, 'assessment.initiative_updated')


def update_task(task, user, data):
    return _apply(task, data, TASK_FIELDS, user, 'assessment.task_updated')


def add_task(ini, user, data):
    title = (data.get('title') or '').strip()
    if not title:
        raise PlanError('Give the task a title.')
    t = Task(initiative=ini, title=title[:300], order=ini.tasks.count())
    return _apply(t, {k: v for k, v in data.items() if k != 'title'}, TASK_FIELDS[1:], user, 'assessment.task_added')
