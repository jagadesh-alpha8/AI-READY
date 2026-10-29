"""Real, AI-backed `FactExtractor`.

Splits a document's already-read pages (from `PDFPageReader`) into
page-boundary-respecting text chunks, asks whichever AI provider is
configured (see `ai_service.get_ai_service`) for structured facts per
chunk, independently validates and *types* every fact in Python (the AI
only ever returns `value` as plain text -- this module decides what it
means for `data_type`), and merges duplicate facts across chunks.

The dicts this returns are already shaped exactly like `ExtractedFact`
creation kwargs (see `pipeline.py: _persist_facts`) -- plus `aiqif_mappings`,
the fact's AI-QIF indicator tags, saved alongside as FactAIQIFMapping rows --
which is what lets
`IdentityAuditFieldMapper` below be a genuine pass-through instead of
another stub -- there's nothing left to map. The class name predates
multi-provider support -- despite it, this works with any configured provider.
"""
import logging
import re

from django.conf import settings

from apps.facts.models import ExtractedFact
from apps.scoring.constants import AIQIF_INDICATORS, AIQIF_PILLARS, PILLAR_CHOICES

from ..exceptions import (
    AIResponseError, ExtractionCancelled, PermanentExtractionError, RecoverableExtractionError,
)
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
    'iqac_coordinator',
]

_PILLAR_GUIDE = '\n'.join(
    f'- {key}: {name} (covers: {"; ".join(kis)})' for key, _code, name, _weight, kis in AIQIF_PILLARS
)

_INDICATOR_GUIDE = '\n'.join(f'- {code}: {name}' for code, (_key, name) in AIQIF_INDICATORS.items())

#: Most indicator tags kept per fact -- a fact is evidence for one or two
#: indicators; a long list would mean the AI is guessing.
MAX_AIQIF_MAPPINGS_PER_FACT = 3

