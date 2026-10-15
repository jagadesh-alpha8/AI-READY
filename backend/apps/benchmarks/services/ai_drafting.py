"""AI writes a benchmark's content: L3/L2/L1, evidence rules per level,
applicability rules, target guidance and owner -- for the draft AI-QIF key
indicators, so they can be released without waiting on manual authoring.

    service = get_ai_service()
    result = draft_benchmark(benchmark, service)        # one benchmark, saved

Decided with the user (2026-10-15): fully automatic -- what the AI writes
counts as the benchmark's content without a person approving it first. So
the safeguards are all mechanical, and everything is traceable:

- Output is constrained to a JSON schema whose enums are the real catalogues
  (evidence types, institution / programme types, statuses, approval bodies).
- It is saved through the SAME services a person's edit goes through
  (authoring.save_level, evidence_rules.create_rule, applicability.create_rule),
  so every check applies: no template text, each level distinct, list sizes,
  value ranges, codes, a mandatory evidence rule on every level. A benchmark
  whose draft fails any check is left exactly as it was (one transaction).
- Everything written carries `ai_model` (the model name) and is saved as the
  "AI drafter" system account, which cannot sign in; every write is in the
  audit log. A level or rule a person wrote is never overwritten.
- Only DRAFT benchmarks are touched; publishing stays a separate step.
"""
import json
import logging
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import transaction

from ..models import (
    APPROVAL_BODIES, AUTONOMOUS_STATUSES, ApplicabilityRule, Benchmark, EvidenceRule, EvidenceType, InstitutionType,
    MaturityDefinition, ProgrammeType, SourceAuditEvent,
)
from . import applicability, authoring, evidence_rules

logger = logging.getLogger(__name__)

AI_USER_EMAIL = 'ai.drafter@system.ingage.local'
LEVELS = ('L3', 'L2', 'L1')
MAX_RULES = 12
MAX_APPLICABILITY_RULES = 6
MAX_CROSSWALK_IN_PROMPT = 15

SYSTEM_PROMPT = """You are a senior expert in Indian higher-education quality assurance (NAAC, NBA, UGC, AICTE, \
NIRF) and in institutional AI readiness. You write the benchmark content for ONE key indicator of InGage AI-QIF \
v1.0, the framework used to assess colleges' AI readiness. Your output is used directly to assess real \
institutions, so it must be precise, observable and verifiable from documents a college can produce.

Write for the key indicator you are given:
1. levels: exactly three, L3, L2 and L1.
   - L3 Foundational: the capability is defined, owned, implemented for the applicable scope and usable.
   - L2 Good / Recommended: systematic across the scope, measured with indicators, adopted, reviewed, improved.
   - L1 Advanced / Aspirational: outcome-driven, data-enabled, sustained impact, scaled, externally credible.
   Each higher level includes everything in the lower one. Each `definition` is 1-3 sentences SPECIFIC to this \
indicator (what a reviewer would actually see) -- never the generic template wording you are shown. \
`measurement_rule`: how to decide the level is met (thresholds or checks, no invented statistics). \
`observable_requirements`, `minimum_evidence`, `outcome_expectations`, `non_examples`: 2-6 short items each. \
`minimum_evidence` names concrete records an Indian college would hold (e.g. "Governing-body resolution \
approving the AI policy"). `non_examples` says what does NOT count (e.g. "A one-off workshop with no follow-up").
2. evidence_rules: 3-9 rules. Every level needs at least one mandatory rule. Use only the evidence type codes \
given. minimum_currency_months: 12-36 for things that must be recent, null for permanent records. \
validation_method is usually "manual_review". privacy_classification "confidential" for personal data of \
students or staff, otherwise "internal" (or "public" for published disclosures).
3. applicability_rules: 1-3 rules. Usually one rule with result "applies" and every condition empty (applies to \
all). Add a narrower rule only when the indicator genuinely does not fit some institutions (e.g. research-heavy \
indicators for ITIs: result "requires_review"). Lower priority numbers run first. Give a plain reason.
4. target_guidance: 1-3 sentences on which level a typical institution should target and when to aim higher.

Principles (InGage AI-QIF): capability over activity -- a policy, lab, course, workshop or pilot alone does not \
establish readiness; outcomes over activity counts; responsible AI (governance, privacy, security, ethics, \
human oversight) is part of readiness; NAAC/accreditation evidence is supporting only, never proof of AI \
readiness by itself.
Never invent laws, regulation or circular numbers, named standards, dates or statistics. If unsure, describe the \
evidence generically."""


