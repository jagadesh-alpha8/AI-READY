import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.documents.constants import normalize_checklist_type
from apps.documents.models import Document

from ..exceptions import ExtractionCancelled
from ..models import AIUsage, ExtractionJob
from ..usage import usage_scope
from . import stub
from .conflict_checker import OpenAIConflictChecker
from .document_analysis import DocumentAnalyzer
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
        field_mapper=None, gap_detector=None, conflict_checker=None, analyzer=None,
    ):
        # The default: one DocumentAnalyzer pairs the AI classifier and fact extractor so the first
        # request does both (services/document_analysis.py). Passing your own classifier or fact
        # extractor (e.g. a stub) runs them separately instead, as before -- still on one read.
        if analyzer is None and classifier is None and fact_extractor is None:
            analyzer = DocumentAnalyzer()
        self.analyzer = analyzer
        self.classifier = classifier or (analyzer.classifier if analyzer else OpenAIDocumentClassifier())
        self.page_reader = page_reader or PDFPageReader()
        self.fact_extractor = fact_extractor or (analyzer.fact_extractor if analyzer else OpenAIFactExtractor())
        self.field_mapper = field_mapper or IdentityAuditFieldMapper()
        self.gap_detector = gap_detector or RuleBasedGapDetector()
        self.conflict_checker = conflict_checker or OpenAIConflictChecker()

    def run(self, job):
        document = job.document
        logger.info(
            'extraction.pipeline.start job_id=%s document_id=%s', job.id, document.id,
        )

        self._advance(job, Step.CLASSIFYING_DOCUMENTS)
        # The document is read and parsed ONCE; classification and fact extraction both use these pages.
        pages = self.page_reader.read_pages(document)
        # Evidence-request assessment reuses this exact OCR/text read instead of running a second OCR pass.
        # The assessment is advisory; failure is recorded on the evidence submission and does not prevent
        # the document's ordinary extraction pipeline from continuing.
        try:
            from apps.facts.evidence_analysis import analyze_pending_document_submissions
            analyze_pending_document_submissions(document, pages, job=job)
        except Exception:
            logger.exception('extraction.pipeline.evidence_assessment_hook_failed document_id=%s', document.id)
        # Every AI call is recorded (tokens + cost) against this job and its stage -- see
        # apps.extraction.usage / AIUsage. With the analyzer, the first request classifies the document
        # AND extracts the first chunk's facts (stage document_analysis).
        first = None
        if self.analyzer is not None:
            self.analyzer.should_stop = lambda: _is_cancelled(job)
            with usage_scope(job=job):
                first = self.analyzer.analyze_first(document, pages)
            classification = first.classification
        else:
            with usage_scope(job=job, stage=AIUsage.Stage.CLASSIFICATION):
                classification = self.classifier.classify(document, pages=pages)
        document.processing_status = 'classified'
        update_fields = ['processing_status', *self._apply_classification(document, classification)]
        document.save(update_fields=[*update_fields, 'updated_at'])

        self._advance(job, Step.READING_PAGES)
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
        else:
            # Not a readable format: say so on the document (shown on the
            # Upload Data Pack page) instead of finishing silently with no facts.
            document.page_count = 0
            document.ocr_required = False
            document.ocr_warnings = [pages.get('format_note') or 'This file type cannot be read.']
            document.processing_status = 'unsupported_format'
            update_fields += ['page_count', 'ocr_required', 'ocr_warnings', 'processing_status']
        if update_fields:
            document.save(update_fields=[*update_fields, 'updated_at'])

        self._advance(job, Step.EXTRACTING_FACTS)
        # Fact extraction is many AI calls on a big document; let it check for
        # a Stop between calls instead of only at the next step.
        if first is not None:
            with usage_scope(job=job):
                raw_facts = self.analyzer.extract_rest(document, first)
        else:
            self.fact_extractor.should_stop = lambda: _is_cancelled(job)
            with usage_scope(job=job, stage=AIUsage.Stage.FACT_EXTRACTION):
                raw_facts = self.fact_extractor.extract_facts(document, pages)

        self._record_completeness(job, document, pages)

        self._advance(job, Step.MAPPING_AUDIT_FIELDS)
        mapped_facts = self.field_mapper.map_fields(document, raw_facts)
        facts_created = self._persist_facts(job, mapped_facts)
        self._ai_check_tags(job, document)

        self._advance(job, Step.DETECTING_GAPS)
        gaps = self.gap_detector.detect_gaps(document, mapped_facts)
        gaps_created = self._persist_gaps(job, gaps)

        self._advance(job, Step.CHECKING_CONFLICTS)
        with usage_scope(job=job, stage=AIUsage.Stage.CONFLICT_CHECK):
            conflicts = self.conflict_checker.check_conflicts(document, mapped_facts)
        conflicts_created = self._persist_conflicts(job, conflicts)
        # After conflicts are recorded, so a fact in an open conflict is left for a person.
        from apps.facts.auto_confirm import auto_confirm
        auto_confirmed = auto_confirm(document.extracted_facts.all())
        if auto_confirmed['confirmed']:
            logger.info('extraction.pipeline.auto_confirmed job_id=%s facts=%d skipped=%s', job.id,
                        len(auto_confirmed['confirmed']), auto_confirmed['skipped'])

        self._advance(job, Step.PREPARING_REVIEW_WORKSPACE)
        # Catch submissions made while this document was still extracting; the same pages are reused.
        try:
            from apps.facts.evidence_analysis import analyze_pending_document_submissions
            analyze_pending_document_submissions(document, pages, job=job)
        except Exception:
            logger.exception('extraction.pipeline.final_evidence_assessment_hook_failed document_id=%s', document.id)
        document.status = Document.Status.PROCESSED
        document.processed_at = timezone.now()
        update_fields = ['status', 'processed_at', 'updated_at']
        if job.completeness == ExtractionJob.Completeness.PARTIAL and document.processing_status != 'unsupported_format':
            document.processing_status = 'processed_partial'
            update_fields.append('processing_status')
        document.save(update_fields=update_fields)

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
        if _is_cancelled(job):
            raise ExtractionCancelled(f'Extraction job {job.id} was stopped by the user.')
        job.current_step = step
        job.progress_percentage = STEP_PROGRESS[step]
        job.save(update_fields=['current_step', 'progress_percentage', 'updated_at'])
        logger.info('extraction.pipeline.step job_id=%s step=%s', job.id, step)

    @staticmethod
    def _apply_classification(document, result):
        """Copy the AI classifier's verdict onto `document` and return the
        changed field names. Overwritten on every run, so reprocessing just
        refreshes it -- unless a person confirmed the category (below);
        `document_type` (the assigned type) is never touched.

        - A checklist category at/above AI_CLASSIFICATION_MIN_CONFIDENCE ->
          CLASSIFIED (counts toward the checklist).
        - A checklist category below it -> NEEDS_REVIEW.
        - null, or anything that isn't a checklist category -> UNCLASSIFIED.

        A result without a confidence (stub.KnownMetadataClassifier just
        echoes upload metadata) isn't an AI verdict -- nothing is saved.

        A category a person confirmed (POST /documents/{id}/confirm-category)
        is left exactly as they left it, like a reviewed fact in
        _persist_facts -- the new verdict is dropped, including its
        confidence and reasoning. Re-read from the database, so a
        confirmation made while this job was running still wins."""
        if not isinstance(result, dict) or 'confidence' not in result:
            return []
        document.refresh_from_db(fields=[
            'classification_status', 'ai_document_type', 'category_confirmed_at', 'category_confirmed_by',
        ])
        if document.category_manually_confirmed:
            logger.info(
                'extraction.pipeline.classification_kept document_id=%s confirmed_type=%s ai_type=%s',
                document.id, document.ai_document_type or None, result.get('document_type'),
            )
            return []

        Status = Document.ClassificationStatus
        category = normalize_checklist_type(result.get('document_type'))
        confidence = float(result['confidence'])
        if category is None:
            status = Status.UNCLASSIFIED
        elif confidence >= settings.AI_CLASSIFICATION_MIN_CONFIDENCE:
            status = Status.CLASSIFIED
        else:
            status = Status.NEEDS_REVIEW

        document.classification_status = status
        document.ai_document_type = category or ''
        document.ai_confidence = confidence
        document.ai_reasoning = (result.get('reasoning') or '').strip()
        document.classified_at = timezone.now()
        logger.info(
            'extraction.pipeline.classified document_id=%s assigned_type=%s ai_type=%s confidence=%.2f status=%s',
            document.id, document.document_type, category, confidence, status,
        )
        return ['classification_status', 'ai_document_type', 'ai_confidence', 'ai_reasoning', 'classified_at']

    def _record_completeness(self, job, document, pages):
        """Store how complete this extraction was, so a document whose chunks failed or were skipped (or
        whose pages could not be read) is never shown as fully processed (services/completeness.py)."""
        report = getattr(self.fact_extractor, 'report', None) or {}
        issues = list(report.get('issues', []))
        if not pages.get('format_supported', True):
            issues.append({'kind': 'unsupported_format',
                           'detail': pages.get('format_note') or 'This file type cannot be read; nothing was extracted.'})
        else:
            unreadable = list(pages.get('ocr_warnings') or [])
            if report and not report.get('chunks_total') and not unreadable:
                issues.append({'kind': 'no_text', 'detail': 'No readable text was found in the document, so no facts '
                                                            'could be extracted.'})
            if unreadable:
                issues.append({'kind': 'unreadable_pages',
                               'detail': f'{len(unreadable)} page(s) had no readable text, so nothing was extracted '
                                         f'from them.', 'pages': unreadable[:50]})
        job.extraction_warnings = issues
        job.chunks_total = report.get('chunks_total', 0)
        job.chunks_completed = report.get('chunks_completed', 0)
        job.completeness = ExtractionJob.Completeness.PARTIAL if issues else ExtractionJob.Completeness.COMPLETE
        job.save(update_fields=['extraction_warnings', 'chunks_total', 'chunks_completed', 'completeness',
                                'updated_at'])

    @staticmethod
    def _persist_facts(job, mapped_facts):
        """Save this run's facts for the document, one row per field_key.

        Reprocessing a document must not duplicate its facts (or the gaps,
        conflicts and recommendations that point at them), so a fact the
        document already has for the same field_key is reused:
        - still unreviewed (EXTRACTED): updated in place with the new value,
          keeping its id so everything linked to it stays linked;
        - already reviewed (confirmed/corrected/rejected/evidence requested):
          left exactly as the reviewer left it -- the new run's value for
          that field is dropped;
        - auto-confirmed (apps/facts/auto_confirm.py, never a person's decision):
          updated like an unreviewed fact and set back to EXTRACTED, so it is
          checked for auto-confirmation again with the new value.
        Facts an earlier run found that this run didn't are kept.
        AI-QIF tagging (apps/facts/aiqif_tagging.py) runs for every fact,
        reviewed ones included: a reviewed fact keeps its value and review,
        but its kind / NAAC metric / automatic tags are refreshed. A kind a
        Super Admin decided, and tags a person reviewed or added, are kept.
        Returns how many facts were created or updated."""
        from apps.facts.aiqif_tagging import Crosswalk, Precedents
        from apps.facts.auto_confirm import is_auto_confirmed
        from apps.facts.models import ExtractedFact

        crosswalk = Crosswalk()
        precedents = Precedents()  # earlier expert decisions, applied to this run's tags (aiqif_tagging rule 4)
        if not crosswalk.loaded:
            logger.error('extraction.pipeline.crosswalk_not_loaded job_id=%s: no AI-QIF tag is accepted '
                         'automatically until the NAAC -> AI-QIF crosswalk is imported', job.id)
        tagging_fields = ('fact_kind', 'naac_metric', 'profile_field', 'tagging_notes')

        def updatable(fact):
            return fact.status == ExtractedFact.Status.EXTRACTED or is_auto_confirmed(fact)

        existing = {}
        # Oldest first, so the newest unreviewed row wins a key -- unless a
        # reviewed row already holds it.
        for fact in ExtractedFact.objects.filter(document=job.document).select_related('reviewed_by').order_by('created_at'):
            key = fact.field_key.strip().lower()
            held = existing.get(key)
            if held is None or updatable(held):
                existing[key] = fact

        count = 0
        with transaction.atomic():
            for item in mapped_facts:
                fields = {name: value for name, value in item.items() if name != 'aiqif_mappings'}
                fact = existing.get(fields['field_key'].strip().lower())
                if fact is None:
                    fact = ExtractedFact.objects.create(
                        sprint=job.sprint, document=job.document, source_document=job.document, **fields,
                    )
                    existing[fact.field_key.strip().lower()] = fact
                elif updatable(fact):
                    for name, value in fields.items():
                        if name == 'fact_kind' and fact.kind_reviewed_by_id:
                            continue  # a Super Admin decided the kind
                        setattr(fact, name, value)
                    fact.source_document = job.document
                    if fact.status != ExtractedFact.Status.EXTRACTED:  # auto-confirmed: checked again below
                        fact.status, fact.reviewed_by, fact.reviewed_at = ExtractedFact.Status.EXTRACTED, None, None
                    fact.save()
                else:
                    # Reviewed: value and review untouched; only its tagging is refreshed.
                    for name in tagging_fields:
                        if name in fields and not (name == 'fact_kind' and fact.kind_reviewed_by_id):
                            setattr(fact, name, fields[name])
                    fact.save(update_fields=[*tagging_fields, 'updated_at'])
                    if 'aiqif_mappings' in item:
                        ExtractionPipeline._save_aiqif_mappings(fact, item['aiqif_mappings'], crosswalk, precedents)
                    continue
                if 'aiqif_mappings' in item:
                    ExtractionPipeline._save_aiqif_mappings(fact, item['aiqif_mappings'], crosswalk, precedents)
                count += 1
        return count

    @staticmethod
    def _ai_check_tags(job, document):
        """AI second opinion on the tags this document's facts still leave for an expert (aiqif_tagging rule 4b).
        Never fails the extraction: a failed check leaves the tags waiting."""
        if not settings.AIQIF_AI_CHECK_ENABLED:
            return
        from apps.facts.aiqif_tagging import ai_check_pending
        try:
            with usage_scope(job=job, stage=AIUsage.Stage.AIQIF_CHECK):
                result = ai_check_pending(list(document.extracted_facts.all()))
            if result['checked']:
                logger.info('extraction.pipeline.aiqif_check job_id=%s checked=%d accepted=%d', job.id,
                            result['checked'], result['accepted'])
        except Exception:
            logger.exception('extraction.pipeline.aiqif_check_failed job_id=%s', job.id)

    @staticmethod
    def _save_aiqif_mappings(fact, mappings, crosswalk=None, precedents=None):
        """Tag `fact` (apps/facts/aiqif_tagging.py: kind, crosswalk, AI suggestions, what is accepted
        automatically) and match a profile fact to the closed profile lists (apps/facts/profile_suggestion.py).
        The Raw CRI never reads tags; coverage counts only the ones aiqif_tagging.counting_q accepts."""
        from apps.facts.aiqif_tagging import apply_tags
        from apps.facts.models import ExtractedFact
        from apps.facts.profile_suggestion import match_code

        if not fact.fact_kind:
            from apps.facts.aiqif_tagging import guess_kind
            fact.fact_kind = guess_kind(fact)
            fact.save(update_fields=['fact_kind', 'updated_at'])
        code = match_code(fact) if fact.fact_kind == ExtractedFact.FactKind.PROFILE else ''
        if code != fact.profile_code:
            fact.profile_code = code
            fact.save(update_fields=['profile_code', 'updated_at'])
        apply_tags(fact, mappings, crosswalk, precedents)

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


def _is_cancelled(job):
    """The user pressed Stop for this job (see ExtractionCancelled)."""
    return ExtractionJob.objects.filter(id=job.id, status=ExtractionJob.Status.CANCELLED).exists()
