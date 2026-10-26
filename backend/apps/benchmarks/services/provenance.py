"""Where each benchmark indicator came from, and which source documents support it (Studio > Benchmark Library,
"Origin & Sources").

Two separate things, never mixed:

- **Origin** -- how the indicator itself entered the library:
  * framework_import: the initial AI-QIF catalogue, imported from the manager-provided workbook
    (services/aiqif_import.py records workbook, sheet, row, version and import date on the row; for older
    imports that did not, the import's own audit event is read instead -- nothing is guessed);
  * candidate: created from an approved benchmark candidate (services/candidates.py);
  * manual: an "other origin" a reviewer entered explicitly (only when none is recorded).
- **Source mappings** -- the requirements linked to the indicator (BenchmarkRequirement: Primary / Supporting /
  Crosswalk), each with its Source Library document, version, page and exact quote. They come from the manager
  workbook's source-reference sheet (requirement.workbook_ref) or are earlier reviewed links. Nothing is inferred
  from titles, names, AI output or similarity; with none, the indicator shows "Source mapping not provided."

Benchmark Studio is read-only (settings.BENCHMARK_CATALOGUE_READ_ONLY): the edit functions below are kept for the
controlled import and maintenance; the portal API refuses them.
"""
import os
import re

from django.db import transaction
from django.utils import timezone

from ..models import (Benchmark, BenchmarkCandidate, BenchmarkRequirement, Requirement, RequirementKind,
                      SourceAuditEvent, SourceSection, SourceVersion)

Origin = Benchmark.Origin
Relationship = BenchmarkRequirement.Relationship


class ProvenanceError(Exception):
    pass


_IMPORT_REASON = re.compile(r'import from (?P<path>.+\.xlsx)\s*$', re.IGNORECASE)


def _import_event(benchmark):
    """The audit event that created the benchmark from a workbook import, if there is one."""
    return (SourceAuditEvent.objects.filter(object_type='Benchmark', object_id=str(benchmark.pk),
                                            action='catalogue.create').order_by('created_at').first())


def origin_of(benchmark):
    """The indicator's origin as plain data. `recorded` says where it was read from: 'row' (stored on the
    benchmark), 'audit' (the import's audit event, for rows imported before origins were stored),
    'candidate' (the candidate record) -- or '' when no origin is recorded anywhere."""
    stored = dict(benchmark.origin or {})
    if benchmark.origin_type:
        return {'type': benchmark.origin_type, 'label': Origin(benchmark.origin_type).label, 'recorded': 'row',
                **stored}
    cand = (BenchmarkCandidate.objects.filter(benchmark=benchmark, candidate_type=BenchmarkCandidate.Type.NEW_BENCHMARK)
            .select_related('source_document').order_by('created_at').first())
    if cand is not None:
        return {'type': Origin.CANDIDATE, 'label': Origin.CANDIDATE.label, 'recorded': 'candidate',
                'candidate_id': str(cand.pk), 'candidate_title': cand.title,
                'source_code': cand.source_document.source_code if cand.source_document_id else None}
    event = _import_event(benchmark)
    m = _IMPORT_REASON.search(event.reason or '') if event else None
    if m:
        from .aiqif_import import FRAMEWORK_CODE, MASTER
        aiqif = bool(benchmark.framework_id and benchmark.framework.code == FRAMEWORK_CODE)
        return {'type': Origin.FRAMEWORK_IMPORT, 'label': Origin.FRAMEWORK_IMPORT.label, 'recorded': 'audit',
                'workbook': os.path.basename(m.group('path').replace('\\', '/')),
                'framework': benchmark.framework.code if benchmark.framework_id else None,
                'framework_version': benchmark.version_label,
                # The AI-QIF importer reads indicators from this one sheet only; the row was not recorded then.
                'sheet': MASTER if aiqif else None, 'row': None, 'indicator_code': benchmark.benchmark_code,
                'imported_at': event.created_at.isoformat(), 'imported_by': event.actor, 'workbook_source_refs': []}
    return {'type': '', 'label': 'Origin not recorded', 'recorded': ''}


# -- supporting source references -------------------------------------------------------

def _norm(text):
    return ' '.join((text or '').replace('“', '"').replace('”', '"').replace('’', "'").split()).casefold()


def quote_check(version, quote, page=None):
    """True when the quote is in the version's extracted text (on that page when a page is given), False when it
    is not, None when there is no extracted text to check against."""
    sections = SourceSection.objects.filter(version=version)
    if not sections.exists():
        return None
    q = _norm(quote)
    if page is not None:
        on_page = sections.filter(page_start__lte=page, page_end__gte=page)
        return any(q in _norm(s.text) for s in on_page)
    return any(q in _norm(s.text) for s in sections)


