"""AI preparation for every Benchmark Studio stage, with people making every approval decision.

    job = start(StudioAIJob.Kind.REQUIREMENT_FIT, 'NAAC-SSR-R004', user)   # queued; a Celery task runs it
    run_job(job.pk)                                                     # (the task) -> ready | failed

Kinds (one handler each, below):
  source_metadata    a source's details, each value backed by a quote found in the source's own text
  requirement_fit    does an approved requirement support an existing indicator, or a distinct new one?
  benchmark_content  L3/L2/L1, evidence rules, applicability, target guidance, owner suggestion (ai_drafting)
  change_analysis    what a detected source change says (quotes from the detected diff), what it affects
  release_notes      version notes, change and impact summaries for a draft release

Rules every kind follows:
- Every answer is checked: codes must be ones that exist, quotes must appear in the text that was sent;
  anything that fails is dropped (listed under output['rejected']) and a wholly unusable answer fails the job.
- A failed job keeps its error and can be retried; nothing from it is applied. A provider/router failure is
  retried once on another router.
- Nothing here approves, confirms, submits or publishes. Proposals become data only through the existing
  services when a person applies them (apply_* below); benchmark_content writes AI-labelled DRAFT content
  that never replaces a person's and needs a reviewer's confirmation before a release can take it.
- The job row is the audit record of the AI step (inputs, output, citations, model, confidence, decision),
  and each state change is also a SourceAuditEvent.
"""
import hashlib
import logging
import re

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from ..models import (
    Benchmark, BenchmarkCandidate, BenchmarkRelease, Capability, Requirement, RequirementKind, SourceAuditEvent,
    SourceChangeEvent, SourceDocument, SourceVersion, StudioAIJob,
)

logger = logging.getLogger(__name__)

Kind, Status = StudioAIJob.Kind, StudioAIJob.Status
TIMEOUT = 240
SOURCE_TEXT_CHARS = 16000
#: Proposed new indicators this similar (word overlap) to an existing one are treated as duplicates.
DUPLICATE_SIMILARITY = 0.5


class StudioAIError(Exception):
    """A request that cannot be honoured (wrong target state, nothing to read ...). Shown to the user."""


class AnswerRejected(Exception):
    """The AI's answer failed a check; nothing is kept."""


class AICallFailed(Exception):
    """The provider / router failed; worth one retry on another router."""


# -- helpers -----------------------------------------------------------------------------------------

