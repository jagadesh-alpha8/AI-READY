import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from apps.documents.constants import REQUIRED_DOCUMENT_TYPES, humanize_document_type
from apps.facts.models import ExtractedFact

from .models import GapItem

logger = logging.getLogger(__name__)


def generate_gaps_for_sprint(sprint):
    """Run every gap detector for a sprint and persist any newly-found gaps.

    Idempotent and safe to call repeatedly (e.g. after every extraction run,
    or any time the review workspace wants a fresh check): each detector
    checks for an existing *active* gap before creating a new one, so
    re-running never creates duplicates. `GapItem.Meta.constraints` backs
    this with real DB-level uniqueness as a second line of defense against
    a race between two concurrent calls.
    """
    created = []
    created += _detect_missing_documents(sprint)
    created += _detect_low_confidence_facts(sprint)
    created += _detect_unconfirmed_facts(sprint)
    created += _detect_conflicting_facts(sprint)
    created += _detect_stale_data(sprint)
    return created


def create_gap_if_new(
    sprint, *, gap_type, title, description, priority, dedup_filter, pillar='',
    source_fact=None, related_document=None,
    conflict_fact_b=None, conflict_value_a=None, conflict_value_b=None, conflict_confidence=None,
):
    """Create a GapItem unless an active one already matches `dedup_filter`
    for this sprint/gap_type -- the shared idempotency primitive every
    detector in this module (and, cross-app, apps.extraction.services.
    gap_detector/conflict_checker) creates gaps through, so "don't create a
    duplicate" is enforced in exactly one place rather than reimplemented
    per detector. `GapItem.Meta.constraints` backs this with real DB-level
    uniqueness as a second line of defense against a race between two
    concurrent calls (e.g. this sprint's per-document pipeline detectors
    and its own end-of-sprint generation pass both finding the same issue).
    """
    already_exists = GapItem.objects.filter(
        sprint=sprint, gap_type=gap_type, status__in=GapItem.ACTIVE_STATUSES, **dedup_filter,
    ).exists()
    if already_exists:
        return None

    try:
        gap = GapItem.objects.create(
            sprint=sprint, gap_type=gap_type, title=title, description=description,
            pillar=pillar, priority=priority, source_fact=source_fact, related_document=related_document,
            conflict_fact_b=conflict_fact_b, conflict_value_a=conflict_value_a,
            conflict_value_b=conflict_value_b, conflict_confidence=conflict_confidence,
        )
    except IntegrityError:
        # Lost a race with another concurrent generation run -- the other
        # call already created this exact gap, which is the correct outcome.
        logger.info(
            'gaps.generate.duplicate_avoided sprint_id=%s gap_type=%s title=%s', sprint.id, gap_type, title,
        )
        return None

    logger.info('gaps.generate.created sprint_id=%s gap_id=%s gap_type=%s', sprint.id, gap.id, gap_type)
    return gap


def _detect_missing_documents(sprint):
    uploaded_types = set(sprint.documents.values_list('document_type', flat=True))
    missing_types = REQUIRED_DOCUMENT_TYPES - uploaded_types

    created = []
    for document_type in sorted(missing_types):
        label = humanize_document_type(document_type)
        title = f'Missing {label}'
        gap = create_gap_if_new(
            sprint,
            gap_type=GapItem.GapType.MISSING_DOCUMENT,
            title=title,
            description=f'{label} has not been uploaded yet and is required for a verified CRI baseline.',
            priority=GapItem.Priority.BLOCKING,
            dedup_filter={'title': title, 'source_fact__isnull': True, 'related_document__isnull': True},
        )
        if gap:
            created.append(gap)
    return created


def _detect_low_confidence_facts(sprint):
    facts = sprint.facts.filter(
        status=ExtractedFact.Status.EXTRACTED,
        confidence_score__lt=settings.GAP_LOW_CONFIDENCE_THRESHOLD,
    )
    created = []
    for fact in facts:
        priority = (
            GapItem.Priority.HIGH
            if fact.confidence_score < settings.GAP_VERY_LOW_CONFIDENCE_THRESHOLD
            else GapItem.Priority.MEDIUM
        )
        gap = create_gap_if_new(
            sprint,
            gap_type=GapItem.GapType.LOW_CONFIDENCE,
            title=f'Low-confidence extraction: {fact.field_name or fact.field_key}',
            description=(
                f'"{fact.field_key}" was extracted with only {fact.confidence_score * 100:.0f}% '
                f'confidence from {fact.source_snippet or "the source document"}. Please verify.'
            ),
            pillar=fact.pillar,
            priority=priority,
            dedup_filter={'source_fact': fact},
            source_fact=fact,
        )
        if gap:
            created.append(gap)
    return created


def _detect_unconfirmed_facts(sprint):
    facts = sprint.facts.filter(
        status=ExtractedFact.Status.EXTRACTED,
        confidence_score__gte=settings.GAP_LOW_CONFIDENCE_THRESHOLD,
    )
    created = []
    for fact in facts:
        gap = create_gap_if_new(
            sprint,
            gap_type=GapItem.GapType.UNCONFIRMED_FACT,
            title=f'Needs confirmation: {fact.field_name or fact.field_key}',
            description=f'"{fact.field_key}" has been extracted but not yet confirmed by an owner.',
            pillar=fact.pillar,
            priority=GapItem.Priority.MEDIUM,
            dedup_filter={'source_fact': fact},
            source_fact=fact,
        )
        if gap:
            created.append(gap)
    return created


def _detect_conflicting_facts(sprint):
    facts = sprint.facts.exclude(status=ExtractedFact.Status.REJECTED).order_by('field_key')
    by_field = {}
    for fact in facts:
        by_field.setdefault(fact.field_key, []).append(fact)

    created = []
    for field_key, group in by_field.items():
        distinct_values = {_hashable_value(fact.value) for fact in group}
        if len(distinct_values) <= 1:
            continue

        representative = min(group, key=lambda fact: fact.confidence_score)
        title = f'Conflicting values for {representative.field_name or field_key}'
        values_summary = ', '.join(json.dumps(fact.value) for fact in group)
        gap = create_gap_if_new(
            sprint,
            gap_type=GapItem.GapType.CONFLICT,
            title=title,
            # Deduped by title (stable per field_key), not by the
            # representative fact -- which document ends up "most suspect"
            # can change as more facts arrive, but the conflict itself is
            # the same one until it's actually resolved.
            dedup_filter={'title': title},
            description=f'Documents report different values for "{field_key}": {values_summary}.',
            pillar=representative.pillar,
            priority=GapItem.Priority.HIGH,
            source_fact=representative,
        )
        if gap:
            created.append(gap)
    return created


def _detect_stale_data(sprint):
    cutoff = timezone.now() - timedelta(days=settings.GAP_STALE_DATA_DAYS)
    documents = sprint.documents.filter(uploaded_at__lt=cutoff)

    created = []
    for document in documents:
        label = humanize_document_type(document.document_type)
        gap = create_gap_if_new(
            sprint,
            gap_type=GapItem.GapType.STALE_DATA,
            title=f'Stale data: {document.original_filename or label}',
            description=(
                f'{document.original_filename or label} was uploaded more than '
                f'{settings.GAP_STALE_DATA_DAYS} days ago and may no longer reflect current data.'
            ),
            priority=GapItem.Priority.MEDIUM,
            dedup_filter={'related_document': document, 'source_fact__isnull': True},
            related_document=document,
        )
        if gap:
            created.append(gap)
    return created


def _hashable_value(value):
    return json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