def _schema(ev_codes, inst_codes, prog_codes):
    s = {'type': 'string'}
    lst = {'type': 'array', 'items': s}
    level = {
        'type': 'object',
        'properties': {
            'level': {'type': 'string', 'enum': list(LEVELS)},
            'definition': s, 'measurement_rule': s,
            'observable_requirements': lst, 'minimum_evidence': lst, 'outcome_expectations': lst, 'non_examples': lst,
            'requires_manual_review': {'type': 'boolean'},
        },
        'required': ['level', 'definition', 'measurement_rule', 'observable_requirements', 'minimum_evidence',
                     'outcome_expectations', 'non_examples', 'requires_manual_review'],
        'additionalProperties': False,
    }
    rule = {
        'type': 'object',
        'properties': {
            'level': {'type': 'string', 'enum': list(LEVELS)},
            'evidence_type': {'type': 'string', 'enum': ev_codes},
            'title': s, 'description': s, 'scope_rule': s,
            'mandatory': {'type': 'boolean'},
            'minimum_count': {'type': 'integer'},
            'minimum_currency_months': {'type': ['integer', 'null']},
            'validation_method': {'type': 'string', 'enum': list(EvidenceRule.Validation.values)},
            'privacy_classification': {'type': 'string', 'enum': list(EvidenceRule.Privacy.values)},
        },
        'required': ['level', 'evidence_type', 'title', 'description', 'scope_rule', 'mandatory', 'minimum_count',
                     'minimum_currency_months', 'validation_method', 'privacy_classification'],
        'additionalProperties': False,
    }
    applic = {
        'type': 'object',
        'properties': {
            'result': {'type': 'string', 'enum': list(ApplicabilityRule.Result.values)},
            'priority': {'type': 'integer'},
            'institution_types': {'type': 'array', 'items': {'type': 'string', 'enum': inst_codes}},
            'programme_types': {'type': 'array', 'items': {'type': 'string', 'enum': prog_codes}},
            'autonomous_statuses': {'type': 'array', 'items': {'type': 'string', 'enum': [c for c, _ in AUTONOMOUS_STATUSES]}},
            'approval_bodies': {'type': 'array', 'items': {'type': 'string', 'enum': APPROVAL_BODIES}},
            'reason': s,
        },
        'required': ['result', 'priority', 'institution_types', 'programme_types', 'autonomous_statuses',
                     'approval_bodies', 'reason'],
        'additionalProperties': False,
    }
    return {
        'type': 'object',
        'properties': {
            'levels': {'type': 'array', 'items': level},
            'evidence_rules': {'type': 'array', 'items': rule},
            'applicability_rules': {'type': 'array', 'items': applic},
            'target_guidance': s,
            'rationale': s,
        },
        'required': ['levels', 'evidence_rules', 'applicability_rules', 'target_guidance', 'rationale'],
        'additionalProperties': False,
    }