def _norm(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip().lower()


def _quote_in(quote, haystack_norm, minimum=12):
    q = _norm(quote)
    return len(q) >= minimum and q in haystack_norm


def _words(text):
    from .linking import tokens
    return tokens(text)


def _similarity(a, b):
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def _digest(text):
    return hashlib.sha256(str(text).encode('utf-8')).hexdigest()[:16]


def _audit(actor, action, job, after=None, reason=''):
    SourceAuditEvent.objects.create(actor=actor[:150], action=action, object_type=job.target_type,
                                    object_id=job.target_id, after={'job': str(job.pk), 'kind': job.kind, **(after or {})},
                                    reason=reason)


def _ask(service, *, prompt, content, schema, name):
    try:
        return service.extract_structured_data(system_prompt=prompt, user_content=content, response_schema=schema,
                                               schema_name=name, timeout=TIMEOUT)
    except Exception as exc:
        raise AICallFailed(f'AI call failed: {exc}'[:1000]) from exc


def _model(service):
    return (getattr(service, 'model', '') or 'unknown-model')[:150]


def _confidence(value):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


S = {'type': 'string'}
NULLABLE_S = {'type': ['string', 'null']}


# -- targets -----------------------------------------------------------------------------------------

def _resolve(kind, target_id):
    """(target_type, object, label) or StudioAIError."""
    if kind == Kind.SOURCE_METADATA:
        obj = SourceDocument.objects.filter(source_code=target_id).first()
        if obj is None:
            raise StudioAIError('Unknown source.')
        return 'SourceDocument', obj, obj.source_code
    if kind == Kind.REQUIREMENT_FIT:
        obj = Requirement.objects.select_related('version__document').filter(code=target_id).first()
        if obj is None:
            raise StudioAIError('Unknown requirement.')
        return 'Requirement', obj, obj.code
    if kind == Kind.BENCHMARK_CONTENT:
        obj = Benchmark.objects.select_related('pillar', 'capability').filter(benchmark_code=target_id).first()
        if obj is None:
            raise StudioAIError('Unknown benchmark.')
        return 'Benchmark', obj, obj.benchmark_code
    if kind == Kind.CHANGE_ANALYSIS:
        obj = SourceChangeEvent.objects.select_related('document', 'feed').filter(pk=target_id).first()
        if obj is None:
            raise StudioAIError('Unknown change event.')
        return 'SourceChangeEvent', obj, f'{obj.document.source_code}: {obj.get_change_kind_display()}'
    if kind == Kind.RELEASE_NOTES:
        obj = BenchmarkRelease.objects.filter(release_label=target_id).first()
        if obj is None:
            raise StudioAIError('Unknown release.')
        return 'BenchmarkRelease', obj, obj.release_label
    raise StudioAIError(f'kind must be one of {", ".join(Kind.values)}.')


def _check_target(kind, obj):
    if kind == Kind.SOURCE_METADATA and not (obj.versions.exclude(file_uri='').exists() or obj.official_url):
        raise StudioAIError('Store a file for this source or give its official URL first; there is nothing to read.')
    if kind == Kind.BENCHMARK_CONTENT and obj.status != Benchmark.Status.DRAFT:
        raise StudioAIError(f'{obj.benchmark_code} is {obj.status}; only a draft can be prepared. Reopen it first.')
    if kind == Kind.RELEASE_NOTES and obj.status != BenchmarkRelease.Status.DRAFT:
        raise StudioAIError(f'{obj.release_label} is {obj.status}; notes are prepared while it is a draft.')


# -- lifecycle ---------------------------------------------------------------------------------------

def start(kind, target_id, user=None, *, dispatch=True):
    """Queue a job (or return the one already queued/running for the same target)."""
    target_type, obj, label = _resolve(kind, str(target_id))
    _check_target(kind, obj)
    key = str(target_id)
    existing = StudioAIJob.objects.filter(kind=kind, target_id=str(key), status__in=StudioAIJob.ACTIVE).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            job = StudioAIJob.objects.create(kind=kind, target_type=target_type, target_id=str(key),
                                             target_label=label[:200], requested_by=user)
    except IntegrityError:
        return StudioAIJob.objects.get(kind=kind, target_id=str(key), status__in=StudioAIJob.ACTIVE)
    _audit(user.email if user else 'studio_ai', 'ai.requested', job)
    if dispatch:
        transaction.on_commit(lambda: _dispatch(job))
    return job


def _dispatch(job):
    from ..tasks import run_studio_ai_job
    try:
        run_studio_ai_job.delay(str(job.pk))
    except Exception as exc:  # broker down: say so instead of leaving it "queued" forever
        StudioAIJob.objects.filter(pk=job.pk, status=Status.QUEUED).update(
            status=Status.FAILED, error=f'Could not reach the task queue: {exc}'[:1000], finished_at=timezone.now())


def retry(job, user):
    if job.status != Status.FAILED:
        raise StudioAIError('Only a failed job can be retried.')
    return start(job.kind, job.target_id, user)


def dismiss(job, user, note=''):
    if job.status != Status.READY:
        raise StudioAIError('Only a draft that is ready for review can be dismissed.')
    _decide(job, user, Status.DISMISSED, note)
    return job


def _decide(job, user, status, note='', **after):
    job.status, job.decided_by, job.decided_at, job.decision_note = status, user, timezone.now(), (note or '').strip()
    job.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note'])
    _audit(user.email, f'ai.{status}', job, after=after, reason=job.decision_note)


def run_job(job_id):
    """Run one queued job (the Celery task). Never raises."""
    from apps.extraction.models import AIUsage
    from apps.extraction.services.ai_service import get_ai_service
    from apps.extraction.services.router_pool import get_router_pool, use_lease
    from apps.extraction.usage import usage_scope

    now = timezone.now()
    if not StudioAIJob.objects.filter(pk=job_id, status=Status.QUEUED).update(
            status=Status.RUNNING, started_at=now, error='', attempts=F('attempts') + 1):
        return None
    job = StudioAIJob.objects.get(pk=job_id)
    try:
        _type, obj, _label = _resolve(job.kind, job.target_id)
        _check_target(job.kind, obj)
        pool, avoid, result = get_router_pool(), '', None
        for attempt in range(2):
            lease = pool.acquire(avoid=avoid) if pool is not None else None
            try:
                with use_lease(lease), usage_scope(stage=AIUsage.Stage.OTHER):
                    service = get_ai_service()
                    result = HANDLERS[job.kind](job, obj, service)
                break
            except AICallFailed:
                if lease is None or attempt:
                    raise
                avoid = lease.router.label
                logger.warning('studio_ai.retry job=%s avoiding=%s', job.pk, avoid)
            finally:
                if lease is not None:
                    pool.release(lease)
        job.output, job.citations, job.confidence, job.model = (
            result['output'], result.get('citations', []), result.get('confidence'), result['model'])
        job.inputs = {**job.inputs, **result.get('inputs', {})}
        job.status = Status.READY
    except AnswerRejected as exc:
        job.status, job.error = Status.FAILED, f'The AI answer failed a check and was not kept: {exc}'[:2000]
    except (AICallFailed, StudioAIError) as exc:
        job.status, job.error = Status.FAILED, str(exc)[:2000]
    except Exception as exc:  # anything unexpected: record it, never leave the job running
        logger.exception('studio_ai.failed job=%s', job.pk)
        job.status, job.error = Status.FAILED, f'{type(exc).__name__}: {exc}'[:2000]
    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'error', 'output', 'citations', 'confidence', 'model', 'inputs', 'finished_at'])
    _audit('studio_ai', f'ai.{job.status}', job,
           after={'model': job.model, 'confidence': job.confidence, 'citations': len(job.citations or []),
                  'error': job.error or None})
    return job


