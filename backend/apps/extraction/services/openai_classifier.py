"""Real, AI-backed `DocumentClassifier`.

Reads a short text sample of the document (via `PDFPageReader`) and asks
whichever AI provider is configured (see `ai_service.get_ai_service`) to
classify it against a strict JSON schema, then independently validates the
result before returning it -- the schema constrains *shape*, not values, so
`confidence` being in [0, 1] and every field's *type* being right is
re-checked here regardless of what the API enforced.

No longer `ExtractionPipeline`'s default is `stub.KnownMetadataClassifier`;
this is. See `services/__init__.py`/`pipeline.py`. The class name predates
multi-provider support -- despite it, this works with any configured provider.
"""
import logging

from django.conf import settings

from apps.documents.constants import CHECKLIST_TYPE_LABELS
from apps.documents.models import Document

from ..exceptions import PermanentExtractionError
from .ai_service import get_ai_service
from .base import DocumentClassifier
from .pdf_reader import PDFPageReader

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are classifying one institutional audit document (e.g. a NAAC SSR, an \
AQAR report, a faculty list) for a higher-education AI-readiness audit platform.

You will be given the document's filename, the type it was assigned at upload (and whether a \
person chose it or it was guessed from filename keywords), and a text sample from its first few \
pages (or a note that no text could be extracted).

`document_type` must be exactly one of these category ids, or null:
""" + '\n'.join(f'- {slug}: {label}' for slug, label in CHECKLIST_TYPE_LABELS.items()) + """

Rules -- follow these exactly:
- The document's text decides the category. Base every field only on the text you were given. \
Never invent, assume, or guess a value that isn't actually supported by the text.
- If the text doesn't contain enough information for a field, return null for that field. A \
null is the correct, honest answer when you don't know -- it is not a failure.
- If the text shows the document is none of the categories above, return null for \
`document_type` and say what it actually is in `reasoning`.
- The filename and the assigned type are hints, not ground truth: if the text supports a \
different category, return that one and explain why in `reasoning`. If there is no usable text, \
you may go by the filename or assigned type alone, but then `confidence` must be 0.5 or lower.
- `confidence` must be a number between 0 and 1 (inclusive) representing how sure you are of \
`document_type` specifically. 0 means you have no real basis for it; 1 means the text leaves no \
doubt.
- `reasoning` must briefly state what in the text (or its absence) led to your answer -- do not \
pad it with generic filler.

Respond only with the requested structured fields."""

CLASSIFICATION_SCHEMA = {
    'type': 'object',
    'properties': {
        'document_type': {
            'type': ['string', 'null'],
            'description': 'One of the listed category ids, e.g. "naac_ssr", or null if none fits or it is unclear.',
        },
        'document_title': {
            'type': ['string', 'null'],
            'description': "The document's own title as it appears in the text, or null.",
        },
        'reporting_year': {
            'type': ['string', 'null'],
            'description': 'The academic/reporting year the document covers (e.g. "2025-26"), or null.',
        },
        'institution_name': {
            'type': ['string', 'null'],
            'description': "The institution's name as it appears in the text, or null.",
        },
        'confidence': {
            'type': 'number',
            'description': 'Confidence in document_type, between 0 and 1.',
        },
        'reasoning': {
            'type': 'string',
            'description': 'Brief explanation grounded in the given text.',
        },
    },
    'required': ['document_type', 'document_title', 'reporting_year', 'institution_name', 'confidence', 'reasoning'],
    'additionalProperties': False,
}

_NULLABLE_STRING_FIELDS = ('document_type', 'document_title', 'reporting_year', 'institution_name')


class ClassificationValidationError(PermanentExtractionError):
    """OpenAI returned syntactically valid JSON matching the schema, but a
    field's *value* failed this app's own validation (e.g. confidence out
    of [0, 1], or a field that isn't a string despite the schema asking for
    one). Retrying the same input against the same model won't fix this."""


class OpenAIDocumentClassifier(DocumentClassifier):
    def __init__(self, *, openai_service=None, page_reader=None, sample_pages=None):
        # Lazy: no OpenAI client is constructed (and no API key is required)
        # until .classify() actually runs -- constructing this classifier,
        # and ExtractionPipeline() itself, must stay side-effect-free.
        self._openai_service = openai_service
        self._page_reader = page_reader or PDFPageReader()
        self.sample_pages = sample_pages if sample_pages is not None else settings.OPENAI_CLASSIFICATION_SAMPLE_PAGES

    def classify(self, document, pages=None):
        """`pages`: the document's already-read PageReader result -- its first `sample_pages` pages are
        used instead of reading the file again."""
        if pages is None:
            sample = self._page_reader.read_pages(document, max_pages=self.sample_pages)
        else:
            sample = {**pages, 'pages': list(pages.get('pages', []))[:self.sample_pages],
                      'pages_read': min(len(pages.get('pages', [])), self.sample_pages)}
        user_content = self._build_user_content(document, sample)

        service = self._openai_service or get_ai_service()
        result = service.extract_structured_data(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            response_schema=CLASSIFICATION_SCHEMA,
            schema_name='document_classification',
        )
        self._validate(result)

        logger.info(
            'extraction.classifier.result document_id=%s uploaded_type=%s ai_type=%s confidence=%s',
            document.id, document.document_type, result.get('document_type'), result.get('confidence'),
        )
        return result

    @staticmethod
    def _build_user_content(document, sample):
        source = {
            Document.TypeSource.UPLOADER: 'chosen by the uploader',
            Document.TypeSource.FILENAME: 'guessed from filename keywords only',
        }.get(document.document_type_source)
        assigned = f'{document.document_type} ({source})' if source and document.document_type else '(none)'
        lines = [
            f'Filename: {document.original_filename or "(unknown)"}',
            f'Assigned document type: {assigned}',
        ]
        if not sample.get('format_supported', True):
            lines.append(
                f'No extractable text is available: {sample.get("format_note", "unsupported file format.")}'
            )
        else:
            text_sample = '\n\n'.join(
                f'--- Page {page["page_number"]} ---\n{page["text"]}'
                for page in sample.get('pages', []) if page.get('text')
            )
            if text_sample:
                lines.append(f'Extracted text from the first {sample.get("pages_read", 0)} page(s):')
                lines.append(text_sample)
            else:
                lines.append(
                    'No extractable text was found in the sampled pages '
                    '(the document may be a scanned image with no OCR performed yet).'
                )
        return '\n'.join(lines)

    @staticmethod
    def validate(result):
        """Check a classification answer (also used for the combined analysis request)."""
        OpenAIDocumentClassifier._validate(result)

    @staticmethod
    def _validate(result):
        for field in _NULLABLE_STRING_FIELDS:
            value = result.get(field)
            if value is not None and not isinstance(value, str):
                raise ClassificationValidationError(f'{field} must be a string or null, got {value!r}.')

        confidence = result.get('confidence')
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ClassificationValidationError(f'confidence must be a number, got {confidence!r}.')
        if not (0 <= confidence <= 1):
            raise ClassificationValidationError(f'confidence must be between 0 and 1, got {confidence!r}.')

        reasoning = result.get('reasoning')
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise ClassificationValidationError(f'reasoning must be a non-empty string, got {reasoning!r}.')