def _context(benchmark):
    """What the AI is told about the indicator (all from the database)."""
    levels = {m.level: m for m in benchmark.maturity_levels.all()}
    lines = [
        f'Framework: InGage AI-QIF v1.0. Criterion {benchmark.pillar.code}: {benchmark.pillar.name} '
        f'(weight {benchmark.pillar.weight} of 1000).',
        f'Key indicator {benchmark.benchmark_code}: {benchmark.title} (weight {benchmark.weight} of 1000).',
        f'What is benchmarked: {benchmark.capability.definition}',
        '',
        'Generic template wording (do NOT copy; write indicator-specific levels):',
    ]
    for lv in LEVELS:
        if lv in levels:
            lines.append(f'- {lv}: {levels[lv].definition}')
            for o in levels[lv].observable_requirements or []:
                lines.append(f'    dimension guide: {o}')
    links = benchmark.naac_crosswalk or []
    if links:
        lines += ['', 'NAAC metrics whose evidence can SUPPORT this indicator (supporting only):']
        lines += [f'- {x.get("metric")}: {(x.get("requirement") or "")[:220]}' for x in links[:MAX_CROSSWALK_IN_PROMPT]]
    lines += ['', 'Evidence type catalogue (use these codes):']
    lines += [f'- {e.code} {e.name}: e.g. {e.examples}' for e in EvidenceType.objects.order_by('code')]
    lines += ['', 'Institution types: ' + ', '.join(f'{t.code} ({t.name})' for t in InstitutionType.objects.order_by('code')),
              'Programme types: ' + ', '.join(f'{t.code} ({t.name})' for t in ProgrammeType.objects.order_by('code')),
              'Autonomous statuses: ' + ', '.join(f'{c} ({n})' for c, n in AUTONOMOUS_STATUSES),
              'Approval bodies: ' + ', '.join(APPROVAL_BODIES)]
    return '\n'.join(lines)


class DraftRejected(Exception):
    """The AI's draft failed a check; nothing was saved."""


@dataclass
class DraftResult:
    code: str
    ok: bool
    detail: str = ''
    levels: int = 0
    evidence_rules: int = 0
    applicability_rules: int = 0
    kept_human: list = field(default_factory=list)


def ai_user():
    """The system account AI-written content is saved as. It can never sign in."""
    User = get_user_model()
    user = User.objects.filter(email=AI_USER_EMAIL).first()
    if user is None:
        user = User(email=AI_USER_EMAIL, username='ai-drafter', first_name='AI', last_name='Drafter',
                    role=User.Role.CONSULTANT, is_active=False)
        user.set_unusable_password()
        user.save()
    return user


def _check(draft):
    levels = {x.get('level'): x for x in draft.get('levels') or []}
    if sorted(levels) != sorted(LEVELS) or len(draft.get('levels') or []) != 3:
        raise DraftRejected('needs exactly one L3, one L2 and one L1')
    rules = draft.get('evidence_rules') or []
    if not 1 <= len(rules) <= MAX_RULES:
        raise DraftRejected(f'needs 1-{MAX_RULES} evidence rules, got {len(rules)}')
    missing = [lv for lv in LEVELS if not any(r.get('level') == lv and r.get('mandatory') for r in rules)]
    if missing:
        raise DraftRejected(f'no mandatory evidence rule for {", ".join(missing)}')
    applic = draft.get('applicability_rules') or []
    if not 1 <= len(applic) <= MAX_APPLICABILITY_RULES:
        raise DraftRejected(f'needs 1-{MAX_APPLICABILITY_RULES} applicability rules, got {len(applic)}')
    return levels, rules, applic


