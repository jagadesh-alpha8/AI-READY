"""Stage 3.4: evidence rules -- what evidence proves a benchmark level or a requirement.

Guards:
- benchmark rules change only while the benchmark is a draft;
- requirement rules change only while every benchmark linked to the requirement
  is a draft (a released benchmark's evidence basis can't move under it);
- a benchmark rule using an evidence type the benchmark doesn't list yet adds
  that type to the benchmark (audited), so the two never disagree;
- every create / update / delete is audited.
"""
from django.db import IntegrityError, transaction

from ..models import Benchmark, EvidenceRule, EvidenceType, MaturityDefinition, SourceAuditEvent

EDITABLE_FIELDS = ('title', 'description', 'mandatory', 'minimum_count', 'minimum_currency_months', 'scope_rule',
                   'validation_method', 'privacy_classification')


class EvidenceRuleError(Exception):
    pass


def _check_editable(benchmark=None, requirement=None):
    from .release_lock import lock_message
    if benchmark is not None and benchmark.status != Benchmark.Status.DRAFT:
        raise EvidenceRuleError(f'{benchmark.benchmark_code} is {benchmark.status}; change its evidence rules in a new draft.')
    if benchmark is not None and lock_message(benchmark):
        raise EvidenceRuleError(lock_message(benchmark))
    if requirement is not None:
        locked = requirement.benchmarks.exclude(status=Benchmark.Status.DRAFT).values_list('benchmark_code', flat=True)
        if locked:
            raise EvidenceRuleError(f'{requirement.code} is part of released benchmark(s) {", ".join(locked)}; '
                                    'its evidence rules can only change in a new draft.')


def _clean(data, *, partial=False):
    out = {}
    if 'title' in data or not partial:
        title = (data.get('title') or '').strip()
        if len(title) < 5:
            raise EvidenceRuleError('Give the rule a short title (at least 5 characters).')
        out['title'] = title[:200]
    for f in ('description', 'scope_rule'):
        if f in data:
            out[f] = (data.get(f) or '').strip()
    if 'mandatory' in data:
        out['mandatory'] = bool(data.get('mandatory'))
    if 'minimum_count' in data:
        raw = data.get('minimum_count')
        try:
            out['minimum_count'] = 1 if raw in (None, '') else int(raw)  # 0 must be refused, not turned into 1
        except (TypeError, ValueError):
            raise EvidenceRuleError('minimum_count must be a whole number.')
        if not 1 <= out['minimum_count'] <= 100:
            raise EvidenceRuleError('minimum_count must be between 1 and 100.')
    if 'minimum_currency_months' in data:
        months = data.get('minimum_currency_months')
        if months in (None, ''):
            out['minimum_currency_months'] = None
        else:
            try:
                out['minimum_currency_months'] = int(months)
            except (TypeError, ValueError):
                raise EvidenceRuleError('minimum_currency_months must be a whole number of months.')
            if not 1 <= out['minimum_currency_months'] <= 120:
                raise EvidenceRuleError('minimum_currency_months must be between 1 and 120.')
    for f, choices in (('validation_method', EvidenceRule.Validation.values),
                       ('privacy_classification', EvidenceRule.Privacy.values)):
        if f in data:
            if data.get(f) not in choices:
                raise EvidenceRuleError(f'{f} must be one of {choices}.')
            out[f] = data[f]
    return out


def _snapshot(rule):
    return {'target': rule.requirement.code if rule.requirement_id else rule.benchmark.benchmark_code,
            'level': rule.level, 'evidence_type': rule.evidence_type.code,
            **{f: getattr(rule, f) for f in EDITABLE_FIELDS}}


def _audit(user, action, rule, before, after):
    target = rule.benchmark if rule.benchmark_id else rule.requirement
    SourceAuditEvent.objects.create(actor=user.email, action=action,
                                    object_type='Benchmark' if rule.benchmark_id else 'Requirement',
                                    object_id=str(target.pk), before=before, after=after)


def create_rule(user, data, *, benchmark=None, requirement=None):
    if (benchmark is None) == (requirement is None):
        raise EvidenceRuleError('A rule belongs to exactly one benchmark or one requirement.')
    _check_editable(benchmark, requirement)
    ev = EvidenceType.objects.filter(code=(data.get('evidence_type') or '').upper()).first()
    if ev is None:
        raise EvidenceRuleError('evidence_type must be an EV code from the evidence catalogue (e.g. EV-01).')
    level = (data.get('level') or '').upper()
    if requirement is not None and level:
        raise EvidenceRuleError('Requirement rules apply to the requirement as a whole; leave level empty.')
    if level and level not in MaturityDefinition.Level.values:
        raise EvidenceRuleError(f'level must be one of {MaturityDefinition.Level.values} or empty.')
    values = _clean(data)
    with transaction.atomic():
        try:
            rule = EvidenceRule.objects.create(benchmark=benchmark, requirement=requirement, level=level,
                                               evidence_type=ev, created_by=user, **values)
        except IntegrityError:
            raise EvidenceRuleError(f'{requirement.code} already has a rule for {ev.code}; edit that one.')
        if benchmark is not None and not benchmark.evidence_types.filter(pk=ev.pk).exists():
            benchmark.evidence_types.add(ev)
            SourceAuditEvent.objects.create(actor=user.email, action='benchmark.evidence_type_added',
                                            object_type='Benchmark', object_id=str(benchmark.pk),
                                            after={'evidence_type': ev.code, 'via_rule': rule.title})
        _audit(user, 'evidence_rule.created', rule, None, _snapshot(rule))
    return rule


def update_rule(rule, user, data):
    _check_editable(rule.benchmark, rule.requirement)
    values = _clean(data, partial=True)
    before = _snapshot(rule)
    for k, v in values.items():
        setattr(rule, k, v)
    if _snapshot(rule) != before:
        rule.save()
        _audit(user, 'evidence_rule.updated', rule, before, _snapshot(rule))
    return rule


def delete_rule(rule, user):
    _check_editable(rule.benchmark, rule.requirement)
    snap = _snapshot(rule)
    with transaction.atomic():
        _audit(user, 'evidence_rule.deleted', rule, snap, None)
        rule.delete()


def level_coverage(benchmark):
    """{level: number of mandatory rules that apply to it} -- an any-level rule counts for all three."""
    rules = list(benchmark.evidence_rules.filter(mandatory=True).values_list('level', flat=True))
    return {lv: sum(1 for r in rules if r in ('', lv)) for lv in ('L3', 'L2', 'L1')}
