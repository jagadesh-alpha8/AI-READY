"""Stage 3.3: experts write each benchmark's real L3/L2/L1 levels.

Rules (server-side):
- Only a draft benchmark can be edited.
- A definition must be benchmark-specific: at least MIN_DEFINITION_CHARS, not
  the Source Pack's shared template text, and different from the other two levels.
- Saving real text clears is_placeholder; every save is audited with before/after,
  so the level history can always be shown.
- readiness() lists what a benchmark still needs before it can go into a release
  (stage 3.6). Items for later stages (evidence rules, scoring rules,
  transformation templates) are listed as pending, never silently "ok".
"""
from django.db import transaction
from django.utils import timezone

from ..models import (
    Benchmark, BenchmarkRequirement, EvidenceRule, MaturityDefinition, RequirementKind, SourceAuditEvent,
)

MIN_DEFINITION_CHARS = 40
LIST_FIELDS = ('observable_requirements', 'minimum_evidence', 'outcome_expectations', 'non_examples')
MAX_LIST_ITEMS = 20
MAX_ITEM_CHARS = 500


class AuthoringError(Exception):
    pass


def _norm(text):
    return ' '.join((text or '').split()).lower()


def _clean_list(name, value):
    if value in (None, ''):
        return []
    if not isinstance(value, list):
        raise AuthoringError(f'{name} must be a list of short statements.')
    items = [str(v).strip() for v in value if str(v).strip()]
    if len(items) > MAX_LIST_ITEMS:
        raise AuthoringError(f'{name}: at most {MAX_LIST_ITEMS} items.')
    if any(len(v) > MAX_ITEM_CHARS for v in items):
        raise AuthoringError(f'{name}: each item at most {MAX_ITEM_CHARS} characters.')
    return items


def _snapshot(md):
    return {'definition': md.definition, 'measurement_rule': md.measurement_rule, 'is_placeholder': md.is_placeholder,
            'requires_manual_review': md.requires_manual_review, **{f: getattr(md, f) for f in LIST_FIELDS}}


def _require_draft(benchmark):
    from .release_lock import lock_message
    if benchmark.status != Benchmark.Status.DRAFT:
        raise AuthoringError(f'{benchmark.benchmark_code} is {benchmark.status}; edit it in a new draft version.')
    if lock_message(benchmark):
        raise AuthoringError(lock_message(benchmark))


def save_level(benchmark, level, user, data):
    _require_draft(benchmark)
    if level not in MaturityDefinition.Level.values:
        raise AuthoringError(f'level must be one of {MaturityDefinition.Level.values}.')
    definition = ' '.join((data.get('definition') or '').split())
    if len(definition) < MIN_DEFINITION_CHARS:
        raise AuthoringError(f'Write a benchmark-specific definition (at least {MIN_DEFINITION_CHARS} characters).')
    if MaturityDefinition.objects.filter(is_placeholder=True).exclude(benchmark=benchmark).filter(
            definition__iexact=definition).exists() or _is_template(definition):
        raise AuthoringError('This is the Source Pack template text shared by many benchmarks; '
                             'describe what this level means for this benchmark.')
    others = benchmark.maturity_levels.exclude(level=level)
    if any(_norm(o.definition) == _norm(definition) for o in others if not o.is_placeholder):
        raise AuthoringError('Each level needs its own definition (this one matches another level).')
    lists = {f: _clean_list(f, data.get(f)) for f in LIST_FIELDS}

    with transaction.atomic():
        md, _ = MaturityDefinition.objects.select_for_update().get_or_create(
            benchmark=benchmark, level=level, defaults={'definition': definition})
        before = _snapshot(md)
        md.definition = definition
        md.measurement_rule = (data.get('measurement_rule') or '').strip()
        md.requires_manual_review = bool(data.get('requires_manual_review'))
        for f, items in lists.items():
            setattr(md, f, items)
        md.is_placeholder = False
        md.ai_model = ''  # written (or edited) by this user; the AI drafter re-labels its own saves
        md.edited_by, md.edited_at = user, timezone.now()
        md.save()
        SourceAuditEvent.objects.create(actor=user.email, action='benchmark.level_saved', object_type='Benchmark',
                                        object_id=str(benchmark.pk), before={'level': level, **before},
                                        after={'level': level, **_snapshot(md)}, reason=data.get('note', ''))
    return md


def _is_template(definition):
    """True if the text equals a placeholder still stored on 3+ benchmarks (the shared template)."""
    from django.db.models import Count
    return (MaturityDefinition.objects.filter(is_placeholder=True, definition__iexact=definition)
            .values('definition').annotate(n=Count('id')).filter(n__gte=3).exists())