def latest(kind, target_id):
    return StudioAIJob.objects.filter(kind=kind, target_id=str(target_id)).first()


# == source_metadata ===================================================================================

SOURCE_FIELDS = ('title', 'authority_name', 'document_type', 'source_role', 'applies_to', 'programme_scope',
                 'version_label', 'issued_on', 'effective_from')
SOURCE_PROMPT = (
    'You read the opening pages of an official Indian higher-education source (a regulation, guideline, '
    'accreditation manual, framework or standard) and report its details. For EVERY value give `quote`: words '
    'copied exactly from the text that show it. If the text does not show a value, return null for both. Never '
    'guess from general knowledge. Dates as YYYY-MM-DD. source_role: mandatory (binding regulation), '
    'authoritative_quality_framework (accreditation/quality framework), good_practice_standard, intelligence_signal '
    '(reports, market studies).')


def _source_schema():
    field = {'type': 'object', 'properties': {'value': NULLABLE_S, 'quote': NULLABLE_S},
             'required': ['value', 'quote'], 'additionalProperties': False}
    return {'type': 'object', 'properties': {**{f: field for f in SOURCE_FIELDS}, 'confidence': {'type': 'number'}},
            'required': [*SOURCE_FIELDS, 'confidence'], 'additionalProperties': False}


def _source_text(doc):
    """(text, where) -- the stored file's first pages, else the official page."""
    from .requirement_drafting import DraftingError, read_pages
    version = doc.versions.exclude(file_uri='').order_by('-created_at').first()
    if version is not None:
        try:
            pages = read_pages(version)
        except DraftingError as exc:
            raise StudioAIError(str(exc))
        text = '\n\n'.join(f'--- Page {p["page_number"]} ---\n{p["text"]}' for p in pages)[:SOURCE_TEXT_CHARS]
        return text, {'version': version.version_label, 'pages_read': len(pages)}
    from .watcher import FetchError, fetch
    try:
        f = fetch(doc.official_url)
    except FetchError as exc:
        raise StudioAIError(f'Could not read the official page: {exc}')
    raw = f.content.decode('utf-8', 'replace')
    if 'html' in (f.content_type or '').lower() or raw.lstrip()[:15].lower().startswith(('<!doctype', '<html')):
        from bs4 import BeautifulSoup
        raw = BeautifulSoup(raw, 'html.parser').get_text('\n')
    text = '\n'.join(line.strip() for line in raw.splitlines() if line.strip())[:SOURCE_TEXT_CHARS]
    return text, {'url': f.url}


def _handle_source_metadata(job, doc, service):
    from datetime import date
    text, where = _source_text(doc)
    if len(text.strip()) < 200:
        raise StudioAIError('The source has too little readable text (a scan without OCR, or an empty page).')
    answer = _ask(service, prompt=SOURCE_PROMPT, content=f'Current record: {doc.source_code} "{doc.title}"\n\n{text}',
                  schema=_source_schema(), name='source_details') or {}
    hay = _norm(text)
    fields, rejected, citations = {}, [], []
    for name in SOURCE_FIELDS:
        item = answer.get(name) or {}
        value, quote = (item.get('value') or '').strip(), (item.get('quote') or '').strip()
        if not value:
            continue
        if not _quote_in(quote, hay, minimum=4):
            rejected.append({'field': name, 'value': value, 'why': 'quote not found in the source text'})
            continue
        if name == 'source_role' and value not in SourceDocument.Role.values:
            rejected.append({'field': name, 'value': value, 'why': 'not a known source role'})
            continue
        if name in ('issued_on', 'effective_from'):
            try:
                date.fromisoformat(value)
            except ValueError:
                rejected.append({'field': name, 'value': value, 'why': 'not a date'})
                continue
        fields[name] = {'value': value[:500], 'quote': quote[:500], 'current': _current_source_value(doc, name)}
        citations.append({'field': name, 'quote': quote[:500]})
    if not fields:
        raise AnswerRejected('no value could be verified against the source text')
    return {'output': {'fields': fields, 'rejected': rejected, 'read': where}, 'citations': citations,
            'confidence': _confidence(answer.get('confidence')), 'model': _model(service),
            'inputs': {'read': where, 'text_chars': len(text), 'text_hash': _digest(text)}}


def _draft_version(doc):
    return doc.versions.filter(status=SourceVersion.Status.DRAFT).order_by('-created_at').first()


def _current_source_value(doc, name):
    if name == 'authority_name':
        return doc.framework.authority.name if doc.framework_id else ''
    if name in ('version_label', 'issued_on', 'effective_from'):
        v = _draft_version(doc)
        return str(getattr(v, name) or '') if v else None
    return getattr(doc, name, '') or ''


