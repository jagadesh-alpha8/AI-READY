"""Stage 2: split a stored source file into sections, then have the AI draft
atomic requirements from each section for expert review.

Safeguards (the blueprint: AI proposes, people decide):
- Every draft must quote the source's exact words and name a page inside its
  section; a draft whose quote can't be found in that section's text is
  dropped, so the AI can't invent a requirement.
- Drafts are RequirementCandidates (pending). Only an expert's accept turns
  one into a Requirement (see accept_candidate).
- AI calls go through get_ai_service(), so they follow AI_PROCESSING_MODE
  (single / multi_router) and are recorded in AI usage like extraction calls.
- A rate limit (HTTP 429, e.g. a free-tier "requests per minute" quota) waits
  as long as the provider asks and retries the same section; each finished
  section is marked (drafted_at), so a rerun after a failure drafts only the
  sections that are left and keeps the drafts already made.
"""
import logging
import os
import re
import time
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import (
    Requirement, RequirementCandidate, RequirementKind, SourceAuditEvent, SourceSection, SourceVersion,
)
from .file_intake import stored_path

logger = logging.getLogger(__name__)

SECTION_MAX_CHARS = 12000  # same page-grouping cap as the fact extractor
MAX_SECTIONS = 60          # safety cap on AI calls per document

RATE_LIMIT_RETRIES = 6        # per section, after a 429
RATE_LIMIT_DEFAULT_WAIT = 20  # seconds, when the provider gives no retry hint
RATE_LIMIT_MAX_WAIT = 120     # never sleep longer than this at once
_sleep = time.sleep           # replaced in tests

SYSTEM_PROMPT = (
    'You extract atomic requirements from an official Indian higher-education / skills / technology source '
    '(regulation, accreditation manual, standard or guideline). An atomic requirement is ONE testable statement '
    'about what an institution must, should or may do or have.\n'
    'Rules:\n'
    '- Only extract what the text actually says. Never add, generalise or infer.\n'
    '- source_quote must be copied EXACTLY from the text (verbatim, 8-60 words).\n'
    '- page must be the page number the quote is on (pages are marked "[Page N]").\n'
    '- kind: "mandatory" (shall/must/is required), "recommended" (should), "guidance" (may/explanatory good practice).\n'
    '- statement: one sentence starting "The institution ...", faithful to the quote.\n'
    '- Skip definitions, procedures for the regulator itself, fees, forms, tables of contents and boilerplate.\n'
    '- If the section contains no requirements, return an empty list.'
)

SCHEMA = {
    'type': 'object',
    'properties': {'requirements': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {
            'statement': {'type': 'string'},
            'kind': {'type': 'string', 'enum': ['mandatory', 'recommended', 'guidance']},
            'page': {'type': 'integer'},
            'source_quote': {'type': 'string'},
            'confidence': {'type': 'number'},
            'rationale': {'type': 'string'},
        },
        'required': ['statement', 'kind', 'page', 'source_quote', 'confidence', 'rationale'],
        'additionalProperties': False,
    }}},
    'required': ['requirements'],
    'additionalProperties': False,
}


class DraftingError(Exception):
    pass


# -- sections ----------------------------------------------------------------

class _StoredFile:
    """The bits of a Django FieldFile that PDFPageReader uses."""
    def __init__(self, path):
        self.name, self._fh = path, None

    def __bool__(self):
        return True

    def open(self, mode='rb'):
        self._fh = open(self.name, mode)

    def read(self):
        return self._fh.read()

    def close(self):
        if self._fh:
            self._fh.close()


def read_pages(version):
    from apps.extraction.services.pdf_reader import PDFPageReader

    path = stored_path(version)
    if not path or not os.path.exists(path):
        raise DraftingError('No stored file: run file intake (ingest_source_files) first.')
    doc = SimpleNamespace(id=version.pk, file=_StoredFile(path), original_filename=os.path.basename(path))
    result = PDFPageReader().read_pages(doc)
    if not result.get('format_supported', True):
        raise DraftingError(result.get('format_note') or 'Unsupported file format.')
    return [p for p in result['pages'] if (p.get('text') or '').strip()]


