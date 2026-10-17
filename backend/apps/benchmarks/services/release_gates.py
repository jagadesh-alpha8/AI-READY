"""Checks the release workflow shows before a release is submitted (all deterministic; nothing
here writes or generates content -- scoring weights and applicability rules stay human-authored).

- score_rule_status(benchmark): does it have valid, approved scoring weights for the active
  scoring model, so an assessment can produce a composite score?
- validate_applicability(benchmark): run the benchmark's saved applicability rules against every
  supported institution profile and report rules that never decide anything (overridden by an
  earlier rule), profiles no rule matches, and profiles that end up "requires review".
"""
from collections import Counter, defaultdict
from decimal import Decimal

from ..models import APPROVAL_BODIES, AUTONOMOUS_STATUSES, ApplicabilityRule, InstitutionType, ProgrammeType
from .applicability import Profile, _check

STATUS_CODES = [c for c, _ in AUTONOMOUS_STATUSES]


# -- scoring rules -------------------------------------------------------------------------

def active_scoring_model():
    from apps.assessments.models import ScoringModel
    return ScoringModel.objects.filter(active=True).first()


def score_rule_status(benchmark, model=None):
    """(ok, detail). ok = approved weights exist for the active model and add up to 1."""
    from apps.assessments.models import BenchmarkScoreRule
    model = model if model is not None else active_scoring_model()
    if model is None:
        return False, 'there is no active scoring model'
    rule = BenchmarkScoreRule.objects.filter(benchmark=benchmark, scoring_model=model).select_related('approved_by').first()
    if rule is None:
        return False, f'no approved weights for {model.code}'
    total = sum(rule.weights().values(), Decimal(0))
    if total != 1:
        return False, f'weights for {model.code} add up to {total}, not 1'
    who = rule.approved_by.email if rule.approved_by_id else 'unknown'
    return True, f'{model.code}: ' + ', '.join(f'{k.replace("_", " ")} {w}' for k, w in rule.weights().items()) + f' (approved by {who})'


# -- applicability -------------------------------------------------------------------------

def _profiles():
    """Every supported profile: institution type x status (or none) x one programme (or none)
    x one approval body (or none), in India."""
    types = list(InstitutionType.objects.order_by('code').values_list('code', flat=True))
    progs = [None] + list(ProgrammeType.objects.order_by('code').values_list('code', flat=True))
    for t in types:
        for st in [''] + STATUS_CODES:
            for p in progs:
                for b in [None] + list(APPROVAL_BODIES):
                    yield Profile(t, st, {p} if p else set(), {b} if b else set())


def _describe(profile):
    parts = [profile.institution_type, profile.autonomous_status or 'no status']
    parts.append(next(iter(profile.programme_types)) if profile.programme_types else 'no programme')
    parts.append(next(iter(profile.approval_bodies)) if profile.approval_bodies else 'no approval body')
    return ' / '.join(parts)


def validate_applicability(benchmark):
    rules = sorted(ApplicabilityRule.objects.filter(benchmark=benchmark)
                   .prefetch_related('institution_types', 'programme_types'), key=lambda r: (r.priority, r.created_at))
    if not rules:
        return {'has_rules': False, 'profiles_checked': 0, 'by_result': {}, 'rules': [], 'unmatched': None,
                'requires_review': None, 'issues': ['No applicability rules: every college sees this benchmark as '
                                                    '"requires review".'], 'ok': False}
    compiled = [(r, {t.code: t.name for t in r.institution_types.all()}, {p.code: p.name for p in r.programme_types.all()})
                for r in rules]
    matches, decides = Counter(), Counter()
    overridden_by = defaultdict(Counter)
    by_result = Counter()
    unmatched, review = defaultdict(int), defaultdict(int)
    unmatched_example, review_example = {}, {}
    total = 0
    for profile in _profiles():
        total += 1
        winner = None
        for i, (rule, types, progs) in enumerate(compiled):
            if all(ok for _, ok in _check(profile, types, rule.autonomous_statuses, progs, rule.approval_bodies,
                                          rule.jurisdiction)):
                matches[i] += 1
                if winner is None:
                    winner = i
                    decides[i] += 1
                else:
                    overridden_by[i][winner] += 1
        if winner is None:
            by_result['does_not_apply (no rule matched)'] += 1
            unmatched[profile.institution_type] += 1
            unmatched_example.setdefault(profile.institution_type, _describe(profile))
        else:
            result = compiled[winner][0].result
            by_result[result] += 1
            if result == ApplicabilityRule.Result.REQUIRES_REVIEW:
                review[profile.institution_type] += 1
                review_example.setdefault(profile.institution_type, _describe(profile))

    rows, issues = [], []
    for i, (rule, _t, _p) in enumerate(compiled):
        note = ''
        if matches[i] == 0:
            note = 'matches no supported institution profile'
        elif decides[i] == 0:
            earlier = ', '.join(f'#{compiled[j][0].priority}' for j in overridden_by[i])
            note = f'never decides: always overridden by earlier rule(s) {earlier}'
        elif overridden_by[i]:
            earlier = ', '.join(f'#{compiled[j][0].priority}' for j in overridden_by[i])
            note = f'partly overridden by earlier rule(s) {earlier} for {sum(overridden_by[i].values())} profile(s)'
        rows.append({'id': str(rule.pk), 'priority': rule.priority, 'result': rule.result, 'matches': matches[i],
                     'decides': decides[i], 'note': note})
        if matches[i] == 0 or decides[i] == 0:
            issues.append(f'Rule #{rule.priority} ({rule.get_result_display().lower()}) {note}.')

    def summary(counts, examples):
        if not counts:
            return None
        return {'count': sum(counts.values()), 'by_institution_type': dict(counts), 'examples': examples}

    return {
        'has_rules': True, 'profiles_checked': total, 'by_result': dict(by_result), 'rules': rows,
        'unmatched': summary(unmatched, unmatched_example), 'requires_review': summary(review, review_example),
        'issues': issues, 'ok': not issues,
    }


def applicability_detail(v):
    if not v['has_rules']:
        return 'no rules'
    parts = [f'{v["profiles_checked"]} profiles checked']
    if v['requires_review']:
        parts.append(f'{v["requires_review"]["count"]} end as "requires review"')
    if v['unmatched']:
        parts.append(f'{v["unmatched"]["count"]} match no rule (does not apply)')
    if v['issues']:
        parts.append('; '.join(v['issues']))
    return ' · '.join(parts)
