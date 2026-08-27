"""Real, AI-backed `FactExtractor`.

Splits a document's already-read pages (from `PDFPageReader`) into
page-boundary-respecting text chunks, asks whichever AI provider is
configured (see `ai_service.get_ai_service`) for structured facts per
chunk, independently validates and *types* every fact in Python (the AI
only ever returns `value` as plain text -- this module decides what it
means for `data_type`), and merges duplicate facts across chunks.

The dicts this returns are already shaped exactly like `ExtractedFact`
creation kwargs (see `pipeline.py: _persist_facts`), which is what lets
`IdentityAuditFieldMapper` below be a genuine pass-through instead of
another stub -- there's nothing left to map. The class name predates
multi-provider support -- despite it, this works with any configured provider.
"""
import logging
import re

from django.conf import settings

from apps.facts.models import ExtractedFact
from apps.scoring.constants import PILLAR_CHOICES

from ..exceptions import AIResponseError, PermanentExtractionError, RecoverableExtractionError
from .ai_service import get_ai_service
from .base import AuditFieldMapper, FactExtractor

logger = logging.getLogger(__name__)

VALID_DATA_TYPES = set(ExtractedFact.DataType.values)
VALID_PILLARS = {key for key, _label in PILLAR_CHOICES}

#: Campus-side roles that can realistically be asked to confirm a fact --
#: deliberately excludes super_admin/consultant (platform staff, not content
#: owners) and viewer (read-only). Kept as an explicit list (rather than
#: every apps.accounts.models.User.Role) both to steer the model towards
#: sensible choices via the schema `enum` below and so a fact never gets
#: assigned to a role that couldn't plausibly own institutional evidence.
FACT_OWNER_ROLE_CHOICES = [
    'institution_admin', 'iqac_coordinator', 'registrar', 'hod',
    'hr_officer', 'lab_admin', 'placement_officer', 'faculty',
]

SYSTEM_PROMPT = f"""You are extracting structured facts from one institutional audit document for a \
higher-education AI-readiness audit platform. Extracted facts feed a scoring engine across eight \
fixed pillars: {', '.join(key for key, _ in PILLAR_CHOICES)}.

You will be given one chunk of the document's real, extracted text, broken into pages with \
"--- Page N ---" markers. Relevant facts include (not an exhaustive list): faculty counts, \
AI-certified faculty, student enrolment/strength, placement statistics, research/publication counts, \
laboratory infrastructure, AI software/tool licenses, industry MoUs, curriculum and AI-course \
information, and governance/policy information -- but only ones the given text actually supports.

Follow these rules exactly, without exception:
- Extract only information supported by the supplied document.
- Never invent numbers, names, dates, statistics or institutional information.
- If information is unavailable, return no fact. Do not create a fact with a guessed or approximate \
value, and do not create a fact just because a category above seems like it should be present.
- Every fact must have supporting evidence: a real snippet quoted or closely paraphrased from the \
text you were given.
- Prefer null over guessing. If you're confident a fact is real but unsure of one specific detail \
(such as exactly which page it's on), return null for that detail -- but if you are not confident \
the fact itself is real, do not include it at all.
- Only cite a page number that actually appears as a "--- Page N ---" marker in the text you were \
given -- never a page number from outside this chunk.
- `value` must always be a plain string, exactly as it should be read off the page (e.g. "42", \
"85%", "Rs. 50,00,000", "Yes", "AI Lab; Cloud Compute Lab") -- do not reformat, convert, or compute \
it yourself; `data_type` tells the caller how to interpret it.
- `confidence_score` must be a number between 0 and 1, reflecting how directly the source text \
supports the value -- an explicit, clearly-labeled statement deserves high confidence; something \
inferred or ambiguously worded deserves lower confidence.
- `confidence_reason` must briefly explain, in your own words, what in the text grounds your answer.
- `owner_role` must be whichever of the given roles would realistically confirm this fact on campus: \
institution_admin (policy/governance), iqac_coordinator (quality assurance, NAAC/AQAR), registrar \
(approvals, enrolment records), hod (curriculum, department-level), hr_officer (faculty records), \
lab_admin (lab/compute infrastructure), placement_officer (placements, industry), faculty \
(course-level AI engagement).

Respond only with the requested structured fields."""

