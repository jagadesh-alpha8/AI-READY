import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from apps.documents.constants import REQUIRED_DOCUMENT_TYPES, humanize_document_type
from apps.facts.models import EvidenceRequest, ExtractedFact

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
    # A document whose category a person confirmed counts as that type too (an import may store it as
    # 'unclassified' until then) -- so a gap closed by that review is not raised again.
    for confirmed in (sprint.documents.filter(category_confirmed_at__isnull=False)
                      .exclude(ai_document_type='').values_list('ai_document_type', flat=True)):
        uploaded_types |= document_type_variants(confirmed)
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
    """A conflict per field whose comparable facts disagree (apps/facts/verification/conflicts.py): values compared
    after removing printing differences, and only between facts of the same period / population / unit /
    categories; an earlier version of the same file does not count as a second source."""
    from apps.facts.verification import conflicts as rules
    facts = (sprint.facts.exclude(status=ExtractedFact.Status.REJECTED)
             .select_related('source_document', 'document').order_by('field_key'))
    by_field = {}
    for fact in facts:
        by_field.setdefault(fact.field_key, []).append(fact)

    created = []
    for field_key, group in by_field.items():
        disagreeing = rules.disagreements(group)
        if not disagreeing:
            continue
        group = disagreeing[0]

        representative = min(group, key=lambda fact: fact.confidence_score)
        title = f'Conflicting values for {representative.field_name or field_key}'
        values_summary = '; '.join(f'{r["value"]!r} ({rules._where(r)})'
                                   for r in (rules.candidate_row(f) for f in group))
        gap = create_gap_if_new(
            sprint,
            gap_type=GapItem.GapType.CONFLICT,
            title=title,
            # Deduped by title (stable per field_key), not by the
            # representative fact -- which document ends up "most suspect"
            # can change as more facts arrive, but the conflict itself is
            # the same one until it's actually resolved.
            dedup_filter={'title': title},
            description=f'Sources report different values for "{field_key}": {values_summary}.',
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
        if newer_reviewed_document(document) is not None:
            continue  # superseded by a newer document a person reviewed
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


#: Fact statuses that count as reviewed evidence -- the same two the CRI
#: engine scores (apps.scoring.services.cri_engine._EVIDENCE_STATUSES).
CONFIRMING_FACT_STATUSES = [ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.CORRECTED]


def resolve_unconfirmed_fact_gap(fact, *, user=None):
    """Close the fact's own open "unconfirmed fact" gap once it has been
    Confirmed or Corrected, so that gap's -3 CRI penalty goes away with no
    separate Resolve click. Returns how many gaps were closed.

    Deliberately narrow: only gap_type=UNCONFIRMED_FACT tied to this fact.
    Genuine gaps -- conflicts, missing documents, low-confidence flags and any
    other deficiency -- stay open until someone deals with them, and a
    Rejected fact closes nothing.
    """
    if fact.status not in CONFIRMING_FACT_STATUSES:
        return 0
    return GapItem.objects.filter(
        source_fact=fact,
        gap_type=GapItem.GapType.UNCONFIRMED_FACT,
        status__in=GapItem.ACTIVE_STATUSES,
    ).update(
        status=GapItem.Status.RESOLVED,
        resolution=f'Automatically resolved: fact {fact.get_status_display().lower()} by a reviewer.',
        resolved_by=user,
        resolved_at=timezone.now(),
        updated_at=timezone.now(),
    )


# -- low-confidence gaps and evidence requests -----------------------------------------------------
# A low-confidence gap says "this extracted value is doubtful". It is closed by a reviewer's
# decision on evidence (apps.facts.evidence_requests), never by an upload, an extraction or a
# bare Resolve click.

def resolve_low_confidence_gap_for_evidence(fact, *, request, link, user):
    """Close the fact's open low-confidence gap after a reviewer accepted evidence for it (accept, or
    accept with correction). Called only from apps.facts.evidence_requests._accept, inside its
    transaction. The resolution names the accepted document, page, decision and reviewer."""
    from .models import GapEvent
    document = link.document
    citation = (document.original_filename or document.title or str(document.id)) if document else \
        f'text submission ({link.source_context[:160]})'
    if fact.source_page:
        citation += f', page {fact.source_page}'
    decision = 'accepted with correction' if fact.status == ExtractedFact.Status.CORRECTED else 'accepted'
    reviewer = user.get_full_name() or user.email
    gaps = GapItem.objects.filter(
        source_fact=fact, gap_type=GapItem.GapType.LOW_CONFIDENCE, status__in=GapItem.ACTIVE_STATUSES,
    )
    resolved = []
    for gap in gaps:
        resolution = (f'Resolved by evidence request {request.id}: evidence "{citation}" {decision} '
                      f'by {reviewer}.')
        _close(gap, GapItem.Status.RESOLVED, user, resolution, GapEvent.Action.AUTO_RESOLVED)
        resolved.append(gap.id)
    return resolved


def resolve_evidence_gaps(fact, *, request, link, user):
    """Accepting evidence closes only the exact fact's unconfirmed and low-confidence gaps.

    Conflicts, replacement gaps and unrelated gaps need their own workflow and remain active.
    Every resolution gets the normal append-only GapEvent audit record.
    """
    from .models import GapEvent
    resolved = []
    for gap in GapItem.objects.filter(
        source_fact=fact, gap_type=GapItem.GapType.UNCONFIRMED_FACT, status__in=GapItem.ACTIVE_STATUSES,
    ):
        if fact.status not in CONFIRMING_FACT_STATUSES:
            continue
        reason = f'Fact confirmed from evidence request {request.id} by {user.get_full_name() or user.email}.'
        _close(gap, GapItem.Status.RESOLVED, user, reason, GapEvent.Action.AUTO_RESOLVED)
        resolved.append(gap.id)
    resolved.extend(resolve_low_confidence_gap_for_evidence(fact, request=request, link=link, user=user))
    return resolved


def fact_has_reviewed_citation(fact):
    """Confirmed/corrected by a reviewer and citing a document with a page or snippet."""
    return (fact.status in CONFIRMING_FACT_STATUSES and fact.source_document_id is not None
            and bool((fact.source_page or '').strip() or (fact.source_snippet or '').strip()))


def _has_open_request(fact, has_open_request):
    if has_open_request is None:
        return fact.evidence_requests.filter(status__in=EvidenceRequest.UNRESOLVED).exists()
    return has_open_request


def low_confidence_resolve_block(gap, has_open_request=None):
    """Why the generic Resolve action may not close this gap, or '' when it may (with an explanation).
    Only low-confidence gaps tied to a fact are restricted; every other gap type is unchanged.
    `has_open_request` may be passed when the caller already knows it (the list serializer)."""
    fact = gap.source_fact
    if gap.gap_type != GapItem.GapType.LOW_CONFIDENCE or fact is None:
        return ''
    if _has_open_request(fact, has_open_request):
        return ('This fact has an open evidence request. The gap closes when a reviewer accepts the evidence '
                'on that request.')
    if not fact_has_reviewed_citation(fact):
        return ('This low-confidence value has not been verified. Review the fact (confirm or correct it with '
                'a citation) or request evidence for it before resolving the gap.')
    return ''


def low_confidence_close_block(gap, has_open_request=None):
    """Why Skip / Mark unavailable may not close this gap now: not while an evidence request on its fact
    is still waiting for a decision (decide or withdraw the request first)."""
    fact = gap.source_fact
    if gap.gap_type != GapItem.GapType.LOW_CONFIDENCE or fact is None:
        return ''
    if _has_open_request(fact, has_open_request):
        return ('This fact has an open evidence request. Decide on it (or withdraw it) in Evidence Requests '
                'before closing the gap another way.')
    return ''


# -- gaps are settled through the underlying issue --------------------------------------------------
# Every gap type closes when the thing it is about is fixed (automatically, from the fact / document
# review that fixes it), and the generic Resolve is refused until then. Skip / Mark unavailable stay
# available -- for a gap that genuinely won't be fixed -- but always need a written reason.

#: The two names the upload checklist and the gap detector use for the same document types.
_TYPE_ALIASES = {'aqar': 'aqar_report', 'faculty_master_list': 'faculty_master'}


def document_type_variants(document_type):
    """Every name a document type goes by (e.g. {'aqar', 'aqar_report'})."""
    t = (document_type or '').strip().lower()
    if not t:
        return set()
    variants = {t}
    for a, b in _TYPE_ALIASES.items():
        if t in (a, b):
            variants |= {a, b}
    return variants


def missing_document_type(gap):
    """The required document type a "Missing <label>" gap is about, or ''."""
    for t in REQUIRED_DOCUMENT_TYPES:
        if gap.title == f'Missing {humanize_document_type(t)}':
            return t
    return ''


def _reviewed(qs):
    """Documents a person has reviewed: their category confirmed in Upload Data Pack."""
    return qs.filter(category_confirmed_at__isnull=False)


def _of_type(qs, document_type):
    from django.db.models import Q
    variants = document_type_variants(document_type)
    return qs.filter(Q(document_type__in=variants) | Q(ai_document_type__in=variants))


def reviewed_document_of_type(sprint, document_type):
    return _reviewed(_of_type(sprint.documents.all(), document_type)).order_by('-category_confirmed_at').first()


def newer_reviewed_document(document):
    """A reviewed document of the same type uploaded after `document` (its updated evidence), or None."""
    if document.uploaded_at is None:
        return None
    types = (document_type_variants(document.document_type)
             | document_type_variants(document.ai_document_type)) - {'unclassified', 'other'}
    if not types:
        return None
    from django.db.models import Q
    qs = document.sprint.documents.exclude(pk=document.pk).filter(uploaded_at__gt=document.uploaded_at)
    return _reviewed(qs.filter(Q(document_type__in=types) | Q(ai_document_type__in=types))).first()


def conflict_facts(gap):
    """The facts a conflict compares: its two sides when recorded, else every fact of that field."""
    if gap.source_fact_id is None:
        return []
    if gap.conflict_fact_b_id:
        return [f for f in (gap.source_fact, gap.conflict_fact_b) if f is not None]
    return list(ExtractedFact.objects.filter(sprint_id=gap.sprint_id, field_key=gap.source_fact.field_key))


def conflict_reconciled(gap):
    """True once the conflicting values agree: every comparable fact still in play (not rejected, not on a
    superseded version) states the same value once printing differences are removed ("1,234" == 1234)."""
    from apps.facts.verification import conflicts as rules
    return not rules.disagreements(conflict_facts(gap))


def _event(gap, action, user, note='', **data):
    from .models import GapEvent
    return GapEvent.objects.create(gap=gap, action=action, user=user, note=note or '', data=data)


def _close(gap, status, user, resolution, action):
    now = timezone.now()
    gap.status, gap.resolution, gap.resolved_by, gap.resolved_at = status, resolution, user, now
    gap.save(update_fields=['status', 'resolution', 'resolved_by', 'resolved_at', 'updated_at'])
    _event(gap, action, user, resolution)


def resolve_block(gap, has_open_request=None):
    """Why the generic Resolve may not close this gap now, or '' when it may."""
    from .models import GapItem as G
    fact = gap.source_fact
    if gap.status == G.Status.NEEDS_REPLACEMENT:
        if fact and ExtractedFact.objects.filter(sprint_id=gap.sprint_id, field_key=fact.field_key,
                                                 status__in=CONFIRMING_FACT_STATUSES).exists():
            return ''
        return ('The fact was rejected. Confirm or correct a replacement value for this field (that closes this '
                'gap), or skip / mark it unavailable with a reason.')
    if gap.gap_type == G.GapType.LOW_CONFIDENCE:
        return low_confidence_resolve_block(gap, has_open_request=has_open_request)
    if gap.gap_type == G.GapType.UNCONFIRMED_FACT and fact is not None:
        if fact.status in CONFIRMING_FACT_STATUSES:
            return ''
        return 'Confirm or correct the fact; that closes this gap.'
    if gap.gap_type == G.GapType.CONFLICT and fact is not None:
        if conflict_reconciled(gap):
            return ''
        return ('The values still disagree. Correct or reject the facts until they agree (that closes this gap), '
                'or close it as unresolved with a reason (skip / mark unavailable).')
    if gap.gap_type == G.GapType.MISSING_DOCUMENT:
        t = missing_document_type(gap)
        if t and reviewed_document_of_type(gap.sprint, t) is None:
            return (f'Upload the {humanize_document_type(t)} and confirm its category in Upload Data Pack; '
                    'that closes this gap.')
        return ''
    if gap.gap_type == G.GapType.STALE_DATA and gap.related_document_id:
        if newer_reviewed_document(gap.related_document) is None:
            return ('Upload a newer version of this document and confirm its category in Upload Data Pack; '
                    'that closes this gap.')
        return ''
    return ''


def close_block(gap, resolution, has_open_request=None):
    """Why Skip / Mark unavailable may not close this gap now ('' = may). A reason is always required."""
    from .models import GapItem as G
    if gap.gap_type == G.GapType.LOW_CONFIDENCE:
        block = low_confidence_close_block(gap, has_open_request=has_open_request)
        if block:
            return block
    if not (resolution or '').strip():
        if gap.gap_type == G.GapType.CONFLICT:
            return 'Say why the conflict is being closed unresolved.'
        return 'Explain why this gap is being closed without fixing it.'
    return ''


# -- hooks: the review that fixes the issue also closes its gaps --------------------------------------

def after_fact_review(fact, *, user, reason=''):
    """Called after a fact is confirmed, corrected or rejected (fact views and evidence decisions).

    - confirmed / corrected: its "needs confirmation" gap closes (resolve_unconfirmed_fact_gap), and so
      does any "needs replacement" gap of the same field (this is the replacement);
    - rejected: its "needs confirmation" and low-confidence gaps become "needs replacement", with the
      rejection reason -- still active, so the gap and its CRI penalty stay until a replacement;
    - either way: a conflict on this field whose values now agree closes.
    Returns the number of gaps changed."""
    from .models import GapEvent
    from .models import GapItem as G
    changed = 0
    if fact.status in CONFIRMING_FACT_STATUSES:
        own = list(G.objects.filter(source_fact=fact, gap_type=G.GapType.UNCONFIRMED_FACT,
                                    status__in=G.ACTIVE_STATUSES))
        changed += resolve_unconfirmed_fact_gap(fact, user=user)
        for gap in own:
            _event(gap, GapEvent.Action.AUTO_RESOLVED, user, f'Fact {fact.get_status_display().lower()}.')
        for gap in G.objects.filter(sprint_id=fact.sprint_id, source_fact__field_key=fact.field_key,
                                    status=G.Status.NEEDS_REPLACEMENT).exclude(gap_type=G.GapType.CONFLICT):
            _close(gap, G.Status.RESOLVED, user,
                   f'Replaced: {fact.field_name or fact.field_key} {fact.get_status_display().lower()} '
                   f'as {fact.value!r}.', GapEvent.Action.AUTO_RESOLVED)
            changed += 1
    elif fact.status == ExtractedFact.Status.REJECTED:
        for gap in G.objects.filter(source_fact=fact, status__in=[G.Status.OPEN, G.Status.IN_PROGRESS],
                                    gap_type__in=[G.GapType.UNCONFIRMED_FACT, G.GapType.LOW_CONFIDENCE]):
            gap.status = G.Status.NEEDS_REPLACEMENT
            gap.save(update_fields=['status', 'updated_at'])
            _event(gap, GapEvent.Action.NEEDS_REPLACEMENT, user, reason)
            changed += 1
    from apps.facts.verification.conflicts import refresh as refresh_conflict
    for gap in G.objects.filter(sprint_id=fact.sprint_id, gap_type=G.GapType.CONFLICT,
                                status__in=G.ACTIVE_STATUSES, source_fact__field_key=fact.field_key):
        refresh_conflict(gap, user=user)  # never leave the old values in its description
        if conflict_reconciled(gap):
            _close(gap, G.Status.RESOLVED, user,
                   f'Reconciled: the values of {fact.field_name or fact.field_key} now agree.',
                   GapEvent.Action.AUTO_RESOLVED)
            changed += 1
    # Evidence uploaded from a low-confidence gap: the reviewed fact from that document settles it.
    from .evidence_upload import close_low_confidence_from_evidence
    changed += close_low_confidence_from_evidence(fact, user)
    return changed


def after_document_review(document, *, user):
    """Called when a person confirms a document's category: a missing-document gap for its type closes,
    and stale-data gaps on older documents of the same type close (this is their updated evidence)."""
    from .models import GapEvent
    from .models import GapItem as G
    changed = 0
    if document.category_confirmed_at is None:
        return 0
    name = document.original_filename or document.title or 'the document'
    for gap in G.objects.filter(sprint_id=document.sprint_id, gap_type=G.GapType.MISSING_DOCUMENT,
                                status__in=G.ACTIVE_STATUSES):
        t = missing_document_type(gap)
        if t and reviewed_document_of_type(document.sprint, t) is not None:
            _close(gap, G.Status.RESOLVED, user, f'Provided: {name}, reviewed by '
                   f'{user.get_full_name() or user.email}.', GapEvent.Action.AUTO_RESOLVED)
            changed += 1
    for gap in G.objects.filter(sprint_id=document.sprint_id, gap_type=G.GapType.STALE_DATA,
                                status__in=G.ACTIVE_STATUSES, related_document__isnull=False):
        if newer_reviewed_document(gap.related_document) is not None:
            _close(gap, G.Status.RESOLVED, user, f'Updated evidence: {name}, reviewed by '
                   f'{user.get_full_name() or user.email}.', GapEvent.Action.AUTO_RESOLVED)
            changed += 1
    return changed


class ConflictChoiceError(Exception):
    pass


def choose_conflict_value(gap, user, fact_id, reason=''):
    """Settle a conflict by choosing the correct value: the chosen fact is confirmed (unless already confirmed
    or corrected), every competing fact with a different value is rejected with the decision as its reason, and
    the conflict closes. Facts with the same value as the chosen one are left as they are. Each change is a
    FactReviewHistory row and the gaps follow the normal review rules (after_fact_review). The CRI is
    recalculated. Permission: ownership.check_conflict_choice (checked by the caller)."""
    from django.db import transaction

    from apps.facts import evidence_requests
    from apps.facts.models import FactReviewHistory

    from .models import GapEvent
    from .models import GapItem as G
    if gap.gap_type != G.GapType.CONFLICT or gap.status not in G.ACTIVE_STATUSES:
        raise ConflictChoiceError('Only an open conflict can be decided.')
    candidates = [f for f in conflict_facts(gap) if f.status != ExtractedFact.Status.REJECTED]
    chosen = next((f for f in candidates if str(f.id) == str(fact_id)), None)
    if chosen is None:
        raise ConflictChoiceError('Choose one of the values this conflict compares.')
    from apps.facts.verification.normalize import same_value
    losers = [f for f in candidates if not same_value(f.value, chosen.value, chosen.data_type)]
    blocked = [f for f in [chosen, *losers] if evidence_requests.open_request_for(f)]
    if blocked:
        raise ConflictChoiceError(f'{blocked[0].field_name or blocked[0].field_key} has an open evidence request; '
                                  'decide that request first.')
    document = chosen.source_document or chosen.document
    where = f'{document.original_filename if document else "its document"}' + (
        f', page {chosen.source_page}' if chosen.source_page else '')
    note = (reason or '').strip()
    decision = f'Conflict decided: {chosen.value!r} from {where} is the correct value.' + (f' {note}' if note else '')
    now = timezone.now()
    with transaction.atomic():
        for fact in losers:
            FactReviewHistory.objects.create(fact=fact, action=FactReviewHistory.Action.REJECTED,
                                             original_value=fact.value, user=user, reason=decision)
            fact.status, fact.reviewed_by, fact.reviewed_at = ExtractedFact.Status.REJECTED, user, now
            fact.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        if chosen.status not in CONFIRMING_FACT_STATUSES:
            FactReviewHistory.objects.create(fact=chosen, action=FactReviewHistory.Action.CONFIRMED,
                                             original_value=chosen.value, user=user, reason=decision)
            chosen.status, chosen.reviewed_by, chosen.reviewed_at = ExtractedFact.Status.CONFIRMED, user, now
            chosen.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        _close(gap, G.Status.RESOLVED, user, decision, GapEvent.Action.RESOLVED)
        for fact in [*losers, chosen]:  # their own gaps follow (needs replacement, then replaced)
            after_fact_review(fact, user=user, reason=decision)
    from apps.scoring.services import run_scoring_engine
    run_scoring_engine(gap.sprint, triggered_by=user)
    return {'chosen': str(chosen.id), 'rejected': [str(f.id) for f in losers], 'resolution': decision}
