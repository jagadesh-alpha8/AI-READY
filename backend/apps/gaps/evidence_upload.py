"""Evidence uploaded straight from a Missing Document or Low Confidence gap.

    upload_for_gap(gap, user, file)   -> (document, reused)   store in the gap's sprint, link, queue processing
    evidence_state(gap)               -> {state, label, reason, next_action, documents}

An upload never confirms a fact, corrects a value, confirms an AI-QIF tag or resolves a gap. The document goes
through the normal sprint pipeline (its own job in this sprint; a file processed in another sprint is processed
again here; the same file in the same sprint is reused, never stored or queued twice). The gap closes only
through the existing review rules (services.py):

- Missing Document: when a person confirms the category of a document of that type (after_document_review);
- Low Confidence: when the original fact is reviewed with a citation, its evidence request is accepted, or --
  new here -- a reviewer confirms / corrects the same field from this gap's uploaded evidence with a citation
  while no conflict on that field is open (close_low_confidence_from_evidence, called from after_fact_review).

Every step is a GapEvent: evidence_uploaded, evidence_processed / evidence_failed, and the existing
auto_resolved when the review closes the gap.
"""
from django.db import transaction

from apps.documents.models import Document
from apps.facts.models import ExtractedFact

from .models import GapEvent, GapItem

ELIGIBLE_TYPES = (GapItem.GapType.MISSING_DOCUMENT, GapItem.GapType.LOW_CONFIDENCE)
LOW_CONFIDENCE_DOCUMENT_TYPE = 'supporting_evidence'


class EvidenceUploadError(Exception):
    pass


def _event(gap, action, user, note='', **data):
    return GapEvent.objects.create(gap=gap, action=action, user=user, note=note or '', data=data)


def requested_document_type(gap):
    from .services import missing_document_type
    if gap.gap_type == GapItem.GapType.MISSING_DOCUMENT:
        return missing_document_type(gap) or 'other'
    return LOW_CONFIDENCE_DOCUMENT_TYPE


def _owner_role(gap):
    from apps.facts.ownership import gap_owner_role
    return gap_owner_role(gap) or ''


def check_eligible(gap):
    if gap.gap_type not in ELIGIBLE_TYPES:
        raise EvidenceUploadError('Evidence can be uploaded from Missing Document and Low Confidence gaps only.')
    if gap.status not in GapItem.ACTIVE_STATUSES:
        raise EvidenceUploadError(f'This gap is already {gap.get_status_display().lower()}.')


def upload_for_gap(gap, user, file_obj, *, document_type=''):
    """Store the file in the gap's sprint (or reuse the identical file already in that sprint), link it to the gap
    and queue its processing in that sprint. Returns (document, reused)."""
    from apps.documents.services import DocumentValidationError, create_document_from_file
    from apps.documents.utils import compute_file_checksum

    check_eligible(gap)
    if not file_obj:
        raise EvidenceUploadError('Choose a file to upload.')
    sprint = gap.sprint
    checksum = compute_file_checksum(file_obj)
    existing = Document.objects.filter(sprint=sprint, checksum=checksum).first() if checksum else None
    with transaction.atomic():
        if existing is not None:
            document, reused = existing, True  # same file, same sprint: one document, one processing record
        else:
            try:
                document = create_document_from_file(
                    sprint=sprint, file_obj=file_obj, document_type=document_type or requested_document_type(gap),
                    owner_role=_owner_role(gap), title=f'Evidence for: {gap.title}'[:255], uploaded_by=user)
            except DocumentValidationError as exc:
                raise EvidenceUploadError(' '.join(f'{k}: {v}' for k, v in exc.errors.items())
                                          if isinstance(exc.errors, dict) else str(exc.errors))
            reused = False
        gap.evidence_documents.add(document)
        if gap.status == GapItem.Status.OPEN:
            gap.status = GapItem.Status.IN_PROGRESS
            gap.save(update_fields=['status', 'updated_at'])
        _event(gap, GapEvent.Action.EVIDENCE_UPLOADED, user,
               f'{document.original_filename} {"(already in this sprint, linked)" if reused else "uploaded"}.',
               document_id=str(document.id), filename=document.original_filename, reused=reused,
               document_type=document.document_type)
    _queue(sprint, document)  # after the link is saved (the atomic block above has finished)
    return document, reused


def _queue(sprint, document):
    """Process the document in this sprint (reusing its retryable job; never a second job for a done one)."""
    from apps.extraction.views import SprintExtractionJobListCreateView, dispatch_job
    for job in SprintExtractionJobListCreateView._prepare_jobs(sprint, [document]):
        dispatch_job(job)


def record_processing(job, ok, message=''):
    """Extraction hook: note the processing result on every gap this document is evidence for."""
    for gap in GapItem.objects.filter(evidence_documents=job.document_id):
        if ok:
            facts = ExtractedFact.objects.filter(document_id=job.document_id).count()
            _event(gap, GapEvent.Action.EVIDENCE_PROCESSED, None,
                   f'{job.document.original_filename} processed: {facts} fact(s) to review'
                   + (' (partially read)' if job.completeness == 'partial' else '') + '.',
                   document_id=str(job.document_id), job_id=str(job.id), facts=facts,
                   completeness=job.completeness)
        else:
            _event(gap, GapEvent.Action.EVIDENCE_FAILED, None, (message or '')[:500],
                   document_id=str(job.document_id), job_id=str(job.id))