def apply_source_metadata(job, user, field_names):
    """Copy the chosen verified values onto the source (and its DRAFT version). Approved versions are frozen and
    the authority is shown for information only, so those are never written."""
    from datetime import date
    if job.kind != Kind.SOURCE_METADATA or job.status != Status.READY:
        raise StudioAIError('Only a ready source-details draft can be applied.')
    doc = SourceDocument.objects.get(source_code=job.target_id)
    fields = job.output.get('fields', {})
    chosen = [f for f in field_names if f in fields and f != 'authority_name']
    if not chosen:
        raise StudioAIError('Choose at least one suggested value to apply.')
    version = _draft_version(doc)
    before, after = {}, {}
    with transaction.atomic():
        for name in chosen:
            value = fields[name]['value']
            if name in ('version_label', 'issued_on', 'effective_from'):
                if version is None:
                    continue  # no draft version: approved versions never change
                before[name] = str(getattr(version, name) or '')
                setattr(version, name, date.fromisoformat(value) if name != 'version_label' else value[:120])
                after[name] = value
            else:
                limit = SourceDocument._meta.get_field(name).max_length
                before[name] = getattr(doc, name)
                setattr(doc, name, value[:limit] if limit else value)
                after[name] = value
        doc.save()
        if version is not None and any(n in after for n in ('version_label', 'issued_on', 'effective_from')):
            version.save()
        SourceAuditEvent.objects.create(actor=user.email, action='source.ai_details_applied',
                                        object_type='SourceDocument', object_id=str(doc.pk), before=before,
                                        after={**after, 'job': str(job.pk), 'model': job.model})
        _decide(job, user, Status.APPLIED, fields=sorted(after))
    return doc


# == requirement_fit ===================================================================================

FIT_PROMPT = (
    'You map one approved requirement from an Indian higher-education source onto the InGage AI-QIF key indicators '
    '(benchmarks). First decide whether it supports EXISTING indicators: list each one it supports with '
    'relationship primary (the indicator measures exactly this) or supporting, and why. Propose a NEW indicator '
    'ONLY when no existing indicator covers it AND the source supports a distinct capability that a college can '
    'demonstrate with evidence; otherwise new_indicator is null. A new indicator goes under one of the listed '
    'criteria and capabilities. `source_quote` must be copied exactly from the requirement text given. Choose '
    'decision "none" when the requirement is not about AI readiness at all.')


def _fit_context(req):
    from .candidates import _aiqif_framework, capabilities_for, criteria
    framework = _aiqif_framework()
    benches = list(Benchmark.objects.select_related('capability', 'pillar').exclude(status=Benchmark.Status.WITHDRAWN)
                   .order_by('benchmark_code'))
    crit = [(p, list(capabilities_for(p, framework))) for p in criteria(framework)]
    lines = [f'Requirement {req.code} ({req.get_kind_display()}) from {req.version.document.source_code} '
             f'"{req.version.document.title}", {req.version.version_label}, page {req.page or "?"}:',
             f'Statement: {req.statement}', f'Exact source text: {req.source_quote}', '', 'Existing indicators:']
    lines += [f'- {b.benchmark_code} [{b.pillar.code}] {b.title} -- capability: {b.capability.definition[:200]}'
              for b in benches]
    lines += ['', 'Criteria and their capabilities (for a new indicator):']
    for p, caps in crit:
        lines.append(f'- {p.code} {p.name}: ' + '; '.join(f'{c.code} {c.name}' for c in caps))
    return '\n'.join(lines), benches, crit


def _fit_schema(bench_codes, pillar_codes, cap_codes):
    match = {'type': 'object', 'properties': {
        'benchmark_code': {'type': 'string', 'enum': bench_codes or ['-']},
        'relationship': {'type': 'string', 'enum': ['primary', 'supporting']},
        'rationale': S, 'confidence': {'type': 'number'}},
        'required': ['benchmark_code', 'relationship', 'rationale', 'confidence'], 'additionalProperties': False}
    new = {'type': ['object', 'null'], 'properties': {
        'pillar_code': {'type': 'string', 'enum': pillar_codes or ['-']},
        'capability_code': {'type': 'string', 'enum': cap_codes or ['-']},
        'title': S, 'benchmark_kind': {'type': 'string', 'enum': list(RequirementKind.values)},
        'capability_statement': S, 'how_measured': S, 'rationale': S, 'source_quote': S},
        'required': ['pillar_code', 'capability_code', 'title', 'benchmark_kind', 'capability_statement',
                     'how_measured', 'rationale', 'source_quote'], 'additionalProperties': False}
    return {'type': 'object', 'properties': {
        'decision': {'type': 'string', 'enum': ['existing', 'new', 'none']},
        'matches': {'type': 'array', 'items': match}, 'new_indicator': new, 'rationale': S,
        'confidence': {'type': 'number'}},
        'required': ['decision', 'matches', 'new_indicator', 'rationale', 'confidence'], 'additionalProperties': False}


