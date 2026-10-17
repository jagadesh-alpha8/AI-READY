"""One AI analysis per document text: classification and fact extraction share the first request.

Before: the classifier read a sample of the document and made its own AI request, then the pages
were read again and the fact extractor made one request per chunk. Now the pipeline reads the
document once and this analyzer works on those pages:

- first chunk  -> ONE request returning {classification, facts}   (usage stage: document_analysis)
- other chunks -> fact-only requests, exactly as before              (usage stage: fact_extraction)
- no text      -> a classification-only request (filename / assigned type only -- there is no text
                  to share), exactly as before                       (usage stage: classification)

Validation is the existing code's: the classification goes through OpenAIDocumentClassifier.validate
(category list / confidence rules are applied by the pipeline's _apply_classification, unchanged),
every fact through OpenAIFactExtractor._validate_fact (schema, data types, cited page, AI-QIF
indicator list). Usage is recorded once per API response by the AI clients; the combined call is
labelled `document_analysis` -- no token split between its classification and facts is invented.
"""
import logging
from dataclasses import dataclass, field

from apps.documents.models import Document

from ..exceptions import AIResponseError, ExtractionCancelled, PermanentExtractionError, RecoverableExtractionError
from ..models import AIUsage
from ..usage import usage_scope
from .ai_service import get_ai_service
from .openai_classifier import CLASSIFICATION_SCHEMA, ClassificationValidationError, OpenAIDocumentClassifier
from .openai_classifier import SYSTEM_PROMPT as CLASSIFICATION_PROMPT
from .openai_fact_extractor import FACT_ITEM_SCHEMA, FactValidationError, OpenAIFactExtractor, _merge_fact
from .openai_fact_extractor import SYSTEM_PROMPT as FACT_PROMPT

logger = logging.getLogger(__name__)

ANALYSIS_SCHEMA = {
    'type': 'object',
    'properties': {
        'classification': CLASSIFICATION_SCHEMA,
        'facts': {'type': 'array', 'items': FACT_ITEM_SCHEMA},
    },
    'required': ['classification', 'facts'],
    'additionalProperties': False,
}

SYSTEM_PROMPT = (
    'You will do two separate things with the same document text and return both in one response: '
    '`classification` (what the document is) and `facts` (structured facts it supports). Apply each part\'s '
    'rules only to that part.\n\n'
    '=== Part 1: classification ===\n' + CLASSIFICATION_PROMPT + '\n\n'
    '=== Part 2: facts ===\n' + FACT_PROMPT
)


@dataclass
class FirstPass:
    """What the first (combined) request produced, and what is left to extract."""
    classification: dict | None
    facts_by_key: dict = field(default_factory=dict)
    remaining: list = field(default_factory=list)   # [(chunk_index, chunk_pages)]
    chunk_count: int = 0


