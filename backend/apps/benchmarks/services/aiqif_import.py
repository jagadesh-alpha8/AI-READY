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
- "AI-QIF Source References"  (optional) one row per source reference of a key
                             indicator: Source Library code, version, page, exact
                             quote, relationship. v1.0 has no such sheet.

The workbook is the authoritative standard catalogue (Benchmark Studio is read-only):
this import is the controlled way it changes -- a dry run first, which lists every
change, then --commit; --baseline then freezes it as the release assessments use
(services/baseline.py).

Provenance (services/provenance.py): every indicator records its origin -- this
workbook (name and SHA-256), its sheet and row, the framework version and the import
date. That is the indicator's origin, not a source document. Source mappings come
only from the workbook's source-reference sheet: each is linked to the Source
Library version it names when that version exists and the quote is in its text
(when it has text); anything else stays listed as "not linked" with the reason --
never inferred or invented.

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

import hashlib
import os

from django.utils import timezone

from ..models import (Authority, Benchmark, BenchmarkRequirement, Capability, Framework, MaturityDefinition, Pillar,
                      Requirement, RequirementKind, SourceAuditEvent, SourceDocument, SourceVersion)
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
SOURCE_REFS = 'AI-QIF Source References'
SOURCE_REF_HEADERS = ('AI-QIF Benchmark ID', 'Source Code', 'Exact Quote')
ROW = '__row__'  # the spreadsheet row number of a parsed row

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
    workbook: str = ''
    workbook_sha256: str = ''
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
    rows = [(n, r) for n, r in enumerate(wb[name].iter_rows(values_only=True), start=1)
            if r and any(c not in (None, '') for c in r)]
    if not rows:
        raise ValueError(f'Sheet {name!r} is empty.')
    headers = [_t(h) for h in rows[0][1]]
    return [{ROW: n, **{h: r[i] if i < len(r) else None for i, h in enumerate(headers) if h}}
            for n, r in rows[1:]], headers


def read_aiqif(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        master, master_headers = _sheet(wb, MASTER)
        maturity, _ = _sheet(wb, MATURITY)
        crosswalk, _ = _sheet(wb, CROSSWALK)
        principles, _ = _sheet(wb, PRINCIPLES)
        architecture, _ = _sheet(wb, ARCHITECTURE)
        refs, ref_headers = _sheet(wb, SOURCE_REFS) if SOURCE_REFS in wb.sheetnames else ([], [])
    finally:
        wb.close()
    missing = [h for h in MASTER_HEADERS if h not in master_headers]
    if missing:
        raise ValueError(f'{MASTER} is missing columns: {", ".join(missing)}')

    with open(path, 'rb') as fh:
        sha256 = hashlib.sha256(fh.read()).hexdigest()
    data = AiQif(workbook=os.path.basename(str(path)), workbook_sha256=sha256)
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
             'crosswalk': links.pop(code, []), 'row': r[ROW], 'source_refs': []}
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
    _read_source_refs(data, refs, ref_headers)

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
                             'kept as the workbook wrote them and marked "template wording".')

    data.purpose = _purpose(data, principles, architecture)
    return data


def _read_source_refs(data, refs, headers):
    """The optional source-reference sheet -> each benchmark's `source_refs` (kept as written; linked later)."""
    if not headers:
        data.warnings.append(f'No "{SOURCE_REFS}" sheet: the {len(data.benchmarks)} key indicators get the workbook as '
                             'their origin, with no source document linked.')
        return
    missing = [h for h in SOURCE_REF_HEADERS if h not in headers]
    if missing:
        data.errors.append(f'{SOURCE_REFS} is missing columns: {", ".join(missing)}')
        return
    by_code = {b['code']: b for b in data.benchmarks}
    for r in refs:
        code, source, quote = (_t(r.get(h)) for h in SOURCE_REF_HEADERS)
        if not (code or source or quote):
            continue
        where = f'{SOURCE_REFS} row {r[ROW]}'
        rel = _t(r.get('Relationship')).lower() or BenchmarkRequirement.Relationship.SUPPORTING
        page = _t(r.get('Page'))
        problems = []
        if code not in by_code:
            problems.append(f'{code or "(blank)"} is not a key indicator')
        if not source or not quote:
            problems.append('needs a source code and the exact quote')
        if rel not in BenchmarkRequirement.Relationship.values:
            problems.append(f'relationship {rel!r} is not primary / supporting / crosswalk')
        if page and not page.isdigit():
            problems.append(f'page {page!r} is not a number')
        if problems:
            data.errors.append(f'{where}: ' + '; '.join(problems))
            continue
        by_code[code]['source_refs'].append({
            'sheet': SOURCE_REFS, 'row': r[ROW], 'source_code': source, 'source_version': _t(r.get('Source Version')),
            'page': int(page) if page else None, 'source_quote': quote, 'relationship': rel,
            'statement': _t(r.get('Requirement Statement'))})


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