def duplicate_check(title, statement=''):
    """Existing (non-withdrawn) indicators most like a proposed one: [{code, title, similarity}]."""
    rows = []
    for b in Benchmark.objects.exclude(status=Benchmark.Status.WITHDRAWN).select_related('capability'):
        sim = max(_similarity(title, b.title), _similarity(f'{title} {statement}', f'{b.title} {b.capability.definition}'))
        if sim > 0.15:
            rows.append({'code': b.benchmark_code, 'title': b.title, 'similarity': round(sim, 2)})
    return sorted(rows, key=lambda r: -r['similarity'])[:5]


def _handle_requirement_fit(job, req, service):
    content, benches, crit = _fit_context(req)
    codes = [b.benchmark_code for b in benches]
    caps_by_pillar = {p.code: {c.code for c in caps} for p, caps in crit}
    answer = _ask(service, prompt=FIT_PROMPT, content=content,
                  schema=_fit_schema(codes, list(caps_by_pillar), sorted({c for s in caps_by_pillar.values() for c in s})),
                  name='requirement_indicator_fit') or {}
    linked = set(req.benchmark_links.values_list('benchmark__benchmark_code', flat=True))
    rejected, matches = [], []
    for m in answer.get('matches') or []:
        if m.get('benchmark_code') not in codes:
            rejected.append({'item': m, 'why': 'unknown indicator'})
            continue
        matches.append({**m, 'confidence': _confidence(m.get('confidence')), 'already_linked': m['benchmark_code'] in linked})
    new = answer.get('new_indicator')
    proposal = None
    hay = _norm(f'{req.statement} {req.source_quote}')
    if answer.get('decision') == 'new' and new:
        problems = []
        if new.get('pillar_code') not in caps_by_pillar:
            problems.append('unknown criterion')
        elif new.get('capability_code') not in caps_by_pillar[new['pillar_code']]:
            problems.append(f'capability is not one of {new["pillar_code"]}\'s')
        if not _quote_in(new.get('source_quote'), hay):
            problems.append('quote not found in the requirement')
        if not (new.get('title') or '').strip():
            problems.append('no title')
        dups = duplicate_check(new.get('title', ''), new.get('capability_statement', ''))
        if problems:
            rejected.append({'item': new, 'why': '; '.join(problems)})
        else:
            blocked = bool(dups and dups[0]['similarity'] >= DUPLICATE_SIMILARITY)
            proposal = {**new, 'title': ' '.join(new['title'].split())[:300], 'duplicates': dups,
                        'blocked': blocked,
                        'blocked_reason': (f'Too close to {dups[0]["code"]} "{dups[0]["title"]}" '
                                           f'({dups[0]["similarity"]:.0%} word overlap): link to it instead.')
                        if blocked else ''}
    if not matches and proposal is None and answer.get('decision') != 'none':
        raise AnswerRejected('; '.join(r['why'] for r in rejected) or 'no usable recommendation')
    citations = [{'requirement': req.code, 'page': req.page, 'quote': req.source_quote[:500]}]
    if proposal:
        citations.append({'requirement': req.code, 'quote': proposal['source_quote'][:500], 'for': 'new indicator'})
    return {'output': {'decision': answer.get('decision'), 'matches': matches, 'new_indicator': proposal,
                       'rationale': answer.get('rationale', ''), 'rejected': rejected},
            'citations': citations, 'confidence': _confidence(answer.get('confidence')), 'model': _model(service),
            'inputs': {'requirement': req.code, 'indicators_offered': len(codes), 'text_hash': _digest(content)}}


def propose_indicator(job, user, note=''):
    """Turn a ready new-indicator proposal into a candidate in expert review, carrying every proposed detail
    (ai_proposal), so the draft can be created from it once the experts approve."""
    from . import candidates as cand
    if job.kind != Kind.REQUIREMENT_FIT or job.status != Status.READY:
        raise StudioAIError('Only a ready indicator-fit result can be proposed.')
    prop = job.output.get('new_indicator')
    if not prop:
        raise StudioAIError('The AI did not propose a new indicator for this requirement.')
    if prop.get('blocked'):
        raise StudioAIError(prop['blocked_reason'])
    req = Requirement.objects.select_related('version__document').get(code=job.target_id)
    doc = req.version.document
    capability = Capability.objects.filter(code=prop['capability_code']).first()
    rationale = (f'{prop["rationale"]}\n\nCapability: {prop["capability_statement"]}\nHow it is measured: '
                 f'{prop["how_measured"]}\n\nSource: {req.code} ({doc.source_code}, {req.version.version_label}, '
                 f'page {req.page or "?"}): "{prop["source_quote"]}"')
    with transaction.atomic():
        c = BenchmarkCandidate.objects.create(
            source_document=doc, capability=capability, candidate_type=BenchmarkCandidate.Type.NEW_BENCHMARK,
            title=prop['title'], proposed_kind=prop['benchmark_kind'], source_rationale=rationale,
            duplication_score=round(100 * (prop['duplicates'][0]['similarity'] if prop['duplicates'] else 0), 2),
            required_roles=cand.required_roles_for(doc, None, title=prop['title'], proposed_kind=prop['benchmark_kind']),
            ai_proposal={**prop, 'requirement_code': req.code, 'job': str(job.pk), 'model': job.model,
                         'confidence': job.confidence},
            status=BenchmarkCandidate.Status.RESEARCH, created_by=user.email)
        cand._audit(user.email, 'candidate.created', c, after={'type': c.candidate_type, 'from_ai_job': str(job.pk)},
                    reason=note)
        cand.submit(c, user)
        _decide(job, user, Status.APPLIED, note, candidate=str(c.pk))
    return c