class DocumentAnalyzer:
    """Pairs the existing classifier and fact extractor around one shared read of the document."""

    def __init__(self, *, classifier=None, fact_extractor=None, ai_service=None):
        # Lazy, like the classifier/extractor: no AI client is built until a request is made.
        self.classifier = classifier or OpenAIDocumentClassifier()
        self.fact_extractor = fact_extractor or OpenAIFactExtractor()
        self._ai_service = ai_service
        self.should_stop = None  # set by ExtractionPipeline: True once the user pressed Stop
        self._service = None

    def _get_service(self):
        if self._service is None:
            self._service = self._ai_service or get_ai_service()
        return self._service

    def _check_stop(self, document):
        if self.should_stop is not None and self.should_stop():
            raise ExtractionCancelled(f'Analysis of document {document.id} was stopped by the user.')

    # -- step 1: classification (+ the first chunk's facts) ------------------------------------

    def analyze_first(self, document, pages):
        chunks = self.fact_extractor.chunks_for(document, pages)
        if not chunks:
            # No extractable text: nothing to share, so classification is asked on its own,
            # from the filename / assigned type, as before.
            with usage_scope(stage=AIUsage.Stage.CLASSIFICATION):
                return FirstPass(classification=self.classifier.classify(document, pages=pages))

        self._check_stop(document)
        first_index, first_pages = 1, chunks[0]
        with usage_scope(stage=AIUsage.Stage.DOCUMENT_ANALYSIS):
            result = self._get_service().extract_structured_data(
                system_prompt=SYSTEM_PROMPT,
                user_content=self._user_content(document, first_pages, first_index, len(chunks)),
                response_schema=ANALYSIS_SCHEMA,
                schema_name='document_analysis',
            )
        if not isinstance(result, dict):
            raise AIResponseError(f'Expected an object with classification and facts, got {result!r}.')
        classification = result.get('classification')
        if not isinstance(classification, dict):
            raise ClassificationValidationError(f'classification must be an object, got {classification!r}.')
        self.classifier.validate(classification)  # same checks as a classification-only answer
        logger.info(
            'extraction.analysis.classified document_id=%s uploaded_type=%s ai_type=%s confidence=%s',
            document.id, document.document_type, classification.get('document_type'), classification.get('confidence'),
        )

        first = FirstPass(classification=classification, chunk_count=len(chunks),
                          remaining=list(enumerate(chunks[1:], start=2)))
        raw_facts = result.get('facts')
        if isinstance(raw_facts, list):
            self._collect(document, raw_facts, first_pages, first_index, first.facts_by_key)
        else:
            # The classification is still good; only this chunk's facts are lost (like a failed chunk).
            logger.error('extraction.analysis.facts_missing document_id=%s value=%r', document.id, raw_facts)
        return first

    # -- step 2: the remaining chunks, facts only ------------------------------------------------

    def extract_rest(self, document, first):
        facts_by_key = first.facts_by_key
        for chunk_index, chunk_pages in first.remaining:
            self._check_stop(document)
            try:
                with usage_scope(stage=AIUsage.Stage.FACT_EXTRACTION):
                    raw_facts = self.fact_extractor._extract_chunk(
                        self._get_service(), document, chunk_pages, chunk_index, first.chunk_count)
            except RecoverableExtractionError:
                raise  # retry the whole job, as before
            except PermanentExtractionError as exc:
                logger.error('fact_extractor.chunk_failed document_id=%s chunk=%d/%d error=%s',
                             document.id, chunk_index, first.chunk_count, exc)
                continue
            self._collect(document, raw_facts, chunk_pages, chunk_index, facts_by_key)
        facts = list(facts_by_key.values())
        logger.info('extraction.analysis.complete document_id=%s chunk_count=%d fact_count=%d',
                    document.id, first.chunk_count, len(facts))
        return facts

    # -- helpers ---------------------------------------------------------------------------------

    def _collect(self, document, raw_facts, chunk_pages, chunk_index, facts_by_key):
        valid_page_numbers = {str(page['page_number']) for page in chunk_pages}
        for raw_fact in raw_facts:
            try:
                fact = self.fact_extractor._validate_fact(raw_fact, valid_page_numbers)
            except FactValidationError as exc:
                logger.warning('fact_extractor.fact_rejected document_id=%s chunk=%d field_key=%r error=%s',
                               document.id, chunk_index,
                               raw_fact.get('field_key') if isinstance(raw_fact, dict) else raw_fact, exc)
                continue
            _merge_fact(facts_by_key, fact)

    @staticmethod
    def _user_content(document, chunk_pages, chunk_index, chunk_count):
        source = {
            Document.TypeSource.UPLOADER: 'chosen by the uploader',
            Document.TypeSource.FILENAME: 'guessed from filename keywords only',
        }.get(document.document_type_source)
        assigned = f'{document.document_type} ({source})' if source and document.document_type else '(none)'
        text = '\n\n'.join(f'--- Page {page["page_number"]} ---\n{page["text"]}' for page in chunk_pages)
        page_numbers = ', '.join(str(page['page_number']) for page in chunk_pages)
        return '\n'.join([
            f'Filename: {document.original_filename or "(unknown)"}',
            f'Assigned document type: {assigned}',
            f'This is chunk {chunk_index} of {chunk_count} for this document, covering page(s): {page_numbers}. '
            'Classify the document from this text; extract facts only from this text.',
            'Text:',
            text,
        ])