def update_benchmark(benchmark, user, data):
    _require_draft(benchmark)
    changed = {}
    for field in ('expert_owner', 'target_guidance'):
        if field in data:
            value = (data.get(field) or '').strip()
            if getattr(benchmark, field) != value:
                changed[field] = (getattr(benchmark, field), value)
                setattr(benchmark, field, value)
    if changed:
        benchmark.save()
        SourceAuditEvent.objects.create(actor=user.email, action='benchmark.updated', object_type='Benchmark',
                                        object_id=str(benchmark.pk), before={k: v[0] for k, v in changed.items()},
                                        after={k: v[1] for k, v in changed.items()})
    return benchmark


def _confirmation_ok(benchmark):
    from .confirmation import CONFIRMED, state
    return state(benchmark) == CONFIRMED


def _confirmation_detail(benchmark):
    from .confirmation import CHANGED, CONFIRMED, state
    s = state(benchmark)
    if s == CONFIRMED:
        return f'by {benchmark.confirmed_by.email} on {benchmark.confirmed_at:%d %b %Y}'
    if s == CHANGED:
        return 'changed since it was confirmed - confirm again'
    return 'not confirmed'


def readiness(benchmark):
    """Checklist for release. severity: required | recommended | pending (later stage)."""
    levels = {m.level: m for m in benchmark.maturity_levels.all()}
    defined = [lv for lv in ('L3', 'L2', 'L1') if lv in levels and not levels[lv].is_placeholder]
    links = BenchmarkRequirement.objects.filter(benchmark=benchmark)
    primary = links.filter(relationship=BenchmarkRequirement.Relationship.PRIMARY).count()
    proposed = benchmark.benchmark_kind == RequirementKind.PROPOSED
    non_examples = sum(len(m.non_examples or []) for m in levels.values())
    from .evidence_rules import level_coverage
    coverage = level_coverage(benchmark)
    primary_ids = set(links.filter(relationship=BenchmarkRequirement.Relationship.PRIMARY)
                      .values_list('requirement_id', flat=True))
    reqs_with_rules = set(EvidenceRule.objects.filter(requirement_id__in=primary_ids)
                          .values_list('requirement_id', flat=True))
    from .release_gates import applicability_detail, score_rule_status, validate_applicability
    applic_check = validate_applicability(benchmark)
    scoring_ok, scoring_detail = score_rule_status(benchmark)
    checks = [
        ('levels', 'L3, L2 and L1 written for this benchmark', 'required', len(defined) == 3,
         f'{len(defined)}/3 defined' + ('' if len(defined) == 3 else ' (others are placeholders)')),
        ('owner', 'Expert owner named', 'required' if proposed else 'recommended', bool(benchmark.expert_owner),
         benchmark.expert_owner or 'none'),
        ('requirements', 'Linked to approved requirements (primary)', 'recommended' if proposed else 'required',
         primary > 0, f'{primary} primary, {links.count()} total'),
        ('evidence_types', 'Evidence types chosen', 'required', benchmark.evidence_types.exists(),
         ', '.join(benchmark.evidence_types.values_list('code', flat=True)) or 'none'),
        ('applicability', 'Applicability rules written', 'required', benchmark.applicability_rules.exists(),
         f'{benchmark.applicability_rules.count()} rule(s)' + ('' if benchmark.applicability_rules.exists()
                                                             else f' - Source Pack text: {benchmark.applicability or "none"}')),
        ('non_examples', 'Non-examples (what does not count)', 'recommended', non_examples > 0, f'{non_examples} given'),
        ('evidence_rules', 'Mandatory evidence rule for every level', 'required', all(coverage.values()),
         ', '.join(f'{lv}: {n}' for lv, n in coverage.items())),
        ('requirement_evidence', 'Evidence rules on each primary requirement', 'recommended',
         primary_ids.issubset(reqs_with_rules), f'{len(primary_ids & reqs_with_rules)}/{len(primary_ids)} covered'),
        ('applicability_coverage', 'Applicability rules checked against every supported profile', 'recommended',
         applic_check['ok'], applicability_detail(applic_check)),
        # Scoring weights are human-approved per benchmark; a release that needs a composite score
        # turns this into a blocker (services/releases.py check_release).
        ('scoring', 'Approved scoring weights (composite score)', 'recommended', scoring_ok, scoring_detail),
        # Required: an InGage reviewer confirms the content before the release can be submitted.
        ('confirmed', 'Content confirmed by an InGage reviewer', 'required', _confirmation_ok(benchmark),
         _confirmation_detail(benchmark)),
    ]
    items = [{'key': k, 'label': lbl, 'severity': sev, 'ok': ok, 'detail': det} for k, lbl, sev, ok, det in checks]
    return {'ready_for_review': all(i['ok'] for i in items if i['severity'] == 'required'), 'checks': items}


def history(benchmark, limit=100):
    return SourceAuditEvent.objects.filter(object_type='Benchmark', object_id=str(benchmark.pk)).order_by('-created_at')[:limit]