FACT_ITEM_SCHEMA = {
    'type': 'object',
    'properties': {
        'field_name': {'type': 'string', 'description': 'Human-readable label, e.g. "Total Faculty Count".'},
        'field_key': {'type': 'string', 'description': 'Machine key, snake_case, e.g. "total_faculty".'},
        'value': {
            'type': 'string',
            'description': 'The value exactly as it should be read off the page, always as plain text.',
        },
        'data_type': {'type': 'string', 'enum': sorted(VALID_DATA_TYPES)},
        'pillar': {'type': 'string', 'enum': sorted(VALID_PILLARS)},
        'owner_role': {'type': 'string', 'enum': FACT_OWNER_ROLE_CHOICES},
        'source_page': {
            'type': ['string', 'null'],
            'description': 'One of the page numbers given in this chunk, as a string, or null.',
        },
        'source_snippet': {'type': 'string', 'description': 'A real snippet from the given text.'},
        'confidence_score': {'type': 'number', 'description': 'Between 0 and 1.'},
        'confidence_reason': {'type': 'string'},
    },
    'required': [
        'field_name', 'field_key', 'value', 'data_type', 'pillar', 'owner_role',
        'source_page', 'source_snippet', 'confidence_score', 'confidence_reason',
    ],
    'additionalProperties': False,
}

FACT_EXTRACTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'facts': {'type': 'array', 'items': FACT_ITEM_SCHEMA},
    },
    'required': ['facts'],
    'additionalProperties': False,
}


class FactValidationError(PermanentExtractionError):
    """One extracted fact failed this app's own validation (bad data_type,
    confidence out of range, an unverifiable page citation, ...). Callers
    drop just this one fact, not the whole chunk or document."""


def _require_nonblank_str(value, field):
    if not isinstance(value, str) or not value.strip():
        raise FactValidationError(f'{field} must be a non-empty string, got {value!r}.')
    return value.strip()


def _parse_number(text, field):
    cleaned = re.sub(r'[,\s]', '', text)
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise FactValidationError(f'{field} {text!r} is not a valid number.') from exc
    return int(number) if number.is_integer() else number


def _parse_and_normalize(raw_value, data_type):
    """Convert the AI's raw string `value` into (value, normalized_value)
    for `data_type` -- the AI never types its own output; this is the
    "Django validates all AI output" boundary. Raises FactValidationError
    rather than silently coercing something that doesn't actually fit."""
    text = raw_value.strip()
    if not text:
        raise FactValidationError('value must not be empty.')

    if data_type == ExtractedFact.DataType.NUMBER:
        number = _parse_number(text, 'value')
        return number, number

    if data_type == ExtractedFact.DataType.PERCENTAGE:
        number = _parse_number(text.replace('%', ''), 'value')
        return number, number

    if data_type == ExtractedFact.DataType.CURRENCY:
        digits = re.sub(r'[^0-9.\-]', '', text)
        number = _parse_number(digits, 'value') if digits else None
        if number is None:
            raise FactValidationError(f'value {raw_value!r} has no numeric amount.')
        return text, number

    if data_type == ExtractedFact.DataType.BOOLEAN:
        lowered = text.lower()
        if lowered in ('true', 'yes', 'y'):
            return text, True
        if lowered in ('false', 'no', 'n'):
            return text, False
        raise FactValidationError(f'value {raw_value!r} is not a recognizable boolean.')

    if data_type == ExtractedFact.DataType.LIST:
        items = [item.strip() for item in re.split(r'[;,\n]', text) if item.strip()]
        if not items:
            raise FactValidationError(f'value {raw_value!r} did not contain any list items.')
        return items, sorted({item.lower() for item in items})

    # STRING / DATE: kept as the AI's own text -- not reinterpreted, just
    # trusted no further than any other field (still went through the
    # non-empty check above).
    return text, text.lower()