# == benchmark_content =================================================================================

def _handle_benchmark_content(job, bench, service):
    from .ai_drafting import ai_user, draft_benchmark
    result = draft_benchmark(bench, service, user=ai_user())
    if not result.ok:
        if result.detail.startswith('AI call failed'):
            raise AICallFailed(result.detail)
        raise AnswerRejected(result.detail)
    return {'output': {'levels': result.levels, 'evidence_rules': result.evidence_rules,
                       'applicability_rules': result.applicability_rules, 'kept_human': result.kept_human,
                       'owner_suggestion': result.owner_suggestion, 'rationale': result.rationale,
                       'target_guidance_written': result.target_guidance_written},
            'citations': result.references, 'confidence': result.confidence, 'model': _model(service),
            'inputs': {'benchmark': bench.benchmark_code,
                       'requirements': list(bench.requirement_links.values_list('requirement__code', flat=True))}}


# == change_analysis ===================================================================================

CHANGE_PROMPT = (
    'A watcher detected a change on an official source page used by InGage benchmarks. Using ONLY the detected '
    'change given, explain what changed and why it matters for Indian colleges\' AI readiness. Each item in '
    '`changes` quotes the changed text exactly. Pick affected requirements and indicators only from the lists '
    'given. impact_level: high = a benchmark\'s expectations or evidence change; medium = wording or reference '
    'changes; low = cosmetic. recommendation: update_benchmark, new_benchmark (a distinct new capability), '
    'source_update (re-review the source), or no_action.')


def _change_text(event):
    d = event.details or {}
    parts = [f'Change: {event.get_change_kind_display()} -- {event.summary}']
    for title, url in d.get('added', []):
        parts.append(f'ADDED LINK: {title} {url}')
    for title, url in d.get('removed', []):
        parts.append(f'REMOVED LINK: {title} {url}')
    parts += [f'ADDED LINE: {line}' for line in d.get('added_lines', [])]
    parts += [f'REMOVED LINE: {line}' for line in d.get('removed_lines', [])]
    if d.get('http_status'):
        parts.append(f'HTTP status: {d["http_status"]}')
    return '\n'.join(parts)[:SOURCE_TEXT_CHARS]


def _handle_change_analysis(job, event, service):
    doc = event.document
    reqs = list(Requirement.objects.filter(version__document=doc).values_list('code', 'statement'))
    benches = list(Benchmark.objects.filter(requirement_links__requirement__version__document=doc)
                   .exclude(status=Benchmark.Status.WITHDRAWN).distinct().values_list('benchmark_code', 'title'))
    diff_text = _change_text(event)
    content = '\n'.join([f'Source {doc.source_code}: {doc.title}', diff_text, '', 'Requirements from this source:',
                         *[f'- {c}: {s[:200]}' for c, s in reqs], '', 'Indicators linked to this source:',
                         *[f'- {c}: {t}' for c, t in benches]])
    schema = {'type': 'object', 'properties': {
        'summary': S, 'changes': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'description': S, 'quote': S}, 'required': ['description', 'quote'], 'additionalProperties': False}},
        'affected_requirements': {'type': 'array', 'items': {'type': 'string', 'enum': [c for c, _ in reqs] or ['-']}},
        'affected_benchmarks': {'type': 'array', 'items': {'type': 'string', 'enum': [c for c, _ in benches] or ['-']}},
        'impact_level': {'type': 'string', 'enum': ['low', 'medium', 'high']}, 'impact_rationale': S,
        'recommendation': {'type': 'string', 'enum': ['update_benchmark', 'new_benchmark', 'source_update', 'no_action']},
        'proposed_title': S, 'confidence': {'type': 'number'}},
        'required': ['summary', 'changes', 'affected_requirements', 'affected_benchmarks', 'impact_level',
                     'impact_rationale', 'recommendation', 'proposed_title', 'confidence'], 'additionalProperties': False}
    answer = _ask(service, prompt=CHANGE_PROMPT, content=content, schema=schema, name='source_change_analysis') or {}
    hay = _norm(diff_text)
    changes, rejected = [], []
    for c in answer.get('changes') or []:
        (changes if _quote_in(c.get('quote'), hay, minimum=6) else rejected).append(
            c if _quote_in(c.get('quote'), hay, minimum=6) else {'item': c, 'why': 'quote not in the detected change'})
    if not changes and event.change_kind not in (SourceChangeEvent.Kind.WITHDRAWAL, SourceChangeEvent.Kind.ACCESS_CHANGE):
        raise AnswerRejected('none of the described changes quotes the detected text')
    req_codes, bench_codes = {c for c, _ in reqs}, {c for c, _ in benches}
    out = {'summary': answer.get('summary', ''), 'changes': changes,
           'affected_requirements': [c for c in answer.get('affected_requirements') or [] if c in req_codes],
           'affected_benchmarks': [c for c in answer.get('affected_benchmarks') or [] if c in bench_codes],
           'impact_level': answer.get('impact_level'), 'impact_rationale': answer.get('impact_rationale', ''),
           'recommendation': answer.get('recommendation'), 'proposed_title': answer.get('proposed_title', ''),
           'rejected': rejected, 'deterministic_impact': event.impact or {}}
    return {'output': out, 'citations': [{'quote': c['quote'][:500]} for c in changes],
            'confidence': _confidence(answer.get('confidence')), 'model': _model(service),
            'inputs': {'event': str(event.pk), 'diff_hash': _digest(diff_text), 'requirements': len(reqs),
                       'indicators': len(benches)}}


