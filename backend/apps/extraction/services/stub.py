"""Default service implementations -- active until real OCR/LLM/table-
extraction backends are wired in.

Per "no fake data": these do whatever real bookkeeping is honestly possible
without AI (e.g. classification just confirms what's already known from
upload) and return empty results everywhere real extraction would be
required, rather than inventing facts, gaps, or conflicts. This lets the
pipeline run end-to-end today -- a job reaches `completed` having found
zero facts, which is the truth, not a placeholder.
"""
from .base import (
    AuditFieldMapper,
    ConflictChecker,
    DocumentClassifier,
    FactExtractor,
    GapDetector,
    OCRProvider,
    PageReader,
)


class KnownMetadataClassifier(DocumentClassifier):
    """The document's type and format are already known from upload --
    nothing here needs AI, so this reports it rather than re-deriving it.

    No longer `ExtractionPipeline`'s default (see `openai_classifier.
    OpenAIDocumentClassifier`, which reads document content and validates
    an AI judgement instead of just echoing upload metadata) -- kept here
    as a trivial, network-free classifier for anything that still wants
    one (e.g. as an explicit fallback, or in a test)."""

    def classify(self, document):
        return {
            'document_type': document.document_type,
            'mime_type': document.mime_type,
            'ocr_required': document.ocr_required,
        }


class NullPageReader(PageReader):
    """No text-extraction backend is wired in yet.

    No longer `ExtractionPipeline`'s default (see `pdf_reader.
    PDFPageReader`) -- kept here as an explicit no-op for anything that
    still wants one (e.g. a test exercising the pipeline without PDF I/O)."""

    def read_pages(self, document, max_pages=None):
        return {'pages': [], 'page_count': None}


class NullOCRProvider(OCRProvider):
    """No OCR backend is wired in yet. Returning `None` (rather than `''`)
    is what lets `PDFPageReader` mark a page as still needing OCR instead
    of quietly treating it as confirmed-blank."""

    def extract_text(self, document, page_number):
        return None


class NullFactExtractor(FactExtractor):
    """No LLM/rules-based extraction backend is wired in yet.

    No longer `ExtractionPipeline`'s default (see `openai_fact_extractor.
    OpenAIFactExtractor`) -- kept here as an explicit no-op for anything
    that still wants one (e.g. a test exercising the pipeline without
    OpenAI calls)."""

    def extract_facts(self, document, pages):
        return []


class NullAuditFieldMapper(AuditFieldMapper):
    """No longer `ExtractionPipeline`'s default -- paired with
    `NullFactExtractor` above, this always received an empty list anyway.
    See `openai_fact_extractor.IdentityAuditFieldMapper`, the pipeline's
    current default, for why a real extractor needs a pass-through
    instead of this."""

    def map_fields(self, document, facts):
        return []


class NullGapDetector(GapDetector):
    """No longer `ExtractionPipeline`'s default (see `gap_detector.
    RuleBasedGapDetector`) -- kept here as an explicit no-op for anything
    that still wants one (e.g. a test exercising the pipeline without
    touching apps.gaps)."""

    def detect_gaps(self, document, mapped_facts):
        return []


class NullConflictChecker(ConflictChecker):
    """No longer `ExtractionPipeline`'s default (see `conflict_checker.
    OpenAIConflictChecker`) -- kept here as an explicit no-op for anything
    that still wants one (e.g. a test exercising the pipeline without
    OpenAI calls)."""

    def check_conflicts(self, document, mapped_facts):
        return []