def _build_chunks(pages, max_chars):
    """Group pages with real text into chunks up to `max_chars` each,
    never splitting a page across two chunks. Pages with no text (nothing
    to extract from) are skipped entirely rather than sent as empty
    context."""
    chunks = []
    current = []
    current_len = 0
    for page in pages:
        text = (page.get('text') or '').strip()
        if not text:
            continue
        if current and current_len + len(text) > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(page)
        current_len += len(text)
    if current:
        chunks.append(current)
    return chunks


class OpenAIFactExtractor(FactExtractor):
    def __init__(self, *, openai_service=None, max_chunk_chars=None, max_chunks=None):
        # Lazy, like OpenAIDocumentClassifier: no OpenAI client is built (no
        # API key required) until .extract_facts() actually runs.
        self._openai_service = openai_service
        self.max_chunk_chars = (
            max_chunk_chars if max_chunk_chars is not None
            else settings.OPENAI_FACT_EXTRACTION_MAX_CHUNK_CHARS
        )
        self.max_chunks = max_chunks if max_chunks is not None else settings.OPENAI_FACT_EXTRACTION_MAX_CHUNKS

    def extract_facts(self, document, pages):
        chunks = _build_chunks(pages.get('pages', []), self.max_chunk_chars)
        if not chunks:
            logger.info('fact_extractor.no_extractable_text document_id=%s', document.id)
            return []

        if len(chunks) > self.max_chunks:
            logger.warning(
                'fact_extractor.too_many_chunks document_id=%s chunk_count=%d max_chunks=%d',
                document.id, len(chunks), self.max_chunks,
            )
            chunks = chunks[:self.max_chunks]

        service = self._openai_service or get_ai_service()
        facts_by_key = {}

        for chunk_index, chunk_pages in enumerate(chunks, start=1):
            try:
                raw_facts = self._extract_chunk(service, document, chunk_pages, chunk_index, len(chunks))
            except RecoverableExtractionError:
                # Worth retrying the whole job (consistent with every other
                # pipeline stage) rather than silently under-extracting --
                # and a transient failure on this chunk likely affects the
                # rest too, so there's little point pressing on regardless.
                raise
            except PermanentExtractionError as exc:
                logger.error(
                    'fact_extractor.chunk_failed document_id=%s chunk=%d/%d error=%s',
                    document.id, chunk_index, len(chunks), exc,
                )
                continue

            valid_page_numbers = {str(page['page_number']) for page in chunk_pages}
            for raw_fact in raw_facts:
                try:
                    fact = self._validate_fact(raw_fact, valid_page_numbers)
                except FactValidationError as exc:
                    logger.warning(
                        'fact_extractor.fact_rejected document_id=%s chunk=%d field_key=%r error=%s',
                        document.id, chunk_index,
                        raw_fact.get('field_key') if isinstance(raw_fact, dict) else raw_fact, exc,
                    )
                    continue
                _merge_fact(facts_by_key, fact)

        facts = list(facts_by_key.values())
        logger.info(
            'fact_extractor.complete document_id=%s chunk_count=%d fact_count=%d',
            document.id, len(chunks), len(facts),
        )
        return facts

    @staticmethod
    def _extract_chunk(service, document, chunk_pages, chunk_index, chunk_count):
        text = '\n\n'.join(f'--- Page {page["page_number"]} ---\n{page["text"]}' for page in chunk_pages)
        page_numbers = ', '.join(str(page['page_number']) for page in chunk_pages)
        user_content = '\n'.join([
            f'Document: {document.original_filename or "(unknown)"} '
            f'(uploader-tagged type: {document.document_type or "(none)"})',
            f'This is chunk {chunk_index} of {chunk_count} for this document, covering page(s): {page_numbers}.',
            'Text:',
            text,
        ])

        result = service.extract_structured_data(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            response_schema=FACT_EXTRACTION_SCHEMA,
            schema_name='extracted_facts',
        )
        facts = result.get('facts') if isinstance(result, dict) else None
        if not isinstance(facts, list):
            raise AIResponseError(f'Expected a "facts" list in the response, got {result!r}.')
        return facts

    @staticmethod
    def _validate_fact(raw_fact, valid_page_numbers):
        if not isinstance(raw_fact, dict):
            raise FactValidationError(f'Expected a fact object, got {type(raw_fact).__name__}.')

        field_name = _require_nonblank_str(raw_fact.get('field_name'), 'field_name')
        field_key = _require_nonblank_str(raw_fact.get('field_key'), 'field_key')

        data_type = raw_fact.get('data_type')
        if data_type not in VALID_DATA_TYPES:
            raise FactValidationError(f'data_type must be one of {sorted(VALID_DATA_TYPES)}, got {data_type!r}.')

        raw_value = raw_fact.get('value')
        if not isinstance(raw_value, str):
            raise FactValidationError(f'value must be a string, got {raw_value!r}.')
        value, normalized_value = _parse_and_normalize(raw_value, data_type)

        pillar = raw_fact.get('pillar')
        if pillar not in VALID_PILLARS:
            raise FactValidationError(f'pillar must be one of {sorted(VALID_PILLARS)}, got {pillar!r}.')

        owner_role = raw_fact.get('owner_role')
        if owner_role not in FACT_OWNER_ROLE_CHOICES:
            raise FactValidationError(
                f'owner_role must be one of {FACT_OWNER_ROLE_CHOICES}, got {owner_role!r}.'
            )

        source_snippet = _require_nonblank_str(raw_fact.get('source_snippet'), 'source_snippet')

        source_page = raw_fact.get('source_page')
        if source_page is not None:
            if not isinstance(source_page, str) or source_page not in valid_page_numbers:
                raise FactValidationError(
                    f'source_page {source_page!r} does not match a page actually included in this chunk '
                    f'({sorted(valid_page_numbers)}).'
                )

        confidence_score = raw_fact.get('confidence_score')
        if not isinstance(confidence_score, (int, float)) or isinstance(confidence_score, bool):
            raise FactValidationError(f'confidence_score must be a number, got {confidence_score!r}.')
        if not (0.0 <= confidence_score <= 1.0):
            raise FactValidationError(f'confidence_score must be between 0 and 1, got {confidence_score!r}.')

        confidence_reason = _require_nonblank_str(raw_fact.get('confidence_reason'), 'confidence_reason')

        return {
            'field_name': field_name,
            'field_key': field_key,
            'value': value,
            'normalized_value': normalized_value,
            'data_type': data_type,
            'pillar': pillar,
            'owner_role': owner_role,
            'source_page': source_page or '',
            'source_snippet': source_snippet,
            'confidence_score': float(confidence_score),
            'confidence_reason': confidence_reason,
            'extraction_method': 'openai',
        }


def _merge_fact(facts_by_key, fact):
    """Duplicate facts across chunks are merged by field_key, keeping
    whichever has the strongest (highest-confidence) evidence rather than
    creating more than one database row for the same fact."""
    key = fact['field_key'].strip().lower()
    existing = facts_by_key.get(key)
    if existing is None or fact['confidence_score'] > existing['confidence_score']:
        facts_by_key[key] = fact


class IdentityAuditFieldMapper(AuditFieldMapper):
    """`OpenAIFactExtractor` already returns facts shaped exactly like
    `ExtractedFact` creation kwargs (see module docstring above), so there's
    nothing left to map. Real, deterministic pass-through -- not a stub --
    paired with `OpenAIFactExtractor` as `ExtractionPipeline`'s default so
    facts it extracts actually reach the database instead of being dropped
    by `stub.NullAuditFieldMapper`."""

    def map_fields(self, document, facts):
        return facts