def _reference(link, check_quotes=True):
    r = link.requirement
    v = r.version
    cand = r.created_from
    return {
        'requirement_code': r.code, 'statement': r.statement, 'kind': r.kind,
        'source_code': v.document.source_code, 'source_title': v.document.title,
        'source_version': v.version_label, 'source_version_status': v.status, 'source_version_id': str(v.pk),
        'page': r.page, 'source_quote': r.source_quote,
        'quote_in_source_text': quote_check(v, r.source_quote, r.page) if check_quotes else None,
        'relationship': link.relationship, 'relationship_label': link.get_relationship_display(), 'note': link.note,
        # Human review: who accepted the requirement, and who linked it to this indicator.
        'requirement_origin': requirement_origin(r),
        'workbook_ref': r.workbook_ref or None,
        'ai_model': cand.model if cand else '',
        'accepted_by': r.approved_by.email if r.approved_by_id else None,
        'accepted_at': r.approved_at.isoformat() if r.approved_at else None,
        'linked_by': link.linked_by.email if link.linked_by_id else None,
        'linked_at': link.linked_at.isoformat() if link.linked_at else None,
    }


def requirement_origin(requirement):
    """'manager_workbook' (a mapping in the authoritative workbook), 'ai_draft_accepted' (an AI draft a person
    accepted, earlier workflow) or 'entered_by_reviewer'."""
    if requirement.workbook_ref:
        return 'manager_workbook'
    return 'ai_draft_accepted' if requirement.created_from_id else 'entered_by_reviewer'


def _links(benchmark):
    return (BenchmarkRequirement.objects.filter(benchmark=benchmark)
            .select_related('requirement__version__document', 'requirement__approved_by', 'requirement__created_from',
                            'linked_by')
            .order_by('relationship', 'requirement__code'))


def source_references(benchmark, check_quotes=True):
    return [_reference(link, check_quotes) for link in _links(benchmark)]


def provenance(benchmark):
    refs = source_references(benchmark)
    return {'benchmark_code': benchmark.benchmark_code, 'version_label': benchmark.version_label,
            'status': benchmark.status, 'origin': origin_of(benchmark), 'source_references': refs,
            'source_document_linked': bool(refs),
            'naac_crosswalk_count': len(benchmark.naac_crosswalk or []), 'frozen_in': None}


def frozen(benchmark):
    """What a release keeps (services/releases.publish): the origin and the source references as they are now."""
    return {'origin': origin_of(benchmark), 'source_references': source_references(benchmark)}


def release_provenance(item):
    """A release item's provenance as it was published. Releases published before provenance was frozen still
    have their requirement links in the snapshot; their origin was not frozen and is reported as such."""
    snap = item.snapshot or {}
    kept = snap.get('provenance')
    if kept:
        origin, refs = kept.get('origin') or {}, kept.get('source_references') or []
    else:
        origin = {'type': '', 'label': 'Origin not frozen in this release (published before origins were kept)',
                  'recorded': ''}
        refs = [{'requirement_code': r.get('code'), 'statement': r.get('statement'), 'source_code': r.get('source_code'),
                 'source_version': r.get('source_version'), 'page': r.get('page'), 'source_quote': r.get('source_quote'),
                 'relationship': r.get('relationship'),
                 'relationship_label': Relationship(r['relationship']).label if r.get('relationship') in Relationship.values
                 else r.get('relationship')} for r in snap.get('requirements') or []]
    rel = item.release
    return {'benchmark_code': item.benchmark.benchmark_code, 'version_label': snap.get('version_label'),
            'status': item.benchmark.status, 'origin': origin, 'source_references': refs,
            'source_document_linked': bool(refs),
            'naac_crosswalk_count': len(snap.get('naac_crosswalk') or []),
            'frozen_in': {'release_label': rel.release_label, 'status': rel.status,
                          'published_at': rel.published_at.isoformat() if rel.published_at else None}}


def releases_with(benchmark):
    """Published / retired releases holding a frozen copy of this benchmark, newest first."""
    from ..models import BenchmarkRelease
    items = (benchmark.release_items.filter(release__status__in=[BenchmarkRelease.Status.PUBLISHED,
                                                                  BenchmarkRelease.Status.RETIRED])
             .select_related('release').order_by('-release__published_at'))
    return [{'release_label': i.release.release_label, 'status': i.release.status,
             'published_at': i.release.published_at.isoformat() if i.release.published_at else None} for i in items]


# -- edits (drafts only, audited) ---------------------------------------------------------

def _check_draft(benchmark):
    from .linking import LinkError, _check_draft as check
    try:
        check(benchmark)
    except LinkError as exc:
        raise ProvenanceError(str(exc)) from exc


def _audit(user, action, obj, before, after, reason):
    SourceAuditEvent.objects.create(actor=user.email, action=action, object_type=type(obj).__name__,
                                    object_id=str(obj.pk), before=before, after=after, reason=reason)