SYSTEM_PROMPT = f"""You are extracting structured facts from one institutional audit document for a \
higher-education AI-readiness audit platform. Extracted facts feed a scoring engine across the nine \
criteria of the InGage AI-QIF framework. Tag every fact with the ONE `pillar` key whose criterion it is \
evidence for:
{_PILLAR_GUIDE}

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
- `scope` says what the value measures, only as printed next to it: `period` (e.g. "2022-23", "as on \
31.03.2023"), `population` (e.g. "UG", "Department of CSE", "whole institution"), and the categories the \
figure `includes` / `excludes` (e.g. "integrated programmes"). Use null / [] for anything not printed.
- `calculation` is null unless the value is a total or share the page does not print as one number. Then -- \
and only then -- give the operation ("sum", "difference", "ratio", "percentage"), each input exactly as \
printed with its page and quote, and what it includes / excludes; `value` is the result. The caller \
recomputes it: never return a computed value without its `calculation`, and never alter a printed input.
- `owner_role` must be 'iqac_coordinator' (as the college-side coordinator responsible for institutional evidence review).

`fact_kind` says what the fact is for. Ask: "Does this fact tell us something about AI at this institution?"
- ai_evidence: yes -- the fact itself is about AI (an AI course or programme, AI lab or compute, AI policy, \
AI-trained faculty, AI projects, AI tools or licences, AI research).
- context: no, but it is a number or detail that AI evidence is read against (intake, enrolment, student or \
faculty counts, number of programmes, pass percentages, general infrastructure).
- profile: no, it describes who the institution is (institution type, approval or accreditation bodies, \
autonomous / affiliated status, affiliating university, programmes offered).

`naac_metric`: the NAAC metric number this fact is reported under (for example "2.1.2" or "1.1.3"), copied \
exactly as it is printed in the given text next to the fact -- or null if no metric number is printed there. \
Never infer a metric number that is not in the text.

`profile_field` (profile facts only, otherwise null): institution_type, autonomous_status, approval_body, \
programme, or other.

`aiqif_indicators` tags an ai_evidence fact with the AI-QIF key indicators it is evidence for -- a category, \
not a judgement of quality. For context and profile facts return an empty list. Use only these codes:
{_INDICATOR_GUIDE}
- Decide from what this fact says and its quoted evidence -- not from the document's type or title.
- List the indicator(s) the evidence directly supports: usually one, at most {MAX_AIQIF_MAPPINGS_PER_FACT}. \
Prefer indicators of the fact's own `pillar`; add another criterion's indicator only when the evidence \
plainly supports it too.
- If no indicator clearly fits, return an empty list. Never pick the closest-sounding one to fill it.
- For each, `reason` briefly says what in the evidence ties it to that indicator, and `confidence` \
(0 to 1) says how clearly it does.
- Never state or imply a maturity level, score or compliance verdict.

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
        'fact_kind': {'type': 'string', 'enum': ['ai_evidence', 'context', 'profile']},
        'naac_metric': {'type': ['string', 'null'],
                        'description': 'The NAAC metric number printed next to the fact, e.g. "2.1.2", or null.'},
        'profile_field': {'type': ['string', 'null'],
                          'enum': ['institution_type', 'autonomous_status', 'approval_body', 'programme', 'other', None]},
        'scope': {
            'type': ['object', 'null'],
            'properties': {
                'period': {'type': ['string', 'null']},
                'population': {'type': ['string', 'null']},
                'includes': {'type': 'array', 'items': {'type': 'string'}},
                'excludes': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['period', 'population', 'includes', 'excludes'],
            'additionalProperties': False,
        },
        'calculation': {
            'type': ['object', 'null'],
            'properties': {
                'operation': {'type': 'string', 'enum': ['sum', 'difference', 'ratio', 'percentage']},
                'inputs': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'label': {'type': 'string'},
                            'value': {'type': 'string'},
                            'source_page': {'type': ['string', 'null']},
                            'source_snippet': {'type': 'string'},
                        },
                        'required': ['label', 'value', 'source_page', 'source_snippet'],
                        'additionalProperties': False,
                    },
                },
                'includes': {'type': 'array', 'items': {'type': 'string'}},
                'excludes': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['operation', 'inputs', 'includes', 'excludes'],
            'additionalProperties': False,
        },
        'aiqif_indicators': {
            'type': 'array',
            'description': 'The AI-QIF key indicators this fact is evidence for; empty if none clearly fits.',
            'items': {
                'type': 'object',
                'properties': {
                    'indicator': {'type': 'string', 'enum': list(AIQIF_INDICATORS)},
                    'reason': {'type': 'string'},
                    'confidence': {'type': 'number', 'description': 'Between 0 and 1.'},
                },
                'required': ['indicator', 'reason', 'confidence'],
                'additionalProperties': False,
            },
        },
    },
    'required': [
        'field_name', 'field_key', 'value', 'data_type', 'pillar', 'owner_role',
        'source_page', 'source_snippet', 'confidence_score', 'confidence_reason', 'fact_kind', 'naac_metric',
        'profile_field', 'scope', 'calculation', 'aiqif_indicators',
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
        # The first amount in the text: "Rs. 20,000" -> 20000, not ".20000" (the prefix's dot) -> 0.2;
        # "Rs 20,000 / month" -> 20000; Indian grouping "Rs. 50,00,000" -> 5000000.
        match = re.search(r'-?\d[\d,]*(?:\.\d+)?', text)
        number = _parse_number(match.group(), 'value') if match else None
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


def new_report(chunk_count):
    """What one document's fact extraction actually read: chunks found, chunks read, and every chunk that
    failed or was skipped. A document with any issue is a *partial* extraction (services/completeness.py)."""
    return {'chunks_total': chunk_count, 'chunks_completed': 0, 'issues': []}


def completeness_issue(kind, detail, **extra):
    return {'kind': kind, 'detail': detail, **extra}


def _pages_label(chunk_pages, last=False):
    page = chunk_pages[-1 if last else 0]
    return page.get('page_number', '?')


def chunk_failed_issue(chunk_index, chunk_pages, exc):
    return completeness_issue(
        'chunk_failed', f'Text chunk {chunk_index} (pages {_pages_label(chunk_pages)}-{_pages_label(chunk_pages, last=True)}) '
        f'could not be extracted: {exc}'[:500], chunk=chunk_index)


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
        #: services/chunk_store.ChunkStore, set by ExtractionPipeline for a job: per-chunk results are saved and
        #: reused, and the chunk cap is per attempt (the job continues) instead of cutting the document off.
        self.store = None

    def chunks_for(self, document, pages):
        """The page chunks this document is analysed in (empty when there is no text). Shared with
        services/document_analysis.py. Also starts `self.report`, the record of what was actually read (see
        completeness_issue / services/completeness.py).

        Inside a job (self.store set) every chunk is kept: OPENAI_FACT_EXTRACTION_MAX_CHUNKS then caps the new AI
        calls of one attempt and the job continues with the rest (chunk_store.py). Without a store -- a direct
        call -- chunks over max_chunks are skipped and reported, as before."""
        chunks = _build_chunks(pages.get('pages', []), self.max_chunk_chars)
        self.report = new_report(len(chunks))
        if not chunks:
            logger.info('fact_extractor.no_extractable_text document_id=%s', document.id)
            return []
        if self.store is not None:
            self.store.prepare(chunks)
            return chunks
        if self.max_chunks and len(chunks) > self.max_chunks:
            logger.warning(
                'fact_extractor.too_many_chunks document_id=%s chunk_count=%d max_chunks=%d',
                document.id, len(chunks), self.max_chunks,
            )
            skipped = chunks[self.max_chunks:]
            self.report['issues'].append(completeness_issue(
                'chunks_skipped', f'{len(skipped)} of {len(chunks)} text chunks were not read (over the '
                f'{self.max_chunks}-chunk limit): pages {_pages_label(skipped[0])}-{_pages_label(skipped[-1], last=True)}.',
                chunks=list(range(self.max_chunks + 1, len(chunks) + 1))))
            chunks = chunks[:self.max_chunks]
        return chunks

    def extract_facts(self, document, pages):
        chunks = self.chunks_for(document, pages)
        if not chunks:
            return []

        services = []

        def request(chunk_index, chunk_pages):
            if not services:
                services.append(self._openai_service or get_ai_service())
            return self._extract_chunk(services[0], document, chunk_pages, chunk_index, len(chunks))

        facts_by_key = {}
        self.process_chunks(document, enumerate(chunks, start=1), len(chunks), facts_by_key, request)
        facts = list(facts_by_key.values())
        logger.info(
            'fact_extractor.complete document_id=%s chunk_count=%d fact_count=%d',
            document.id, len(chunks), len(facts),
        )
        return facts

    def process_chunks(self, document, indexed_chunks, chunk_count, facts_by_key, request):
        """Extract each (index, pages) chunk with `request(index, pages)` -> raw facts, merging the validated facts
        into `facts_by_key`. A chunk the store already completed is reused without an AI call. A recoverable
        error is recorded on the chunk and re-raised (the job retries -- only this and later chunks run again);
        a permanent one fails just this chunk (the document becomes partial)."""
        for chunk_index, chunk_pages in indexed_chunks:
            # Set by ExtractionPipeline: stop between AI calls when the user
            # presses Stop, rather than finishing a long document first.
            should_stop = getattr(self, 'should_stop', None)
            if should_stop is not None and should_stop():
                raise ExtractionCancelled(f'Fact extraction for document {document.id} was stopped by the user.')
            reused = self.store.reusable(chunk_index) if self.store is not None else None
            if reused is not None:
                self.report['chunks_completed'] += 1
                for fact in reused.facts:
                    _merge_fact(facts_by_key, fact)
                continue
            if self.store is not None:
                self.store.before_call(chunk_index)
            try:
                raw_facts = request(chunk_index, chunk_pages)
            except RecoverableExtractionError as exc:
                # Worth retrying the job (consistent with every other pipeline stage) rather than silently
                # under-extracting; chunks already done are kept and reused by the retry.
                if self.store is not None:
                    self.store.failed(chunk_index, exc)
                raise
            except PermanentExtractionError as exc:
                logger.error(
                    'fact_extractor.chunk_failed document_id=%s chunk=%d/%d error=%s',
                    document.id, chunk_index, chunk_count, exc,
                )
                self.report['issues'].append(chunk_failed_issue(chunk_index, chunk_pages, exc))
                if self.store is not None:
                    self.store.failed(chunk_index, exc)
                continue
            validated = self.validate_chunk(document, raw_facts, chunk_pages, chunk_index)
            if self.store is not None:
                self.store.completed(chunk_index, validated)
            self.report['chunks_completed'] += 1
            for fact in validated:
                _merge_fact(facts_by_key, fact)

    def validate_chunk(self, document, raw_facts, chunk_pages, chunk_index):
        """The chunk's facts that pass this app's validation (each rejected one is logged and dropped)."""
        valid_page_numbers = {str(page['page_number']) for page in chunk_pages}
        chunk_text = '\n'.join(page.get('text') or '' for page in chunk_pages)
        out = []
        for raw_fact in raw_facts:
            try:
                out.append(self._validate_fact(raw_fact, valid_page_numbers, chunk_text))
            except FactValidationError as exc:
                logger.warning(
                    'fact_extractor.fact_rejected document_id=%s chunk=%d field_key=%r error=%s',
                    document.id, chunk_index,
                    raw_fact.get('field_key') if isinstance(raw_fact, dict) else raw_fact, exc,
                )
        return out

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
    def _validate_fact(raw_fact, valid_page_numbers, chunk_text=None):
        """`chunk_text`: the text the fact came from; a NAAC metric not printed in it is discarded."""
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
        if owner_role in {'institution_admin', 'iqac_coordinator', 'registrar', 'hod', 'hr_officer', 'lab_admin', 'placement_officer', 'faculty'}:
            owner_role = 'iqac_coordinator'
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
        notes = []  # what tagging left out and why (ExtractedFact.tagging_notes)

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
            **_validate_tagging(raw_fact, field_key, chunk_text, notes),
            'scope': _validate_scope(raw_fact.get('scope')),
            'derivation': _validate_calculation(raw_fact.get('calculation'), valid_page_numbers, notes),
            'tagging_notes': notes,
            # Not an ExtractedFact field: saved as FactAIQIFMapping rows by
            # ExtractionPipeline._persist_facts (apps/facts/aiqif_tagging.py decides which are used).
            'aiqif_mappings': _validate_aiqif_mappings(raw_fact.get('aiqif_indicators'), field_key, notes),
        }


def _clean_text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _clean_list(value):
    if not isinstance(value, list):
        return []
    return [item.strip()[:80] for item in value if isinstance(item, str) and item.strip()][:10]


def _validate_scope(raw):
    """What the value measures, as the extractor read it (an AI reading: verification/scope.py uses it only to
    tell facts apart, never to treat two facts as the same metric). Anything malformed is dropped."""
    if not isinstance(raw, dict):
        return {}
    scope = {'period': _clean_text(raw.get('period'), 120), 'population': _clean_text(raw.get('population'), 120),
             'includes': _clean_list(raw.get('includes')), 'excludes': _clean_list(raw.get('excludes'))}
    if not any(scope.values()):
        return {}
    return {**scope, 'source': 'extraction'}


def _validate_calculation(raw, valid_page_numbers, notes):
    """A calculated value's inputs, each cited on a page of this chunk -- the verification pipeline recomputes the
    arithmetic and grounds every input (verification/derived.py). A malformed calculation is dropped with a note,
    which leaves the value without a derivation (so it must be printed in its own quote to verify)."""
    if not isinstance(raw, dict):
        return {}
    operation = raw.get('operation')
    inputs = []
    for item in raw.get('inputs') or []:
        if not isinstance(item, dict) or not isinstance(item.get('value'), str) or not item['value'].strip():
            continue
        page = item.get('source_page')
        if page is not None and page not in valid_page_numbers:
            notes.append({'kind': 'calculation_dropped',
                          'detail': f'A calculation input cites page {page!r}, outside the text it came from.'})
            return {}
        inputs.append({'label': str(item.get('label') or '')[:120], 'value': item['value'].strip(),
                       'source_page': page or '', 'source_snippet': str(item.get('source_snippet') or '')[:1000]})
    if operation not in ('sum', 'difference', 'ratio', 'percentage') or len(inputs) < 2:
        notes.append({'kind': 'calculation_dropped',
                      'detail': 'The calculation had no valid operation or fewer than two inputs.'})
        return {}
    return {'operation': operation, 'inputs': inputs, 'includes': _clean_list(raw.get('includes')),
            'excludes': _clean_list(raw.get('excludes')), 'source': 'extraction'}


def _validate_tagging(raw_fact, field_key, chunk_text, notes):
    """fact_kind / naac_metric / profile_field, checked: a missing kind is guessed without the AI
    (aiqif_tagging.guess_kind), and a metric is kept only when it is printed in the chunk the fact came from."""
    from apps.facts.aiqif_tagging import guess_kind, metric_in_text, normalize_metric

    kind = raw_fact.get('fact_kind')
    if kind not in ExtractedFact.FactKind.values:
        kind = guess_kind(raw_fact)
        notes.append({'kind': 'fact_kind_guessed', 'detail': f'The AI gave no valid kind; classified as {kind}.'})
    raw_metric = raw_fact.get('naac_metric')
    metric = normalize_metric(raw_metric) if isinstance(raw_metric, str) else ''
    if metric and chunk_text is not None and not metric_in_text(metric, chunk_text):
        notes.append({'kind': 'naac_metric_discarded',
                      'detail': f'NAAC metric {metric} is not printed in the text this fact came from.'})
        metric = ''
    profile_field = raw_fact.get('profile_field') if kind == ExtractedFact.FactKind.PROFILE else ''
    if profile_field not in ExtractedFact.ProfileField.values:
        profile_field = ExtractedFact.ProfileField.OTHER if kind == ExtractedFact.FactKind.PROFILE else ''
    return {'fact_kind': kind, 'naac_metric': metric, 'profile_field': profile_field}


def _validate_aiqif_mappings(raw_mappings, field_key, notes=None):
    """The AI's indicator tags for one fact, as [{indicator_code, criterion,
    reason, confidence}], strongest first. A tag that isn't one of the 36
    AI-QIF indicators, or lacks a reason or a 0-1 confidence, is dropped on
    its own -- a bad tag never costs the fact itself, it just leaves it
    unmapped. Same indicator twice: the more confident one is kept. Each drop
    is also noted in `notes` (kept on the fact as `tagging_notes`)."""
    notes = notes if notes is not None else []
    if not isinstance(raw_mappings, list):
        if raw_mappings is not None:
            logger.warning('fact_extractor.aiqif_mappings_rejected field_key=%r value=%r', field_key, raw_mappings)
            notes.append({'kind': 'tag_dropped', 'detail': 'The AI-QIF tags were not a list, so none was used.'})
        return []

    by_code = {}
    for raw in raw_mappings:
        if not isinstance(raw, dict):
            continue
        code = raw.get('indicator')
        code = code.strip().upper() if isinstance(code, str) else None
        if code and not code.startswith('AIQIF-'):
            code = f'AIQIF-{code}'  # 'C4.1' -> 'AIQIF-C4.1'
        reason = raw.get('reason')
        confidence = raw.get('confidence')
        if (
            code not in AIQIF_INDICATORS
            or not isinstance(reason, str) or not reason.strip()
            or not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            logger.warning('fact_extractor.aiqif_mapping_rejected field_key=%r mapping=%r', field_key, raw)
            notes.append({'kind': 'tag_dropped', 'detail': f'AI-QIF tag {str(raw.get("indicator"))[:20]!r} dropped: '
                                                           'unknown indicator, or no reason / confidence.'})
            continue
        if code not in by_code or confidence > by_code[code]['confidence']:
            by_code[code] = {
                'indicator_code': code,
                'criterion': AIQIF_INDICATORS[code][0],
                'reason': reason.strip(),
                'confidence': float(confidence),
            }
    mappings = sorted(by_code.values(), key=lambda m: m['confidence'], reverse=True)
    return mappings[:MAX_AIQIF_MAPPINGS_PER_FACT]


def _merge_fact(facts_by_key, fact):
    """Duplicate facts across chunks are merged by field_key, keeping
    whichever has the strongest (highest-confidence) evidence rather than
    creating more than one database row for the same fact -- with the AI-QIF
    tags of both copies, so a tag is never lost to the merge."""
    key = fact['field_key'].strip().lower()
    existing = facts_by_key.get(key)
    if existing is None:
        facts_by_key[key] = fact
        return
    winner, other = (fact, existing) if fact['confidence_score'] > existing['confidence_score'] else (existing, fact)
    # Keep both copies' AI-QIF tags (the more confident tag per indicator) and a NAAC metric either copy found.
    tags = {m['indicator_code']: m for m in other.get('aiqif_mappings', [])}
    for m in winner.get('aiqif_mappings', []):
        if m['indicator_code'] not in tags or m['confidence'] >= tags[m['indicator_code']]['confidence']:
            tags[m['indicator_code']] = m
    winner['aiqif_mappings'] = sorted(tags.values(), key=lambda m: m['confidence'], reverse=True)[
        :MAX_AIQIF_MAPPINGS_PER_FACT]
    if not winner.get('naac_metric') and other.get('naac_metric'):
        winner['naac_metric'] = other['naac_metric']
    if fact.get('extraction_method') == 'vision' or existing.get('extraction_method') == 'vision':
        winner['extraction_method'] = 'vision'
    facts_by_key[key] = winner


class IdentityAuditFieldMapper(AuditFieldMapper):
    """`OpenAIFactExtractor` already returns facts shaped exactly like
    `ExtractedFact` creation kwargs (see module docstring above), so there's
    nothing left to map. Real, deterministic pass-through -- not a stub --
    paired with `OpenAIFactExtractor` as `ExtractionPipeline`'s default so
    facts it extracts actually reach the database instead of being dropped
    by `stub.NullAuditFieldMapper`."""

    def map_fields(self, document, facts):
        return facts