def _origin(data, b, existing, actor):
    """The indicator's origin: this workbook, sheet and row. The import date is the first import of this
    workbook (kept on re-runs, so a re-import changes nothing that did not change)."""
    from .provenance import origin_of
    before = origin_of(existing) if existing else {}
    same_book = before.get('type') == Benchmark.Origin.FRAMEWORK_IMPORT and before.get('workbook') == data.workbook
    return {'workbook': data.workbook, 'workbook_sha256': data.workbook_sha256, 'framework': FRAMEWORK_CODE,
            'framework_version': VERSION_LABEL,
            'sheet': MASTER, 'row': b['row'], 'indicator_code': b['code'],
            'imported_at': before['imported_at'] if same_book and before.get('imported_at') else timezone.now().isoformat(),
            'imported_by': before['imported_by'] if same_book and before.get('imported_by') else actor}


def _ref_plan(ref, existing):
    """How one workbook source reference lands: (status, version or None). Linked only to a real Source Library
    version, and only when the quote is in its text (when it has text)."""
    from .provenance import quote_check
    doc = SourceDocument.objects.filter(source_code=ref['source_code']).first()
    if doc is None:
        return f'not linked: {ref["source_code"]} is not in the Source Library', None
    versions = doc.versions.exclude(status=SourceVersion.Status.WITHDRAWN)
    version = (versions.filter(version_label=ref['source_version']).first() if ref['source_version']
               else versions.order_by('-issued_on', '-created_at').first())
    if version is None:
        wanted = f'version {ref["source_version"]}' if ref['source_version'] else 'current version'
        return f'not linked: no {wanted} of {doc.source_code}', None
    if existing is not None:
        found = BenchmarkRequirement.objects.filter(
            benchmark=existing, requirement__version=version, requirement__page=ref['page'],
            requirement__source_quote=ref['source_quote']).select_related('requirement').first()
        if found:
            return f'linked as {found.requirement.code}', None
    if quote_check(version, ref['source_quote'], ref['page']) is False:
        where = f'on page {ref["page"]} of' if ref['page'] else 'in'
        return f'not linked: the quote is not {where} {version}', None
    return 'to link', version


def _link_ref(bench, version, ref, data, actor, linked_by):
    """The workbook's mapping -> a requirement marked as the workbook's (no approver: the workbook is
    authoritative) linked to the indicator. Returns the requirement code."""
    from .linking import _check_draft
    from .requirement_drafting import _next_code
    _check_draft(bench)  # LinkError when the indicator is locked
    wb = {'workbook': data.workbook, 'workbook_sha256': data.workbook_sha256, 'sheet': ref['sheet'], 'row': ref['row']}
    req = Requirement.objects.create(
        code=_next_code(version), version=version, statement=ref['statement'] or ref['source_quote'],
        kind=RequirementKind.GUIDANCE, page=ref['page'], source_quote=ref['source_quote'], workbook_ref=wb,
        approved_by=linked_by, approved_at=timezone.now())
    note = f'Source mapping in {data.workbook}, {ref["sheet"]} row {ref["row"]}.'
    BenchmarkRequirement.objects.create(benchmark=bench, requirement=req, relationship=ref['relationship'],
                                        note=note, linked_by=linked_by)
    SourceAuditEvent.objects.create(actor=actor, action='benchmark.linked_from_workbook', object_type='Benchmark',
                                    object_id=str(bench.pk), after={'requirement': req.code, **wb,
                                                                    'relationship': ref['relationship']},
                                    reason=note)
    return req.code


def apply_aiqif(data, *, actor, commit=False, reason='', withdraw_others=False, linked_by=None):
    """Save the framework. withdraw_others: also withdraw every other DRAFT benchmark
    (e.g. the earlier Source Pack catalogue), so AI-QIF is the only working set.
    Nothing is deleted, and a benchmark past draft is never changed. linked_by: optionally, the InGage person
    running the import, recorded on the workbook's source mappings (they are linked either way)."""
    from .linking import LinkError
    summary = CatalogueSummary(committed=commit)
    summary.withdrawn = []
    summary.source_refs = Counter()
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
            plans = [(ref, *_ref_plan(ref, existing)) for ref in b['source_refs']]
            origin = _origin(data, b, existing, actor)
            origin['workbook_source_refs'] = [{**ref, 'status': st} for ref, st, _v in plans]
            values['origin_type'], values['origin'] = Benchmark.Origin.FRAMEWORK_IMPORT, origin
            if not (existing and existing.target_guidance):
                values['target_guidance'] = rules.get('Target Rule', '')
            bench = _upsert(Benchmark, {'benchmark_code': b['code']}, values, summary, 'benchmark', actor, reason)
            if any(st == 'to link' for _r, st, _v in plans):
                for entry, (ref, st, version) in zip(origin['workbook_source_refs'], plans):
                    if st != 'to link':
                        continue
                    try:
                        entry['status'] = f'linked as {_link_ref(bench, version, ref, data, actor, linked_by)}'
                    except LinkError as exc:
                        entry['status'] = f'not linked: {exc}'
                bench.origin = origin
                bench.save(update_fields=['origin', 'updated_at'])
            for entry in origin['workbook_source_refs']:
                summary.source_refs['linked' if entry['status'].startswith('linked') else 'not linked'] += 1
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
