"""Stage 3.5: which benchmarks (and requirements) apply to an institution.

    profile = Profile(institution_type='engineering', autonomous_status='autonomous',
                      programme_types={'ug_engineering', 'mba_pgdm'}, approval_bodies={'AICTE', 'NBA'})
    evaluate(benchmark.applicability_rules.all(), profile) -> Decision(result, reason, rule_id)
    resolve_benchmarks(profile) -> [ {benchmark, decision}, ... ] for the whole catalogue

Rules are tried in priority order (lowest first); the first rule whose
conditions all match decides. An empty condition matches everyone. Every
decision carries a plain-language reason -- the developer guide asks for a
reason for every inclusion AND exclusion. A benchmark with no rules is
"requires_review", never silently "applies".

Editing guards mirror the other stages: benchmark rules only while the
benchmark is a draft, requirement rules only while every benchmark linked to
the requirement is a draft; every change audited.
"""
from dataclasses import dataclass, field

from django.db import transaction

from ..models import (
    APPROVAL_BODIES, AUTONOMOUS_STATUSES, ApplicabilityRule, Benchmark, InstitutionType, ProgrammeType,
    SourceAuditEvent,
)

STATUS_CODES = [c for c, _ in AUTONOMOUS_STATUSES]
STATUS_NAMES = dict(AUTONOMOUS_STATUSES)


class ApplicabilityError(Exception):
    pass


@dataclass
class Profile:
    institution_type: str
    autonomous_status: str = ''
    programme_types: set = field(default_factory=set)
    approval_bodies: set = field(default_factory=set)
    jurisdiction: str = 'India'

    @classmethod
    def from_data(cls, data):
        itype = (data.get('institution_type') or '').strip()
        if not InstitutionType.objects.filter(code=itype).exists():
            raise ApplicabilityError('institution_type must be one of: '
                                     + ', '.join(InstitutionType.objects.values_list('code', flat=True)))
        status = (data.get('autonomous_status') or '').strip()
        if status and status not in STATUS_CODES:
            raise ApplicabilityError(f'autonomous_status must be one of {STATUS_CODES}.')
        return cls(institution_type=itype, autonomous_status=status,
                   programme_types=set(data.get('programme_types') or []),
                   approval_bodies={b.strip() for b in (data.get('approval_bodies') or []) if b.strip()},
                   jurisdiction=(data.get('jurisdiction') or 'India').strip())


@dataclass
class Decision:
    result: str
    reason: str
    rule_id: str = ''


def _check(profile, types, statuses, programmes, bodies, jurisdiction):
    """[(label, matched?)] for each condition a rule sets. types/programmes are {code: name}."""
    out = []
    if types:
        out.append((f'institution type is {" or ".join(types.values())}', profile.institution_type in types))
    if statuses:
        names = ' or '.join(STATUS_NAMES.get(s, s) for s in statuses)
        out.append((f'status is {names}', profile.autonomous_status in statuses))
    if programmes:
        out.append((f'offers {" or ".join(programmes.values())}', bool(profile.programme_types & set(programmes))))
    if bodies:
        out.append((f'holds {" or ".join(bodies)} approval', bool(profile.approval_bodies & set(bodies))))
    if jurisdiction:
        out.append((f'jurisdiction is {jurisdiction}', profile.jurisdiction.lower() == jurisdiction.lower()))
    return out


def _conditions(rule):
    """[(label, matched?)] for each condition the rule sets, given a profile (closure)."""
    types = {t.code: t.name for t in rule.institution_types.all()}
    programmes = {p.code: p.name for p in rule.programme_types.all()}
    return lambda profile: _check(profile, types, rule.autonomous_statuses, programmes, rule.approval_bodies,
                                  rule.jurisdiction)


def evaluate_snapshot(rules, profile):
    """Like evaluate(), but on the frozen rules of a published release item (plain dicts,
    already in priority order). Stage 5 uses this so a college is judged by the release,
    never by later draft edits."""
    if not rules:
        return Decision(ApplicabilityRule.Result.REQUIRES_REVIEW, 'No applicability rules in this release.')
    type_names = dict(InstitutionType.objects.values_list('code', 'name'))
    prog_names = dict(ProgrammeType.objects.values_list('code', 'name'))
    misses = []
    for i, rule in enumerate(rules):
        conds = _check(profile, {c: type_names.get(c, c) for c in rule.get('institution_types', [])},
                       rule.get('autonomous_statuses') or [], {c: prog_names.get(c, c) for c in rule.get('programme_types', [])},
                       rule.get('approval_bodies') or [], rule.get('jurisdiction') or '')
        failed = [label for label, ok in conds if not ok]
        if not failed:
            why = rule.get('reason') or ('Matches: ' + '; '.join(label for label, _ in conds) if conds
                                         else 'Applies to all institutions.')
            return Decision(rule['result'], why, f'rule {i + 1}')
        misses.append(failed[0])
    return Decision(ApplicabilityRule.Result.DOES_NOT_APPLY,
                    'No rule matched (' + '; '.join(f'needs {m}' for m in dict.fromkeys(misses)) + ').')


