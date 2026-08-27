"""Real, deterministic `GapDetector` -- no AI involved.

Per this task's own instruction ("do not replace deterministic business
rules with AI unnecessarily"), and because none of these checks require
semantic judgement, gap detection stays 100% rule-based; AI is reserved for
`conflict_checker.py`, where "do these two pieces of evidence actually
disagree" genuinely does need interpretation.

Deliberately does *not* detect `missing_document`: that's a sprint-wide
question ("which required document types has this sprint not uploaded at
all yet"), not answerable by looking at one document's own facts, and
checking it mid-processing (while sibling documents in the same sprint may
still be uploading) would be actively misleading. `apps.gaps.services.
generate_gaps_for_sprint` already covers it correctly, triggered once every
job in the sprint's current batch has finished (see `tasks.py:
_advance_sprint_if_all_jobs_done`).

Returns plain dicts shaped for `apps.gaps.services.create_gap_if_new`
(`pipeline.py: _persist_gaps` calls that, not a raw `GapItem.objects.
create()`) -- the same dedup-safe primitive the sprint-wide pass uses, so
whichever of the two notices a given fact/document first "wins" and the
other is a no-op, never a duplicate row.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.documents.constants import humanize_document_type
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem

from .base import GapDetector

logger = logging.getLogger(__name__)


class RuleBasedGapDetector(GapDetector):
    def detect_gaps(self, document, mapped_facts):
        gaps = []
        gaps += self._fact_gaps(document)
        gaps += self._stale_document_gap(document)
        logger.info(
            'gap_detector.complete document_id=%s stage=detecting_gaps candidate_count=%d',
            document.id, len(gaps),
        )
        return gaps

    @staticmethod
    def _fact_gaps(document):
        """One gap per fact this pipeline run just extracted from
        `document`: low_confidence if it's below the configured threshold,
        unconfirmed_fact otherwise (an extracted-but-not-yet-owner-reviewed
        fact is itself a gap in the review workflow, not just a value)."""
        gaps = []
        for fact in document.extracted_facts.filter(status=ExtractedFact.Status.EXTRACTED):
            if fact.confidence_score < settings.GAP_LOW_CONFIDENCE_THRESHOLD:
                priority = (
                    GapItem.Priority.HIGH
                    if fact.confidence_score < settings.GAP_VERY_LOW_CONFIDENCE_THRESHOLD
                    else GapItem.Priority.MEDIUM
                )
                gaps.append({
                    'gap_type': GapItem.GapType.LOW_CONFIDENCE,
                    'title': f'Low-confidence extraction: {fact.field_name or fact.field_key}',
                    'description': (
                        f'"{fact.field_key}" was extracted with only {fact.confidence_score * 100:.0f}% '
                        f'confidence from {fact.source_snippet or "the source document"}. Please verify.'
                    ),
                    'pillar': fact.pillar,
                    'priority': priority,
                    'dedup_filter': {'source_fact': fact},
                    'source_fact': fact,
                })
            else:
                gaps.append({
                    'gap_type': GapItem.GapType.UNCONFIRMED_FACT,
                    'title': f'Needs confirmation: {fact.field_name or fact.field_key}',
                    'description': f'"{fact.field_key}" has been extracted but not yet confirmed by an owner.',
                    'pillar': fact.pillar,
                    'priority': GapItem.Priority.MEDIUM,
                    'dedup_filter': {'source_fact': fact},
                    'source_fact': fact,
                })
        return gaps

    @staticmethod
    def _stale_document_gap(document):
        if document.uploaded_at is None:
            return []
        cutoff = timezone.now() - timedelta(days=settings.GAP_STALE_DATA_DAYS)
        if document.uploaded_at >= cutoff:
            return []

        label = humanize_document_type(document.document_type)
        return [{
            'gap_type': GapItem.GapType.STALE_DATA,
            'title': f'Stale data: {document.original_filename or label}',
            'description': (
                f'{document.original_filename or label} was uploaded more than '
                f'{settings.GAP_STALE_DATA_DAYS} days ago and may no longer reflect current data.'
            ),
            'priority': GapItem.Priority.MEDIUM,
            'dedup_filter': {'related_document': document, 'source_fact__isnull': True},
            'related_document': document,
        }]