def set_manual_origin(benchmark, user, *, description, reference='', reason=''):
    """An "other" origin, entered by a reviewer -- only when no origin is recorded (a workbook import or a
    candidate is a recorded fact and is never overwritten)."""
    _check_draft(benchmark)
    description, reference = ' '.join((description or '').split()), (reference or '').strip()
    if not description:
        raise ProvenanceError('Describe where this indicator came from.')
    current = origin_of(benchmark)
    if current['type'] and current['type'] != Origin.MANUAL:
        raise ProvenanceError(f'{benchmark.benchmark_code} already has a recorded origin ({current["label"]}); '
                              'it cannot be replaced by hand. Add supporting sources as source references instead.')
    with transaction.atomic():
        before = {'origin_type': benchmark.origin_type, 'origin': benchmark.origin}
        benchmark.origin_type = Origin.MANUAL
        benchmark.origin = {'description': description[:1000], 'reference': reference[:500],
                            'entered_by': user.email, 'entered_at': timezone.now().isoformat()}
        benchmark.save(update_fields=['origin_type', 'origin', 'updated_at'])
        _audit(user, 'benchmark.origin_set', benchmark, before,
               {'origin_type': benchmark.origin_type, 'origin': benchmark.origin}, (reason or '').strip())
    return benchmark


def clear_manual_origin(benchmark, user, *, reason):
    _check_draft(benchmark)
    if not (reason or '').strip():
        raise ProvenanceError('Give a reason for removing the origin.')
    if benchmark.origin_type != Origin.MANUAL:
        raise ProvenanceError('Only an origin entered by a reviewer can be removed.')
    with transaction.atomic():
        before = {'origin_type': benchmark.origin_type, 'origin': benchmark.origin}
        benchmark.origin_type, benchmark.origin = '', {}
        benchmark.save(update_fields=['origin_type', 'origin', 'updated_at'])
        _audit(user, 'benchmark.origin_cleared', benchmark, before, None, reason.strip())
    return benchmark


def add_source_reference(benchmark, user, *, version, page, source_quote, statement, relationship,
                         kind=RequirementKind.GUIDANCE, note=''):
    """A reviewer adds a source reference by hand: the exact words of a Source Library version (checked against
    its extracted text when there is any) become an approved requirement, entered and accepted by that reviewer,
    and are linked to the indicator. One requirement can then be linked to more indicators as usual."""
    from .linking import LinkError, link
    from .requirement_drafting import _next_code

    _check_draft(benchmark)
    if relationship not in Relationship.values:
        raise ProvenanceError(f'relationship must be one of {Relationship.values}.')
    if kind not in RequirementKind.values:
        raise ProvenanceError(f'kind must be one of {RequirementKind.values}.')
    if version.status == SourceVersion.Status.WITHDRAWN:
        raise ProvenanceError(f'{version} was withdrawn; cite a current version.')
    statement, quote = ' '.join((statement or '').split()), (source_quote or '').strip()
    if not quote:
        raise ProvenanceError('Paste the exact words from the source.')
    if not statement:
        raise ProvenanceError('Write what the source requires, in one sentence.')
    if page is not None:
        if page < 1 or (version.pages and page > version.pages):
            raise ProvenanceError(f'Page {page} is not in {version} ({version.pages or "?"} pages).')
    checked = quote_check(version, quote, page)
    if checked is False:
        where = f'on page {page} of ' if page is not None else 'in '
        raise ProvenanceError(f'These words are not {where}{version}. Copy them exactly from the source.')
    with transaction.atomic():
        now = timezone.now()
        req = Requirement.objects.create(code=_next_code(version), version=version, statement=statement, kind=kind,
                                         page=page, source_quote=quote, approved_by=user, approved_at=now)
        _audit(user, 'requirement.entered', req, None,
               {'code': req.code, 'statement': statement, 'kind': kind, 'page': page, 'source': str(version),
                'quote_checked': checked is True, 'for_benchmark': benchmark.benchmark_code}, note)
        try:
            link(benchmark, req, user, relationship=relationship, note=note)
        except LinkError as exc:
            raise ProvenanceError(str(exc)) from exc
    return req


# -- the other direction: which indicators a source / requirement supports ------------------

def indicators_by_document():
    """{document_id: [{benchmark_code, title, status, links: [{requirement_code, relationship}]}]} in one query."""
    out = {}
    rows = (BenchmarkRequirement.objects
            .values_list('requirement__version__document_id', 'benchmark__benchmark_code', 'benchmark__title',
                         'benchmark__status', 'requirement__code', 'relationship')
            .order_by('benchmark__benchmark_code', 'requirement__code'))
    for doc_id, code, title, status, req_code, rel in rows:
        by_code = out.setdefault(str(doc_id), {})
        entry = by_code.setdefault(code, {'benchmark_code': code, 'title': title, 'status': status, 'links': []})
        entry['links'].append({'requirement_code': req_code, 'relationship': rel})
    return {doc: list(codes.values()) for doc, codes in out.items()}
