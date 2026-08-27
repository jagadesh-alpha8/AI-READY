import logging

from django.utils import timezone

from apps.documents.models import Document

from ..models import ExtractionJob
from . import stub
from .conflict_checker import OpenAIConflictChecker
from .gap_detector import RuleBasedGapDetector
from .openai_classifier import OpenAIDocumentClassifier
from .openai_fact_extractor import IdentityAuditFieldMapper, OpenAIFactExtractor
from .pdf_reader import PDFPageReader

logger = logging.getLogger(__name__)

Step = ExtractionJob.Step

STEP_ORDER = [
    Step.CLASSIFYING_DOCUMENTS,
    Step.READING_PAGES,
    Step.EXTRACTING_FACTS,
    Step.MAPPING_AUDIT_FIELDS,
    Step.DETECTING_GAPS,
    Step.CHECKING_CONFLICTS,
    Step.PREPARING_REVIEW_WORKSPACE,
]

#: Evenly-paced, real progress milestones tied to genuine stage completion
#: (not a fabricated "AI confidence" style estimate).
STEP_PROGRESS = {
    Step.CLASSIFYING_DOCUMENTS: 15,
    Step.READING_PAGES: 30,
    Step.EXTRACTING_FACTS: 45,
    Step.MAPPING_AUDIT_FIELDS: 60,
    Step.DETECTING_GAPS: 75,
    Step.CHECKING_CONFLICTS: 90,
    Step.PREPARING_REVIEW_WORKSPACE: 100,
}


class ExtractionPipeline:
    """Moves one document through the seven fixed processing stages.

    Every stage but one is real as of this task: OpenAI-backed
    classification and fact extraction, pdfplumber-backed PDF reading,
    deterministic per-document gap detection, and OpenAI-assisted semantic
    conflict detection -- see `openai_classifier.py`/`pdf_reader.py`/
    `openai_fact_extractor.py`/`gap_detector.py`/`conflict_checker.py`.
    `field_mapper` is a pass-through paired with the fact extractor's
    already-mapped output (`IdentityAuditFieldMapper`). Replacing any stage
    later means implementing its interface from `base.py` and passing it in
    here -- this orchestration, and the Celery retry/logging wrapper around
    it in `tasks.py`, doesn't need to change.
    """

    def __init__(
        self, *,
        classifier=None, page_reader=None, fact_extractor=None,
        field_mapper=None, gap_detector=None, conflict_checker=None,
    ):
        self.classifier = classifier or OpenAIDocumentClassifier()
        self.page_reader = page_reader or PDFPageReader()
        self.fact_extractor = fact_extractor or OpenAIFactExtractor()
        self.field_mapper = field_mapper or IdentityAuditFieldMapper()
        self.gap_detector = gap_detector or RuleBasedGapDetector()
        self.conflict_checker = conflict_checker or OpenAIConflictChecker()

    def run(self, job):
        document = job.document
        logger.info(
            'extraction.pipeline.start job_id=%s document_id=%s', job.id, document.id,
        )

        self._advance(job, Step.CLASSIFYING_DOCUMENTS)
        self.classifier.classify(document)
        document.processing_status = 'classified'
        document.save(update_fields=['processing_status', 'updated_at'])

        self._advance(job, Step.READING_PAGES)
        pages = self.page_reader.read_pages(document)
        update_fields = []
        if pages.get('page_count') is not None:
            document.page_count = pages['page_count']
            update_fields.append('page_count')
        if pages.get('format_supported', True):
            # Corrects the upload-time guess (every PDF is flagged
            # ocr_required=True purely by file extension, before any content
            # is read -- see apps.documents.constants.OCR_REQUIRED_EXTENSIONS)
            # with the real, content-based finding from PDFPageReader.
            document.ocr_required = pages.get('requires_ocr', False)
            document.ocr_warnings = pages.get('ocr_warnings', [])
            update_fields += ['ocr_required', 'ocr_warnings']
        if update_fields:
            document.save(update_fields=[*update_fields, 'updated_at'])

        self._advance(job, Step.EXTRACTING_FACTS)
        raw_facts = self.fact_extractor.extract_facts(document, pages)

        self._advance(job, Step.MAPPING_AUDIT_FIELDS)
        mapped_facts = self.field_mapper.map_fields(document, raw_facts)
        facts_created = self._persist_facts(job, mapped_facts)

        self._advance(job, Step.DETECTING_GAPS)
        gaps = self.gap_detector.detect_gaps(document, mapped_facts)
        gaps_created = self._persist_gaps(job, gaps)

        self._advance(job, Step.CHECKING_CONFLICTS)
        conflicts = self.conflict_checker.check_conflicts(document, mapped_facts)
        conflicts_created = self._persist_conflicts(job, conflicts)

        self._advance(job, Step.PREPARING_REVIEW_WORKSPACE)
        document.status = Document.Status.PROCESSED
        document.processed_at = timezone.now()
        document.save(update_fields=['status', 'processed_at', 'updated_at'])

        logger.info(
            'extraction.pipeline.complete job_id=%s facts=%d gaps=%d conflicts=%d',
            job.id, facts_created, gaps_created, conflicts_created,
        )
        return {
            'facts_extracted': facts_created,
            'gaps_detected': gaps_created,
            'conflicts_detected': conflicts_created,
        }

    def _advance(self, job, step):
        job.current_step = step
        job.progress_percentage = STEP_PROGRESS[step]
        job.save(update_fields=['current_step', 'progress_percentage', 'updated_at'])
        logger.info('extraction.pipeline.step job_id=%s step=%s', job.id, step)

    @staticmethod
    def _persist_facts(job, mapped_facts):
        from apps.facts.models import ExtractedFact

        count = 0
        for item in mapped_facts:
            ExtractedFact.objects.create(
                sprint=job.sprint, document=job.document, source_document=job.document, **item,
            )
            count += 1
        return count

    @staticmethod
    def _persist_gaps(job, gaps):
        """`gaps` are dicts shaped for apps.gaps.services.create_gap_if_new
        (gap_type/title/description/priority/dedup_filter/...), not raw
        GapItem kwargs -- routing through it (rather than a bare
        GapItem.objects.create()) means these gaps dedupe against each
        other, against a re-run of this same job, and against
        apps.gaps.services.generate_gaps_for_sprint's own end-of-sprint
        pass, all through one shared, already-tested idempotency check."""
        from apps.gaps.services import create_gap_if_new

        count = 0
        for item in gaps:
            if create_gap_if_new(job.sprint, **item):
                count += 1
        return count

    @staticmethod
    def _persist_conflicts(job, conflicts):
        """Conflicts are GapItem rows too (gap_type=CONFLICT, with the
        extra conflict_* fields populated) -- see gap_detector.py's
        docstring on why create_gap_if_new is the shared persistence path
        rather than a second, bespoke one here."""
        from apps.gaps.services import create_gap_if_new

        count = 0
        for item in conflicts:
            if create_gap_if_new(job.sprint, **item):
                count += 1
        return count