def draft_benchmark(benchmark, service, *, user=None):
    """Ask the AI for one benchmark's content and save it. Returns a DraftResult;
    on any failed check nothing is saved and the benchmark is unchanged."""
    code = benchmark.benchmark_code
    if benchmark.status != Benchmark.Status.DRAFT:
        return DraftResult(code, False, f'is {benchmark.status}; only drafts are written')
    user = user or ai_user()
    model = (getattr(service, 'model', '') or 'unknown-model')[:150]
    ev_codes = list(EvidenceType.objects.order_by('code').values_list('code', flat=True))
    if not ev_codes:
        return DraftResult(code, False, 'the evidence type catalogue is empty')
    schema = _schema(ev_codes, list(InstitutionType.objects.values_list('code', flat=True)),
                     list(ProgrammeType.objects.values_list('code', flat=True)))
    try:
        draft = service.extract_structured_data(
            system_prompt=SYSTEM_PROMPT, user_content=_context(benchmark), response_schema=schema,
            schema_name='benchmark_content', timeout=240)
    except Exception as exc:  # the provider failed; nothing to save
        logger.warning('benchmarks.ai_draft.call_failed code=%s error=%s', code, exc)
        return DraftResult(code, False, f'AI call failed: {exc}'[:500])

    result = DraftResult(code, True)
    try:
        levels, rules, applic = _check(draft or {})
        with transaction.atomic():
            human_levels = {m.level for m in benchmark.maturity_levels.all()
                            if m.edited_by_id and m.edited_by_id != user.pk and not m.ai_model}
            for lv in LEVELS:
                if lv in human_levels:
                    result.kept_human.append(f'{lv} level')
                    continue
                md = authoring.save_level(benchmark, lv, user, {**levels[lv], 'note': f'AI-generated by {model}'})
                MaturityDefinition.objects.filter(pk=md.pk).update(ai_model=model)
                result.levels += 1

            # Replace earlier AI rules; rules a person wrote stay.
            for old in EvidenceRule.objects.filter(benchmark=benchmark).exclude(ai_model=''):
                evidence_rules.delete_rule(old, user)
            for r in rules:
                rule = evidence_rules.create_rule(user, r, benchmark=benchmark)
                EvidenceRule.objects.filter(pk=rule.pk).update(ai_model=model)
                result.evidence_rules += 1
            if EvidenceRule.objects.filter(benchmark=benchmark, ai_model='').exists():
                result.kept_human.append('evidence rules written by a person')

            for old in ApplicabilityRule.objects.filter(benchmark=benchmark).exclude(ai_model=''):
                applicability.delete_rule(old, user)
            for a in applic:
                rule = applicability.create_rule(user, {**a, 'jurisdiction': 'India'}, benchmark=benchmark)
                ApplicabilityRule.objects.filter(pk=rule.pk).update(ai_model=model)
                result.applicability_rules += 1

            owner = benchmark.expert_owner
            values = {'target_guidance': (draft.get('target_guidance') or '').strip()}
            if not owner or owner.startswith('AI '):
                values['expert_owner'] = f'AI (auto) - {model}'[:150]
            authoring.update_benchmark(benchmark, user, values)
            SourceAuditEvent.objects.create(
                actor=user.email, action='benchmark.ai_drafted', object_type='Benchmark', object_id=str(benchmark.pk),
                after={'model': model, 'levels': result.levels, 'evidence_rules': result.evidence_rules,
                       'applicability_rules': result.applicability_rules, 'kept_human': result.kept_human,
                       'rationale': (draft.get('rationale') or '')[:2000]},
                reason='Fully automatic AI drafting (no expert review), as decided on 2026-10-15.')
    except (DraftRejected, authoring.AuthoringError, evidence_rules.EvidenceRuleError,
            applicability.ApplicabilityError) as exc:
        logger.warning('benchmarks.ai_draft.rejected code=%s reason=%s', code, exc)
        return DraftResult(code, False, f'draft rejected: {exc}'[:500])
    result.detail = (f'{result.levels} levels, {result.evidence_rules} evidence rules, '
                     f'{result.applicability_rules} applicability rules by {model}')
    return result


def draft_many(benchmarks, *, actor='ai_draft_benchmarks'):
    """Draft several benchmarks with one AI service (call inside a router lease in multi_router mode)."""
    from apps.extraction.models import AIUsage
    from apps.extraction.services.ai_service import get_ai_service
    from apps.extraction.usage import usage_scope

    service = get_ai_service()
    user = ai_user()
    results = []
    with usage_scope(stage=AIUsage.Stage.OTHER):
        for b in benchmarks:
            results.append(draft_benchmark(b, service, user=user))
            logger.info('benchmarks.ai_draft code=%s ok=%s %s', b.benchmark_code, results[-1].ok, results[-1].detail)
    return results


def summary_json(results):
    return json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=1)