def build_sections(version, pages=None):
    """Replace the version's sections. Refused once any draft was reviewed."""
    if version.requirement_candidates.exclude(status=RequirementCandidate.Status.PENDING).exists():
        raise DraftingError('Drafts of this version were already reviewed; sections are kept as they are.')
    pages = pages if pages is not None else read_pages(version)
    groups, current, size = [], [], 0
    for p in pages:
        text = p['text']
        if current and size + len(text) > SECTION_MAX_CHARS:
            groups.append(current)
            current, size = [], 0
        current.append(p)
        size += len(text)
    if current:
        groups.append(current)
    if len(groups) > MAX_SECTIONS:
        logger.warning('benchmarks.sections.capped version=%s sections=%d cap=%d', version.pk, len(groups), MAX_SECTIONS)
        groups = groups[:MAX_SECTIONS]
    with transaction.atomic():
        version.requirement_candidates.all().delete()
        version.sections.all().delete()
        for i, group in enumerate(groups, start=1):
            first_line = next((ln.strip() for ln in group[0]['text'].splitlines() if ln.strip()), '')
            SourceSection.objects.create(
                version=version, ordinal=i, heading=first_line[:300],
                page_start=group[0]['page_number'], page_end=group[-1]['page_number'],
                text='\n\n'.join(f'[Page {p["page_number"]}]\n{p["text"]}' for p in group))
    return version.sections.count()


# -- drafting ----------------------------------------------------------------

def _norm(text):
    return re.sub(r'\s+', ' ', (text or '')).strip().lower()


#: A provider's own retry hint in its error text: Gemini's "retryDelay': '4s'" or "Please retry in 4.5s".
_RETRY_HINT = re.compile(r'retry(?:Delay[\'"]?\s*:\s*[\'"]|\s+in\s+)(\d+(?:\.\d+)?)\s*s', re.I)


def rate_limit_wait(exc):
    """Seconds to wait before retrying `exc`, or None when it is not a rate limit (HTTP 429). Uses the
    provider's own hint -- a Retry-After header, else a delay named in the message -- plus a second of
    margin, capped at RATE_LIMIT_MAX_WAIT."""
    cause = exc.__cause__ or exc
    if getattr(cause, 'status_code', None) != 429 and 'rate limit' not in str(exc).lower():
        return None
    wait = None
    response = getattr(cause, 'response', None)
    header = getattr(response, 'headers', {}).get('retry-after') if response is not None else None
    if header:
        try:
            wait = float(header)
        except ValueError:
            wait = None
    if wait is None:
        match = _RETRY_HINT.search(str(exc))
        wait = float(match.group(1)) if match else RATE_LIMIT_DEFAULT_WAIT
    return min(max(wait, 0) + 1, RATE_LIMIT_MAX_WAIT)


def _ask_ai(section, service):
    """One AI call for the section, retried after a rate limit (any other error is raised at once)."""
    from apps.extraction.exceptions import RecoverableExtractionError

    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return service.extract_structured_data(
                system_prompt=SYSTEM_PROMPT,
                user_content=f'Source: {section.version.document.title} ({section.version.version_label})\n\n{section.text}',
                response_schema=SCHEMA, schema_name='source_requirements')
        except RecoverableExtractionError as exc:
            wait = rate_limit_wait(exc)
            if wait is None or attempt == RATE_LIMIT_RETRIES:
                raise
            logger.warning('benchmarks.drafting.rate_limited section=%s attempt=%d wait=%.1fs',
                           section.pk, attempt + 1, wait)
            _sleep(wait)


def _verified(section, service, result):
    """The AI's drafts for the section that quote its text on one of its pages (others are dropped)."""
    kept, dropped = [], 0
    haystack = _norm(section.text)
    for item in (result or {}).get('requirements', []):
        quote = (item.get('source_quote') or '').strip()
        page = item.get('page')
        statement = (item.get('statement') or '').strip()
        if (not statement or len(_norm(quote)) < 20 or _norm(quote) not in haystack
                or not isinstance(page, int) or not section.page_start <= page <= section.page_end):
            dropped += 1
            continue
        kind = item.get('kind') if item.get('kind') in RequirementKind.values else RequirementKind.GUIDANCE
        kept.append(RequirementCandidate(
            version=section.version, section=section, statement=statement[:2000], kind=kind, page=page,
            source_quote=quote[:2000], confidence=max(0.0, min(1.0, float(item.get('confidence') or 0))),
            rationale=(item.get('rationale') or '')[:2000], model=getattr(service, 'model', '') or ''))
    return kept, dropped