def candidate_from_change(job, user, note=''):
    """A ready change analysis -> one candidate in expert review (update an affected indicator, or review the
    source / a new indicator), with the AI summary and the quoted changes as its rationale."""
    from . import candidates as cand
    if job.kind != Kind.CHANGE_ANALYSIS or job.status != Status.READY:
        raise StudioAIError('Only a ready change analysis can prepare a candidate.')
    out = job.output
    rec = out.get('recommendation')
    if rec == 'no_action':
        raise StudioAIError('The analysis recommends no action; dismiss it, or create a candidate by hand.')
    event = SourceChangeEvent.objects.select_related('document').get(pk=job.target_id)
    bench = None
    if rec == 'update_benchmark' and out.get('affected_benchmarks'):
        bench = Benchmark.objects.filter(benchmark_code=out['affected_benchmarks'][0]).first()
    ctype = (BenchmarkCandidate.Type.UPDATE_BENCHMARK if bench else
             BenchmarkCandidate.Type.NEW_BENCHMARK if rec == 'new_benchmark' else BenchmarkCandidate.Type.SOURCE_UPDATE)
    open_q = BenchmarkCandidate.objects.filter(status__in=cand.OPEN_STATUSES, candidate_type=ctype)
    open_q = open_q.filter(benchmark=bench) if bench else open_q.filter(source_document=event.document, change_event=event)
    if open_q.exists():
        raise StudioAIError('A candidate for this is already open; review that one.')
    title = (out.get('proposed_title') or (f'Update {bench.benchmark_code} after a change to {event.document.source_code}'
                                           if bench else f'Review the change to {event.document.source_code}'))[:300]
    rationale = '\n'.join([f'AI analysis ({job.model}): {out.get("summary", "")}',
                           f'Impact: {out.get("impact_level")} -- {out.get("impact_rationale", "")}', 'Changed text:',
                           *[f'- {c["description"]}: "{c["quote"]}"' for c in out.get('changes', [])],
                           'Affected requirements: ' + (', '.join(out.get('affected_requirements', [])) or 'none named'),
                           'Affected indicators: ' + (', '.join(out.get('affected_benchmarks', [])) or 'none named')])
    with transaction.atomic():
        c = BenchmarkCandidate.objects.create(
            change_event=event, source_document=event.document, benchmark=bench,
            capability=bench.capability if bench else None, candidate_type=ctype, title=title, source_rationale=rationale,
            proposed_kind=bench.benchmark_kind if bench else 'proposed', emergence_score=event.materiality_score,
            required_roles=cand.required_roles_for(event.document, bench, title=title,
                                                    proposed_kind='' if bench else 'proposed'),
            ai_proposal={'from_change_analysis': str(job.pk), 'model': job.model, 'confidence': job.confidence,
                         'impact_level': out.get('impact_level')},
            status=BenchmarkCandidate.Status.RESEARCH, created_by=user.email)
        cand._audit(user.email, 'candidate.created', c, after={'type': ctype, 'from_ai_job': str(job.pk)}, reason=note)
        cand.submit(c, user)
        _decide(job, user, Status.APPLIED, note, candidate=str(c.pk))
    return c


def queue_change_analysis(events):
    """Watcher hook: analyse each material change (never fails the watcher)."""
    from .candidates import CANDIDATE_EVENT_KINDS, MIN_MATERIALITY
    for ev in events:
        if ev.change_kind in CANDIDATE_EVENT_KINDS and ev.materiality_score >= MIN_MATERIALITY:
            try:
                start(Kind.CHANGE_ANALYSIS, ev.pk)
            except Exception:
                logger.exception('studio_ai.change_queue_failed event=%s', ev.pk)


