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
"""
import logging
import os
import re
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


def draft_section(section, service):
    """Ask the AI for requirements in one section; keep only verifiable ones."""
    result = service.extract_structured_data(
        system_prompt=SYSTEM_PROMPT,
        user_content=f'Source: {section.version.document.title} ({section.version.version_label})\n\n{section.text}',
        response_schema=SCHEMA, schema_name='source_requirements')
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
    RequirementCandidate.objects.bulk_create(kept)
    return len(kept), dropped


def draft_version(version, *, actor='requirement_drafting'):
    """Sections (if missing) + AI drafts for every section. Call inside a router
    lease in multi_router mode (the Celery task does that)."""
    from apps.extraction.models import AIUsage
    from apps.extraction.services.ai_service import get_ai_service
    from apps.extraction.usage import usage_scope

    if not version.sections.exists():
        build_sections(version)
    version.requirement_candidates.filter(status=RequirementCandidate.Status.PENDING).delete()
    service = get_ai_service()
    kept = dropped = 0
    with usage_scope(stage=AIUsage.Stage.OTHER):
        for section in version.sections.all():
            k, d = draft_section(section, service)
            kept, dropped = kept + k, dropped + d
    SourceAuditEvent.objects.create(actor=actor, action='requirements.drafted', object_type='SourceVersion',
                                    object_id=str(version.pk), after={'drafts': kept, 'dropped_unverifiable': dropped,
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