def _latest_job(document):
    from apps.extraction.models import ExtractionJob
    return ExtractionJob.objects.filter(document=document).order_by('-created_at').first()


def evidence_state(gap, requests=None):
    """What has happened to the evidence for this gap, why, and what to do next (for the Gap Dashboard)."""
    from apps.extraction.models import ExtractionJob as J
    docs = list(gap.evidence_documents.all().order_by('-created_at')) if gap.pk else []
    if gap.status not in GapItem.ACTIVE_STATUSES:
        return {'state': 'resolved' if gap.status == GapItem.Status.RESOLVED else 'closed',
                'label': gap.get_status_display(), 'reason': gap.resolution, 'next_action': '', 'documents': _docs(docs)}
    if not docs:
        if requests and any(r.status in ('open', 'returned') for r in requests):
            return {'state': 'evidence_requested', 'label': 'Evidence requested', 'documents': [],
                    'reason': 'An evidence request is open for this gap.',
                    'next_action': 'The assigned person submits evidence, or upload it here.'}
        return {'state': 'still_open', 'label': 'Still open', 'documents': [],
                'reason': 'No evidence has been uploaded for this gap yet.', 'next_action': 'Upload Evidence.'}
    doc = docs[0]
    job = _latest_job(doc)
    if job is None or job.status in (J.Status.PENDING, J.Status.RUNNING, J.Status.RETRYING):
        state = ('uploaded', 'Uploaded') if job is None else ('processing', 'Processing')
        return {'state': state[0], 'label': state[1], 'documents': _docs(docs),
                'reason': f'{doc.original_filename} is {"queued" if job is None else "being processed"}.',
                'next_action': 'Wait for processing (AI Processing Monitor).'}
    if job.status != J.Status.COMPLETED:
        return {'state': 'processing_failed', 'label': 'Processing failed', 'documents': _docs(docs),
                'reason': (job.error_message or 'Processing stopped.')[:300],
                'next_action': 'Process the document again in the AI Processing Monitor.'}
    if gap.gap_type == GapItem.GapType.MISSING_DOCUMENT:
        reason = f'{doc.original_filename} was received and processed.'
        nxt = 'Confirm its category in Upload Data Pack (that closes this gap), and review its facts in Facts Review.'
    else:
        reason = f'{doc.original_filename} was processed; its facts are separate suggestions awaiting review.'
        nxt = ('In Facts Review, confirm or correct the value for this field from the new document (with its '
               'citation). If it disagrees with a confirmed value, settle the conflict first.')
    if job.completeness == 'partial':
        reason += ' Some of it could not be read (partially processed).'
    return {'state': 'awaiting_review', 'label': 'Awaiting fact review', 'reason': reason, 'next_action': nxt,
            'documents': _docs(docs)}


def _docs(docs):
    return [{'id': str(d.id), 'filename': d.original_filename, 'document_type': d.document_type} for d in docs]


def close_low_confidence_from_evidence(fact, user):
    """A reviewer confirmed / corrected `fact`: close each low-confidence gap whose uploaded evidence this fact
    came from, for the same field, when the fact cites the document and no conflict on that field is open.
    Recalculates the sprint's CRI when a gap closed. Returns the number of gaps closed."""
    from .services import CONFIRMING_FACT_STATUSES, _close, fact_has_reviewed_citation
    if fact.status not in CONFIRMING_FACT_STATUSES or fact.document_id is None or not fact_has_reviewed_citation(fact):
        return 0
    key = fact.field_key.strip().lower()
    closed = 0
    for gap in GapItem.objects.filter(sprint_id=fact.sprint_id, gap_type=GapItem.GapType.LOW_CONFIDENCE,
                                      status__in=GapItem.ACTIVE_STATUSES, evidence_documents=fact.document_id,
                                      source_fact__isnull=False).select_related('source_fact'):
        if gap.source_fact.field_key.strip().lower() != key or gap.source_fact_id == fact.id:
            continue
        if GapItem.objects.filter(sprint_id=fact.sprint_id, gap_type=GapItem.GapType.CONFLICT,
                                  status__in=GapItem.ACTIVE_STATUSES, source_fact__field_key=fact.field_key).exists():
            continue  # the new evidence disagrees with another value: settle the conflict first
        _close(gap, GapItem.Status.RESOLVED, user,
               f'Verified from uploaded evidence: {fact.field_name or fact.field_key} = {fact.value!r} '
               f'({fact.get_status_display().lower()} by {user.get_full_name() or user.email}, page '
               f'{fact.source_page or "?"}).', GapEvent.Action.AUTO_RESOLVED)
        closed += 1
    if closed:
        from apps.scoring.services import run_scoring_engine
        run_scoring_engine(fact.sprint, triggered_by=user)
    return closed