def _save_section(section, kept):
    """Store the section's drafts and mark it finished, together (a crash never leaves half a section)."""
    with transaction.atomic():
        section.candidates.filter(status=RequirementCandidate.Status.PENDING).delete()  # an interrupted attempt
        RequirementCandidate.objects.bulk_create(kept)
        section.drafted_at = timezone.now()
        section.save(update_fields=['drafted_at'])


def draft_section(section, service):
    """Ask the AI for requirements in one section; keep only verifiable ones."""
    kept, dropped = _verified(section, service, _ask_ai(section, service))
    _save_section(section, kept)
    return len(kept), dropped


def draft_version(version, *, actor='requirement_drafting'):
    """Sections (if missing) + AI drafts for every section not drafted yet. Call inside a router
    lease in multi_router mode (the Celery task does that).

    A rerun after an interrupted run (a rate limit that outlasted its retries, a crash) drafts only the
    sections left and keeps the drafts of the finished ones. A version whose sections are all finished
    is drafted afresh, as before: its pending drafts are replaced; reviewed ones are never touched."""
    from apps.extraction.models import AIUsage
    from apps.extraction.services.ai_service import get_ai_service
    from apps.extraction.usage import usage_scope

    if not version.sections.exists():
        build_sections(version)
    sections = list(version.sections.all())
    if all(s.drafted_at for s in sections):
        version.requirement_candidates.filter(status=RequirementCandidate.Status.PENDING).delete()
        version.sections.update(drafted_at=None)
        for s in sections:
            s.drafted_at = None
    todo = [s for s in sections if s.drafted_at is None]
    service = get_ai_service()
    kept = dropped = 0
    with usage_scope(stage=AIUsage.Stage.OTHER):
        for section in todo:
            k, d = draft_section(section, service)
            kept, dropped = kept + k, dropped + d
    SourceAuditEvent.objects.create(actor=actor, action='requirements.drafted', object_type='SourceVersion',
                                    object_id=str(version.pk), after={
                                        'drafts': kept, 'dropped_unverifiable': dropped,
                                        'sections_drafted': len(todo), 'sections_kept': len(sections) - len(todo),
                                        'model': getattr(service, 'model', '')})
    return kept, dropped


# -- review ------------------------------------------------------------------

def _next_code(version):
    prefix = f'{version.document.source_code}-R'
    used = Requirement.objects.filter(code__startswith=prefix).values_list('code', flat=True)
    nums = [int(c[len(prefix):]) for c in used if c[len(prefix):].isdigit()]
    return f'{prefix}{(max(nums) if nums else 0) + 1:03d}'


def accept_candidate(candidate, user, *, statement=None, kind=None, note=''):
    """Expert accepts a draft (optionally edited) -> a Requirement."""
    if candidate.status != RequirementCandidate.Status.PENDING:
        raise DraftingError(f'This draft was already {candidate.status}.')
    if candidate.version.status == SourceVersion.Status.WITHDRAWN:
        raise DraftingError('The source version was withdrawn.')
    if kind and kind not in RequirementKind.values:
        raise DraftingError(f'kind must be one of {RequirementKind.values}.')
    with transaction.atomic():
        now = timezone.now()
        req = Requirement.objects.create(
            code=_next_code(candidate.version), version=candidate.version, section=candidate.section,
            statement=(statement or candidate.statement).strip(), kind=kind or candidate.kind, page=candidate.page,
            source_quote=candidate.source_quote, created_from=candidate, approved_by=user, approved_at=now)
        candidate.status, candidate.reviewed_by, candidate.reviewed_at = RequirementCandidate.Status.ACCEPTED, user, now
        candidate.review_note = note
        candidate.save()
        SourceAuditEvent.objects.create(
            actor=user.email, action='requirement.accepted', object_type='Requirement', object_id=str(req.pk),
            after={'code': req.code, 'statement': req.statement, 'kind': req.kind,
                   'edited': bool(statement and statement.strip() != candidate.statement)}, reason=note)
    return req


def reject_candidate(candidate, user, *, note=''):
    if candidate.status != RequirementCandidate.Status.PENDING:
        raise DraftingError(f'This draft was already {candidate.status}.')
    candidate.status, candidate.reviewed_by, candidate.reviewed_at = RequirementCandidate.Status.REJECTED, user, timezone.now()
    candidate.review_note = note
    candidate.save()
    SourceAuditEvent.objects.create(actor=user.email, action='requirement.rejected', object_type='RequirementCandidate',
                                    object_id=str(candidate.pk), reason=note)
