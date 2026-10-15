"""Stage 4b: benchmark candidates -- proposed library changes, apart from
approved data until domain experts approve them (schema: benchmark_candidates,
candidate_reviews; guide: "A watcher candidate is not an active requirement or
benchmark", "Create candidates only; never publish automatically").

From the watcher (`create_from_event`), for every material change event:
  - one "update benchmark" candidate per benchmark linked to the changed source
    (a withdrawal proposes retiring nothing by itself -- it asks for an update);
  - a "review this source" candidate when no benchmark depends on it yet.
  Low-authority sources are rejected automatically; a candidate that duplicates
  one still open for the same benchmark / source is not created.

Who must approve (`required_roles`), per the guide:
  regulatory / government policy sources -> accreditation + legal
  accreditation bodies                    -> accreditation + academic
  rankings                                -> academic
  standards bodies                        -> academic (+ cybersecurity for CERT-In style sources)
  anything about an AI benchmark          -> + ai_governance + academic
Each required role must be approved by a different person; any reject
rejects the candidate; "needs research" sends it back to research.

An approved "update" candidate lets staff reopen the active benchmark as a new
draft (`reopen_for_revision`); it is marked published when a release carrying
that benchmark is published (`mark_published`, called by releases.publish).
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from ..models import (
    Authority, Benchmark, BenchmarkCandidate, BenchmarkRequirement, CandidateReview, SourceAuditEvent,
    SourceChangeEvent, SourceDocument,
)

Type, Status, Role = BenchmarkCandidate.Type, BenchmarkCandidate.Status, BenchmarkCandidate.Role
MIN_MATERIALITY = 50
MIN_AUTHORITY_TRUST = 50
OPEN_STATUSES = (Status.RESEARCH, Status.REVIEW, Status.APPROVED)
CANDIDATE_EVENT_KINDS = (SourceChangeEvent.Kind.NEW_DOCUMENT, SourceChangeEvent.Kind.NEW_VERSION,
                         SourceChangeEvent.Kind.CONTENT_CHANGE, SourceChangeEvent.Kind.WITHDRAWAL)


class CandidateError(Exception):
    pass


def _audit(actor, action, candidate, after=None, reason=''):
    SourceAuditEvent.objects.create(actor=actor, action=action, object_type='BenchmarkCandidate',
                                    object_id=str(candidate.pk), after=after, reason=reason)


def _is_ai(document=None, benchmark=None, extra_text=''):
    text = ' '.join(filter(None, [
        benchmark.benchmark_code if benchmark else '', benchmark.title if benchmark else '',
        document.category if document else '', document.title if document else '', extra_text,
    ])).lower().replace('-', ' ')
    return (benchmark is not None and benchmark.benchmark_code.upper().startswith('AI')) or ' ai ' in f' {text} ' \
        or 'artificial intelligence' in text


def required_roles_for(document=None, benchmark=None, *, title='', proposed_kind=''):
    roles = []
    kind = document.framework.authority.kind if document else ''
    if kind in (Authority.Kind.REGULATORY, Authority.Kind.GOVERNMENT_POLICY):
        roles += [Role.ACCREDITATION, Role.LEGAL]
    elif kind == Authority.Kind.ACCREDITATION:
        roles += [Role.ACCREDITATION, Role.ACADEMIC]
    elif kind in (Authority.Kind.RANKING, Authority.Kind.STANDARDS_BODY):
        roles += [Role.ACADEMIC]
        if document and 'cert' in (document.framework.authority.code or '').lower():
            roles += [Role.CYBERSECURITY]
    if (_is_ai(document, benchmark, title) or proposed_kind == 'proposed'
            or (benchmark and benchmark.benchmark_kind == 'proposed')):
        roles += [Role.AI_GOVERNANCE, Role.ACADEMIC]
    if not roles:
        roles = [Role.ACADEMIC, Role.PRODUCT]
    return list(dict.fromkeys(str(r) for r in roles))


def _rationale(event):
    lines = [f'Watcher: {event.get_change_kind_display()} on {event.document.source_code} '
             f'({event.document.title}) — {event.summary}']
    for title, url in (event.details or {}).get('added', [])[:5]:
        lines.append(f'+ {title or url} — {url}')
    for title, url in (event.details or {}).get('removed', [])[:5]:
        lines.append(f'- no longer listed: {title or url}')
    for line in (event.details or {}).get('added_lines', [])[:5]:
        lines.append(f'+ "{line}"')
    if event.feed_id:
        lines.append(f'Official page: {event.feed.endpoint_url}')
    return '\n'.join(lines)


def create_from_event(event):
    """Candidates for one change event. Returns the list created (auto-rejected
    low-authority ones included); duplicates of open candidates are skipped."""
    if event.change_kind not in CANDIDATE_EVENT_KINDS or event.materiality_score < MIN_MATERIALITY:
        return []
    doc = event.document
    low_authority = (doc.source_role == SourceDocument.Role.INTELLIGENCE
                     or (event.feed is not None and event.feed.authority_trust_score < MIN_AUTHORITY_TRUST))
    benches = list(Benchmark.objects.filter(
        requirement_links__requirement__version__document=doc).exclude(status=Benchmark.Status.WITHDRAWN).distinct())
    rationale = _rationale(event)
    now = timezone.now()
    targets = [(Type.UPDATE_BENCHMARK, b, f'Review {b.benchmark_code} after a change to {doc.source_code}') for b in benches] \
        or [(Type.SOURCE_UPDATE, None, f'Review the change to {doc.source_code}: {doc.title}'[:300])]
    created = []
    with transaction.atomic():
        for ctype, bench, title in targets:
            open_q = BenchmarkCandidate.objects.filter(status__in=OPEN_STATUSES, candidate_type=ctype)
            open_q = open_q.filter(benchmark=bench) if bench else open_q.filter(source_document=doc, benchmark__isnull=True)
            if open_q.exists():
                continue  # a candidate for this is already open -- don't duplicate it
            c = BenchmarkCandidate.objects.create(
                change_event=event, source_document=doc, benchmark=bench,
                capability=bench.capability if bench else None, candidate_type=ctype, title=title[:300],
                proposed_kind=bench.benchmark_kind if bench else 'mandatory', source_rationale=rationale,
                emergence_score=event.materiality_score, required_roles=required_roles_for(doc, bench),
                status=Status.REJECTED if low_authority else Status.REVIEW, created_by='watcher',
                decided_at=now if low_authority else None)
            _audit('watcher', 'candidate.auto_rejected' if low_authority else 'candidate.created', c,
                   after={'type': ctype, 'benchmark': bench.benchmark_code if bench else None,
                          'event': str(event.pk)},
                   reason='Low-authority source (intelligence signal or trust score below '
                          f'{MIN_AUTHORITY_TRUST}).' if low_authority else '')
            created.append(c)
    return created


def create(user, data):
    ctype = data.get('candidate_type') or Type.NEW_BENCHMARK
    if ctype not in Type.values:
        raise CandidateError(f'candidate_type must be one of {Type.values}.')
    title = (data.get('title') or '').strip()
    rationale = (data.get('source_rationale') or '').strip()
    if not title or not rationale:
        raise CandidateError('A title and the source rationale (why, according to which source) are needed.')
    bench = None
    if data.get('benchmark_code'):
        bench = Benchmark.objects.filter(benchmark_code=data['benchmark_code']).first()
        if bench is None:
            raise CandidateError('Unknown benchmark.')
    if ctype in (Type.UPDATE_BENCHMARK, Type.RETIRE_BENCHMARK) and bench is None:
        raise CandidateError('Choose the benchmark this candidate updates or retires.')
    doc = SourceDocument.objects.filter(source_code=data.get('source_code', '')).first() if data.get('source_code') else None
    event = SourceChangeEvent.objects.filter(pk=data['change_event']).first() if data.get('change_event') else None
    if event and not doc:
        doc = event.document
    c = BenchmarkCandidate.objects.create(
        change_event=event, source_document=doc, benchmark=bench, capability=bench.capability if bench else None,
        candidate_type=ctype, title=title[:300], source_rationale=rationale,
        proposed_kind=data.get('proposed_kind') or (bench.benchmark_kind if bench else 'proposed'),
        emergence_score=Decimal(str(event.materiality_score)) if event else 0,
        required_roles=required_roles_for(doc, bench, title=title,
                                          proposed_kind=data.get('proposed_kind') or ('' if bench else 'proposed')),
        status=Status.RESEARCH, created_by=user.email)
    _audit(user.email, 'candidate.created', c, after={'type': ctype})
    return c


EDITABLE = ('title', 'source_rationale', 'proposed_kind', 'proposed_maturity', 'proposed_evidence_rules',
            'feasibility_score', 'duplication_score', 'required_roles')


def update(candidate, user, data):
    if candidate.status not in (Status.RESEARCH, Status.REVIEW):
        raise CandidateError(f'A {candidate.get_status_display().lower()} candidate cannot be changed.')
    changed = {}
    for field in EDITABLE:
        if field not in data:
            continue
        value = data[field]
        if field == 'required_roles':
            value = list(dict.fromkeys(value or []))
            if not value or any(r not in Role.values for r in value):
                raise CandidateError(f'required_roles must be a non-empty list from {Role.values}.')
            if candidate.reviews.exists():
                raise CandidateError('Reviews have started; the required roles can no longer change.')
        if field in ('feasibility_score', 'duplication_score'):
            value = Decimal(str(value))
            if not 0 <= value <= 100:
                raise CandidateError(f'{field} must be 0-100.')
        setattr(candidate, field, value)
        changed[field] = str(value)[:200]
    candidate.save()
    _audit(user.email, 'candidate.updated', candidate, after=changed)
    return candidate


def submit(candidate, user):
    if candidate.status != Status.RESEARCH:
        raise CandidateError('Only a candidate in research can be sent to expert review.')
    candidate.status = Status.REVIEW
    candidate.save(update_fields=['status'])
    _audit(user.email, 'candidate.submitted', candidate)


def _latest_by_role(candidate):
    latest = {}
    for r in candidate.reviews.select_related('reviewer').order_by('reviewed_at'):
        latest[r.reviewer_role] = r
    return latest


def review(candidate, user, role, decision, notes=''):
    if candidate.status != Status.REVIEW:
        raise CandidateError('Only a candidate in expert review can be reviewed.')
    if role not in candidate.required_roles:
        raise CandidateError(f'This candidate needs reviews from: {", ".join(candidate.required_roles)}.')
    if decision not in CandidateReview.Decision.values:
        raise CandidateError(f'decision must be one of {CandidateReview.Decision.values}.')
    notes = (notes or '').strip()
    if decision != CandidateReview.Decision.APPROVE and not notes:
        raise CandidateError('Say why, so the next person knows what to change.')
    others = {r: rv for r, rv in _latest_by_role(candidate).items() if r != role}
    if any(rv.reviewer_id == user.pk for rv in others.values()):
        raise CandidateError('Each required role must be reviewed by a different person.')
    with transaction.atomic():
        CandidateReview.objects.create(candidate=candidate, reviewer=user, reviewer_role=role, decision=decision,
                                       notes=notes)
        latest = _latest_by_role(candidate)
        decisions = {r: latest[r].decision for r in latest}
        if CandidateReview.Decision.REJECT in decisions.values():
            candidate.status, candidate.decided_at = Status.REJECTED, timezone.now()
        elif decision == CandidateReview.Decision.NEEDS_RESEARCH:
            candidate.status = Status.RESEARCH
        elif all(decisions.get(r) == CandidateReview.Decision.APPROVE for r in candidate.required_roles):
            candidate.status, candidate.decided_at = Status.APPROVED, timezone.now()
        candidate.save(update_fields=['status', 'decided_at'])
        _audit(user.email, 'candidate.reviewed', candidate,
               after={'role': role, 'decision': decision, 'status': candidate.status}, reason=notes)
    return candidate


def reopen_for_revision(candidate, user):
    """Approved update/retire candidate -> the active benchmark becomes a new draft
    version for the next release (releases.reopen_benchmark)."""
    from .releases import ReleaseError, reopen_benchmark

    if candidate.status != Status.APPROVED or candidate.benchmark is None:
        raise CandidateError('Only an approved candidate for a specific benchmark can open a revision.')
    if candidate.benchmark.status == Benchmark.Status.DRAFT:
        return candidate.benchmark  # already being revised
    try:
        reopen_benchmark(candidate.benchmark, user, f'Approved candidate: {candidate.title}')
    except ReleaseError as exc:
        raise CandidateError(str(exc))
    _audit(user.email, 'candidate.revision_opened', candidate, after={'benchmark': candidate.benchmark.benchmark_code})
    candidate.benchmark.refresh_from_db()
    return candidate.benchmark


def mark_published(release):
    """Called when `release` is published: approved candidates for benchmarks it
    adds, updates or retires are now in effect."""
    codes = release.items.exclude(change_type='unchanged').values_list('benchmark_id', flat=True)
    for c in BenchmarkCandidate.objects.filter(status=Status.APPROVED, benchmark_id__in=list(codes)):
        c.status = Status.PUBLISHED
        c.save(update_fields=['status'])
        _audit('release', 'candidate.published', c, after={'release': release.release_label})
