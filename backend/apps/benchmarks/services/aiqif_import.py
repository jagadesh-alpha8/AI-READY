"""Import InGage AI-QIF v1.0 -- the AI readiness benchmark framework -- from its master workbook.

    data = read_aiqif(path)                                   # parse + check, no DB access
    summary = apply_aiqif(data, actor=..., commit=False)      # dry run

AI-QIF is the framework the benchmark library is built on: 9 criteria (stored
as pillars, weights out of 1000) and 36 key indicators (one benchmark each,
with L3/L2/L1). Sheets used:

- "AI Benchmark Master"      one row per key indicator, with L3/L2/L1
- "AI-QIF Maturity"          what each level means per dimension (strategy,
                             governance, ...) -> each level's observable requirements
- "NAAC → AI-QIF Crosswalk"  NAAC metrics that can support a key indicator
- "AI-QIF Principles", "Scoring Architecture" -> the framework's description

Everything lands as DRAFT; the workbook itself says "requires expert validation
before publication". The L3/L2/L1 text is one template with only the key
indicator's name changed, so it is stored with is_placeholder=True: an expert
confirms or rewrites each level in the Studio (saving it clears the flag).
Re-running is safe: drafts update in place, a benchmark past draft is never
touched, a level an expert saved is kept, and expert-set target guidance is kept.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction

from ..models import (Authority, Benchmark, Capability, Framework, MaturityDefinition, Pillar, RequirementKind,
                      SourceAuditEvent)
from .catalogue_import import CatalogueSummary, _upsert

AUTHORITY = {'code': 'INGAGE', 'name': 'InGage Technologies', 'kind': Authority.Kind.INGAGE_PROPOSED}
FRAMEWORK_CODE = 'AIQIF-V1.0'
VERSION_LABEL = 'AI-QIF v1.0'
TOTAL_WEIGHT = Decimal(1000)
PLACEHOLDER_MIN_SHARED = 3

MASTER = 'AI Benchmark Master'
MATURITY = 'AI-QIF Maturity'
CROSSWALK = 'NAAC → AI-QIF Crosswalk'
PRINCIPLES = 'AI-QIF Principles'
ARCHITECTURE = 'Scoring Architecture'

# (level, column in the master sheet, column in the maturity sheet)
LEVELS = (('L3', 'L3 — Foundational'), ('L2', 'L2 — Good / Recommended'), ('L1', 'L1 — Advanced / Aspirational'))
MASTER_HEADERS = ('AI-QIF Benchmark ID', 'Criterion ID', 'Criterion', 'Criterion Weight (of 1000)', 'Key Indicator',
                  'KI Provisional Weight', 'What AI Readiness Capability Is Being Benchmarked?') + tuple(
                      h for _l, h in LEVELS)
# Columns that hold one framework-wide rule repeated on every row.
FRAMEWORK_COLUMNS = ('Why It Matters for AI Readiness', 'Benchmark Test 1 — Foundation', 'Benchmark Test 2 — Adoption',
                     'Benchmark Test 3 — Outcomes', 'Measurement Types', 'Evidence Standard', 'Applicability',
                     'Target Rule', 'Gap Rule', 'Transformation Rule', 'Primary CRI Relationship', 'Status')


def _t(v):
    return '' if v is None else ' '.join(str(v).split())


def _num(v):
    try:
        return Decimal(_t(v))
    except (InvalidOperation, ValueError):
        return None


@dataclass
class AiQif:
    criteria: list = field(default_factory=list)
    benchmarks: list = field(default_factory=list)
    framework_rules: dict = field(default_factory=dict)
    maturity: dict = field(default_factory=dict)        # level -> ["Strategy: ...", ...]
    purpose: str = ''
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


def _sheet(wb, name):
    if name not in wb.sheetnames:
        raise ValueError(f'Sheet {name!r} not found.')
    rows = [r for r in wb[name].iter_rows(values_only=True) if r and any(c not in (None, '') for c in r)]
    if not rows:
        raise ValueError(f'Sheet {name!r} is empty.')
    headers = [_t(h) for h in rows[0]]
    return [{h: r[i] if i < len(r) else None for i, h in enumerate(headers) if h} for r in rows[1:]], headers


def read_aiqif(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        master, master_headers = _sheet(wb, MASTER)
        maturity, _ = _sheet(wb, MATURITY)
        crosswalk, _ = _sheet(wb, CROSSWALK)
        principles, _ = _sheet(wb, PRINCIPLES)
        architecture, _ = _sheet(wb, ARCHITECTURE)
    finally:
        wb.close()
    missing = [h for h in MASTER_HEADERS if h not in master_headers]
    if missing:
        raise ValueError(f'{MASTER} is missing columns: {", ".join(missing)}')

    data = AiQif()
    for col in FRAMEWORK_COLUMNS:
        values = Counter(_t(r.get(col)) for r in master if _t(r.get(col)))
        if values:
            data.framework_rules[col] = values.most_common(1)[0][0]
            if len(values) > 1:
                data.warnings.append(f'"{col}" differs between rows; the most common text is used for the framework.')

    for lvl, col in LEVELS:
        data.maturity[lvl] = [f'{_t(r.get("Dimension"))}: {_t(r.get(col))}' for r in maturity
                              if _t(r.get('Dimension')) and _t(r.get(col))]

    links = defaultdict(list)
    for r in crosswalk:
        metric = _t(r.get('NAAC Metric ID'))
        kis = _key_indicators(_t(r.get('AI-QIF Key Indicator')))
        for ki in kis if metric else []:
            links[ki].append({'metric': metric, 'naac_key_indicator': _t(r.get('NAAC Key Indicator')),
                              'requirement': _t(r.get('NAAC Requirement')),
                              'relationship': _t(r.get('Relationship')),
                              'shared_with': [k for k in kis if k != ki]})

    criteria = {}
    seen = set()
    for r in master:
        code = _t(r.get('AI-QIF Benchmark ID'))
        if not code:
            continue
        crit = _t(r.get('Criterion ID'))
        b = {'code': code, 'criterion': crit, 'title': _t(r.get('Key Indicator')),
             'definition': _t(r.get('What AI Readiness Capability Is Being Benchmarked?')),
             'weight': _num(r.get('KI Provisional Weight')),
             'levels': {lvl: _t(r.get(col)) for lvl, col in LEVELS},
             'crosswalk': links.pop(code, [])}
        problems = []
        if code in seen:
            problems.append('duplicate benchmark ID')
        seen.add(code)
        if not re.fullmatch(r'[A-Z0-9-]+-C\d+\.\d+', code) or len(code) > 20:
            problems.append('ID is not like AIQIF-C1.1')
        if not crit or not code.startswith(crit + '.'):
            problems.append(f'criterion {crit!r} does not match the ID')
        if not b['title']:
            problems.append('no key indicator name')
        if b['weight'] is None:
            problems.append('no KI weight')
        if problems:
            data.errors.append(f'{code or "(blank)"}: ' + '; '.join(problems))
            continue
        c = criteria.setdefault(crit, {'code': crit, 'name': _t(r.get('Criterion')),
                                       'weight': _num(r.get('Criterion Weight (of 1000)')), 'kis': 0, 'ki_sum': Decimal(0)})
        c['kis'] += 1
        c['ki_sum'] += b['weight']
        data.benchmarks.append(b)
    data.criteria = list(criteria.values())

    # Weights: the 9 criteria add up to 1000 and each criterion's KIs add up to its weight.
    total = sum((c['weight'] or 0) for c in data.criteria)
    if total != TOTAL_WEIGHT:
        data.warnings.append(f'Criterion weights add up to {total}, not {TOTAL_WEIGHT}.')
    for c in data.criteria:
        if c['weight'] != c['ki_sum']:
            data.warnings.append(f'{c["code"]}: key indicator weights add up to {c["ki_sum"]}, criterion weight is {c["weight"]}.')
    for ki in links:
        data.warnings.append(f'Crosswalk names {ki}, which is not a key indicator; those NAAC rows were skipped.')
    unmapped = [b['code'] for b in data.benchmarks if not b['crosswalk']]
    if unmapped:
        data.warnings.append(f'{len(unmapped)} key indicators have no NAAC crosswalk (AI-specific): {", ".join(unmapped)}.')

    # Template text: the same words on many benchmarks once the KI's own name is taken off.
    for lvl, _c in LEVELS:
        bodies = Counter(_strip_title(b, lvl) for b in data.benchmarks if b['levels'][lvl])
        for b in data.benchmarks:
            text = b['levels'][lvl]
            b.setdefault('placeholder', {})[lvl] = not text or bodies[_strip_title(b, lvl)] >= PLACEHOLDER_MIN_SHARED
    n_template = sum(all(b['placeholder'].values()) for b in data.benchmarks)
    if n_template:
        data.warnings.append(f'{n_template} of {len(data.benchmarks)} key indicators use the shared L3/L2/L1 template; '
                             'imported as placeholders for experts to confirm or rewrite.')

    data.purpose = _purpose(data, principles, architecture)
    return data


def _key_indicators(text):
    """'AIQIF-C3.1 / C3.2' -> ['AIQIF-C3.1', 'AIQIF-C3.2'] (one NAAC metric can support two)."""
    out, prefix = [], ''
    for part in (p.strip() for p in text.split('/')):
        m = re.fullmatch(r'(?:([A-Z0-9]+)-)?(C\d+\.\d+)', part)
        if not m:
            if part:
                out.append(part)  # reported as unknown later
            continue
        prefix = m.group(1) or prefix or 'AIQIF'
        out.append(f'{prefix}-{m.group(2)}')
    return out


def _strip_title(b, lvl=None):
    """Level text without the leading 'Key indicator name:'."""
    levels = [lvl] if lvl else [lv for lv, _c in LEVELS]
    out = []
    for lv in levels:
        text = b['levels'][lv]
        prefix = b['title'] + ':'
        out.append(text[len(prefix):].strip() if text.startswith(prefix) else text)
    return ' | '.join(out)


def _purpose(data, principles, architecture):
    rules = data.framework_rules
    lines = ['InGage AI-QIF v1.0: 9 AI readiness criteria (weights out of 1000) and 36 key indicators, '
             'each benchmarked at L3 Foundational / L2 Good / L1 Advanced.', '', 'Principles:']
    lines += [f'- {_t(r.get("Principle"))}: {_t(r.get("Rule"))}' for r in principles if _t(r.get('Principle'))]
    lines += ['', 'Scoring architecture:']
    lines += [f'- {_t(r.get("Layer"))}: {_t(r.get("Definition"))} ({_t(r.get("Authority"))})'
              for r in architecture if _t(r.get('Layer'))]
    lines += ['', 'Rules for every key indicator:']
    lines += [f'- {col}: {rules[col]}' for col in FRAMEWORK_COLUMNS if col in rules]
    return '\n'.join(lines)


def _audit(actor, action, obj, after, reason):
    SourceAuditEvent.objects.create(actor=actor, action=action, object_type=type(obj).__name__,
                                    object_id=str(obj.pk), after=after, reason=reason)


def apply_aiqif(data, *, actor, commit=False, reason='', withdraw_others=False):
    """Save the framework. withdraw_others: also withdraw every other DRAFT benchmark
    (e.g. the earlier Source Pack catalogue), so AI-QIF is the only working set.
    Nothing is deleted, and a benchmark past draft is never changed."""
    summary = CatalogueSummary(committed=commit)
    summary.withdrawn = []
    rules = data.framework_rules
    with transaction.atomic():
        authority = _upsert(Authority, {'code': AUTHORITY['code']},
                            {'name': AUTHORITY['name'], 'kind': AUTHORITY['kind']}, summary, 'authority', actor, reason)
        framework = _upsert(Framework, {'code': FRAMEWORK_CODE},
                            {'authority': authority, 'name': f'InGage {VERSION_LABEL}', 'purpose': data.purpose},
                            summary, 'framework', actor, reason)
        pillars = {c['code']: _upsert(Pillar, {'code': c['code']}, {
            'name': c['name'], 'weight': c['weight'],
            'coverage': f'{VERSION_LABEL} criterion: {c["kis"]} key indicators, weight {c["weight"]} of 1000.',
            'catalogue_status': rules.get('Status', '')[:200],
        }, summary, 'pillar', actor, reason) for c in data.criteria}

        for b in data.benchmarks:
            existing = Benchmark.objects.filter(benchmark_code=b['code']).first()
            if existing and existing.status != Benchmark.Status.DRAFT:
                summary.locked.append(f'{b["code"]} ({existing.status}) - left unchanged')
                continue
            pillar = pillars[b['criterion']]
            capability = _upsert(Capability, {'code': f'CAP-{b["code"]}'},
                                 {'name': b['title'], 'domain': pillar.name, 'definition': b['definition'] or b['title']},
                                 summary, 'capability', actor, reason)
            values = {
                'capability': capability, 'pillar': pillar, 'framework': framework, 'title': b['title'],
                'benchmark_kind': RequirementKind.PROPOSED, 'benchmark_class': f'InGage {VERSION_LABEL} (proposed)',
                'version_label': VERSION_LABEL, 'weight': b['weight'], 'naac_crosswalk': b['crosswalk'],
                'applicability': rules.get('Applicability', ''),
                'source_basis': f'InGage {VERSION_LABEL} master workbook. {rules.get("Why It Matters for AI Readiness", "")}'.strip(),
                'scoring_dimensions': rules.get('Measurement Types', '')[:200],
                'activation_status': rules.get('Status', ''),
            }
            if not (existing and existing.target_guidance):
                values['target_guidance'] = rules.get('Target Rule', '')
            bench = _upsert(Benchmark, {'benchmark_code': b['code']}, values, summary, 'benchmark', actor, reason)
            for lvl, _c in LEVELS:
                md = MaturityDefinition.objects.filter(benchmark=bench, level=lvl).first()
                if md and md.edited_by_id:
                    summary.locked.append(f'{b["code"]} {lvl} - written by an expert, kept')
                    continue
                _upsert(MaturityDefinition, {'benchmark': bench, 'level': lvl}, {
                    'definition': b['levels'][lvl] or '(not defined)', 'is_placeholder': b['placeholder'][lvl],
                    'observable_requirements': data.maturity.get(lvl, []),
                }, summary, 'maturity_level', actor, reason)

        if withdraw_others:
            codes = {b['code'] for b in data.benchmarks}
            for other in Benchmark.objects.filter(status=Benchmark.Status.DRAFT).exclude(benchmark_code__in=codes):
                other.status = Benchmark.Status.WITHDRAWN
                other.save(update_fields=['status', 'updated_at'])
                summary.withdrawn.append(other.benchmark_code)
                _audit(actor, 'catalogue.withdraw', other, {'status': 'withdrawn'},
                       reason or f'Replaced by {VERSION_LABEL}')
        if not commit:
            transaction.set_rollback(True)
    return summary