def evaluate(rules, profile):
    rules = sorted(rules, key=lambda r: (r.priority, r.created_at))
    if not rules:
        return Decision(ApplicabilityRule.Result.REQUIRES_REVIEW, 'No applicability rules written yet.')
    misses = []
    for rule in rules:
        conds = _conditions(rule)(profile)
        failed = [label for label, ok in conds if not ok]
        if not failed:
            why = rule.reason or ('Matches: ' + '; '.join(label for label, _ in conds) if conds else 'Applies to all institutions.')
            return Decision(rule.result, why, str(rule.pk))
        misses.append(failed[0])
    return Decision(ApplicabilityRule.Result.DOES_NOT_APPLY,
                    'No rule matched (' + '; '.join(f'needs {m}' for m in dict.fromkeys(misses)) + ').')


def resolve_benchmarks(profile, benchmarks=None):
    qs = benchmarks if benchmarks is not None else Benchmark.objects.all()
    qs = qs.select_related('pillar').prefetch_related(
        'applicability_rules__institution_types', 'applicability_rules__programme_types').order_by('benchmark_code')
    return [{'benchmark': b, 'decision': evaluate(list(b.applicability_rules.all()), profile)} for b in qs]


# -- editing ------------------------------------------------------------------------

def _check_editable(benchmark=None, requirement=None):
    from .release_lock import lock_message
    if benchmark is not None and benchmark.status != Benchmark.Status.DRAFT:
        raise ApplicabilityError(f'{benchmark.benchmark_code} is {benchmark.status}; change applicability in a new draft.')
    if benchmark is not None and lock_message(benchmark):
        raise ApplicabilityError(lock_message(benchmark))
    if requirement is not None:
        locked = requirement.benchmarks.exclude(status=Benchmark.Status.DRAFT).values_list('benchmark_code', flat=True)
        if locked:
            raise ApplicabilityError(f'{requirement.code} is part of released benchmark(s) {", ".join(locked)}.')


def _clean(data):
    result = data.get('result', ApplicabilityRule.Result.APPLIES)
    if result not in ApplicabilityRule.Result.values:
        raise ApplicabilityError(f'result must be one of {ApplicabilityRule.Result.values}.')
    try:
        priority = int(data.get('priority', 100))
    except (TypeError, ValueError):
        raise ApplicabilityError('priority must be a whole number.')
    if not 0 <= priority <= 1000:
        raise ApplicabilityError('priority must be between 0 and 1000.')
    statuses = list(dict.fromkeys(data.get('autonomous_statuses') or []))
    if any(s not in STATUS_CODES for s in statuses):
        raise ApplicabilityError(f'autonomous_statuses must be from {STATUS_CODES}.')
    bodies = list(dict.fromkeys(b.strip() for b in (data.get('approval_bodies') or []) if b.strip()))
    unknown = [b for b in bodies if b not in APPROVAL_BODIES]
    if unknown:
        raise ApplicabilityError(f'Unknown approval bodies {unknown}; use {APPROVAL_BODIES}.')
    type_codes = list(dict.fromkeys(data.get('institution_types') or []))
    types = list(InstitutionType.objects.filter(code__in=type_codes))
    if len(types) != len(type_codes):
        raise ApplicabilityError('Unknown institution type code(s).')
    prog_codes = list(dict.fromkeys(data.get('programme_types') or []))
    progs = list(ProgrammeType.objects.filter(code__in=prog_codes))
    if len(progs) != len(prog_codes):
        raise ApplicabilityError('Unknown programme type code(s).')
    return {'result': result, 'priority': priority, 'autonomous_statuses': statuses, 'approval_bodies': bodies,
            'jurisdiction': (data.get('jurisdiction', 'India') or '').strip(), 'reason': (data.get('reason') or '').strip()}, types, progs


def snapshot(rule):
    return {'result': rule.result, 'priority': rule.priority,
            'institution_types': sorted(rule.institution_types.values_list('code', flat=True)),
            'autonomous_statuses': rule.autonomous_statuses,
            'programme_types': sorted(rule.programme_types.values_list('code', flat=True)),
            'approval_bodies': rule.approval_bodies, 'jurisdiction': rule.jurisdiction, 'reason': rule.reason}


def _audit(user, action, rule, before, after):
    target = rule.benchmark if rule.benchmark_id else rule.requirement
    SourceAuditEvent.objects.create(actor=user.email, action=action,
                                    object_type='Benchmark' if rule.benchmark_id else 'Requirement',
                                    object_id=str(target.pk), before=before, after=after)


def create_rule(user, data, *, benchmark=None, requirement=None):
    if (benchmark is None) == (requirement is None):
        raise ApplicabilityError('A rule belongs to exactly one benchmark or one requirement.')
    _check_editable(benchmark, requirement)
    values, types, progs = _clean(data)
    with transaction.atomic():
        rule = ApplicabilityRule.objects.create(benchmark=benchmark, requirement=requirement, created_by=user, **values)
        rule.institution_types.set(types)
        rule.programme_types.set(progs)
        _audit(user, 'applicability_rule.created', rule, None, snapshot(rule))
    return rule


def update_rule(rule, user, data):
    _check_editable(rule.benchmark, rule.requirement)
    merged = {**snapshot(rule), **data}
    values, types, progs = _clean(merged)
    before = snapshot(rule)
    with transaction.atomic():
        for k, v in values.items():
            setattr(rule, k, v)
        rule.save()
        rule.institution_types.set(types)
        rule.programme_types.set(progs)
        if snapshot(rule) != before:
            _audit(user, 'applicability_rule.updated', rule, before, snapshot(rule))
    return rule


def delete_rule(rule, user):
    _check_editable(rule.benchmark, rule.requirement)
    with transaction.atomic():
        _audit(user, 'applicability_rule.deleted', rule, snapshot(rule), None)
        rule.delete()