# == release_notes =====================================================================================

NOTES_PROMPT = (
    'Write the release notes for a draft InGage benchmark release, for the people who approve it and for colleges. '
    'Use only the items given. version_notes: 2-4 sentences; change_summary: what is added, updated, retired; '
    'impact_summary: what colleges must now evidence differently; one item_impacts entry per added/updated/retired '
    'indicator; readiness_notes: any item that looks not ready according to the checks given.')


def _handle_release_notes(job, release, service):
    from . import releases
    rows = releases.diff(release)
    problems, warnings = releases.check_release(release)
    changed = [r for r in rows if r['change_type'] != 'unchanged']
    if not changed:
        raise StudioAIError('The release has no added, updated or retired indicators to describe.')
    content = '\n'.join([f'Release {release.release_label} (based on '
                         f'{release.based_on.release_label if release.based_on else "nothing: first release"})', 'Items:',
                         *[f'- {r["benchmark_code"]} {r["title"]}: {r["change_type"]}'
                           + (f' (changed: {", ".join(r["changed"])})' if r['changed'] else '') for r in changed],
                         f'Unchanged items carried forward: {len(rows) - len(changed)}', 'Checks:',
                         *[f'- {p}' for p in problems], *[f'- (warning) {w}' for w in warnings]])
    codes = [r['benchmark_code'] for r in changed]
    schema = {'type': 'object', 'properties': {
        'version_notes': S, 'change_summary': S, 'impact_summary': S, 'readiness_notes': S,
        'item_impacts': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'benchmark_code': {'type': 'string', 'enum': codes}, 'impact_summary': S},
            'required': ['benchmark_code', 'impact_summary'], 'additionalProperties': False}},
        'confidence': {'type': 'number'}},
        'required': ['version_notes', 'change_summary', 'impact_summary', 'readiness_notes', 'item_impacts', 'confidence'],
        'additionalProperties': False}
    answer = _ask(service, prompt=NOTES_PROMPT, content=content, schema=schema, name='release_notes') or {}
    if not (answer.get('version_notes') or '').strip():
        raise AnswerRejected('no version notes')
    impacts = {i['benchmark_code']: i['impact_summary'].strip() for i in answer.get('item_impacts') or []
               if i.get('benchmark_code') in codes and (i.get('impact_summary') or '').strip()}
    return {'output': {k: answer.get(k, '') for k in ('version_notes', 'change_summary', 'impact_summary',
                                                      'readiness_notes')} | {'item_impacts': impacts},
            'citations': [{'benchmark_code': c} for c in impacts], 'confidence': _confidence(answer.get('confidence')),
            'model': _model(service), 'inputs': {'release': release.release_label, 'items': codes}}


def apply_release_notes(job, user, *, overwrite_items=False):
    """Write the reviewed notes onto the DRAFT release (and item impact summaries that are still empty, unless
    overwrite_items). Approving and publishing stay separate human steps."""
    from .releases import ReleaseError
    if job.kind != Kind.RELEASE_NOTES or job.status != Status.READY:
        raise StudioAIError('Only ready release notes can be applied.')
    release = BenchmarkRelease.objects.get(release_label=job.target_id)
    if release.status != BenchmarkRelease.Status.DRAFT:
        raise ReleaseError(f'{release.release_label} is {release.status}; notes change only while it is a draft.')
    out = job.output
    notes = '\n\n'.join(filter(None, [out.get('version_notes'), f'Changes: {out.get("change_summary")}'
                                      if out.get('change_summary') else '', f'Impact: {out.get("impact_summary")}'
                                      if out.get('impact_summary') else '']))
    with transaction.atomic():
        before = release.release_notes
        release.release_notes = notes
        release.save(update_fields=['release_notes'])
        written = []
        for item in release.items.select_related('benchmark'):
            text = out.get('item_impacts', {}).get(item.benchmark.benchmark_code)
            if text and (overwrite_items or not item.impact_summary.strip()):
                item.impact_summary = text
                item.save(update_fields=['impact_summary'])
                written.append(item.benchmark.benchmark_code)
        SourceAuditEvent.objects.create(actor=user.email, action='release.ai_notes_applied', object_type='BenchmarkRelease',
                                        object_id=str(release.pk), before={'release_notes': before},
                                        after={'release_notes': notes, 'item_impacts': written, 'job': str(job.pk),
                                               'model': job.model})
        _decide(job, user, Status.APPLIED, items=written)
    return release


HANDLERS = {
    Kind.SOURCE_METADATA: _handle_source_metadata,
    Kind.REQUIREMENT_FIT: _handle_requirement_fit,
    Kind.BENCHMARK_CONTENT: _handle_benchmark_content,
    Kind.CHANGE_ANALYSIS: _handle_change_analysis,
    Kind.RELEASE_NOTES: _handle_release_notes,
}
