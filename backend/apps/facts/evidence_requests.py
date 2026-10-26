"""Evidence requests: a reviewer asks a named person for evidence behind one fact, that person submits a
document, and a reviewer explicitly decides. Every step is an EvidenceRequestEvent (append-only); every
change to the fact itself is also a FactReviewHistory row, as with the other fact actions.

AI evidence analysis is advisory. Uploading or pasting evidence never confirms a fact, changes its value,
resolves a request or touches the CRI -- only an authorized, different reviewer can do that through
`review()`.
"""
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import REVIEW_ROLES, user_can_access_institution
from apps.documents.models import Document

from .models import EvidenceRequest, EvidenceRequestDocument, EvidenceRequestEvent, ExtractedFact, FactReviewHistory

Status = EvidenceRequest.Status
Event = EvidenceRequestEvent.Action

#: Besides the requester, who may assign / reassign a request (and so cover a role with no user yet).
ASSIGN_ROLES = {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.INSTITUTION_ADMIN, User.Role.IQAC_COORDINATOR}

#: Default document type for a file uploaded as evidence (the uploader may choose another).
EVIDENCE_DOCUMENT_TYPE = 'supporting_evidence'


class EvidenceRequestError(Exception):
    """A rule of the workflow was broken; the message is shown to the user (HTTP 400)."""


def _event(request, action, user, note='', **data):
    return EvidenceRequestEvent.objects.create(request=request, action=action, user=user, note=note, data=data)


def _person(user):
    return {'id': str(user.id), 'name': user.get_full_name() or user.email} if user else None


def open_request_for(fact):
    return fact.evidence_requests.filter(status__in=EvidenceRequest.UNRESOLVED).first()


# -- who ------------------------------------------------------------------------------------------

def eligible_assignees(sprint):
    """Active people of the sprint's college who can upload evidence (everyone but a viewer)."""
    return (User.objects.filter(institution_id=sprint.institution_id, is_active=True)
            .exclude(role=User.Role.VIEWER).order_by('first_name', 'last_name', 'email'))


def _eligible(sprint, user_id):
    if user_id in (None, ''):
        return None
    user = eligible_assignees(sprint).filter(pk=user_id).first()
    if user is None:
        raise EvidenceRequestError('Assign the request to an active, non-viewer user of this college.')
    return user


def can_assign(user, request):
    return user.role in ASSIGN_ROLES or user.pk == request.requested_by_id


def _require_unresolved(request):
    if request.is_resolved:
        raise EvidenceRequestError(f'This request is already {request.get_status_display().lower()}.')


# -- create / assign / comment ----------------------------------------------------------------------

def create_request(fact, user, *, description='', evidence_needed='', reason='', assigned_to=None, due_date=None):
    # `description` remains accepted for old clients. New clients store the request and its reason separately.
    evidence_needed = (evidence_needed or description or '').strip()
    reason = (reason or description or '').strip()
    description = f'{evidence_needed}\n\nWhy: {reason}'.strip()
    if not evidence_needed:
        raise EvidenceRequestError('Say what evidence is needed.')
    if not reason:
        raise EvidenceRequestError('Explain why the evidence is needed.')
    if due_date and due_date < date.today():
        raise EvidenceRequestError('The due date cannot be in the past.')
    assignee = _eligible(fact.sprint, assigned_to)
    try:
        with transaction.atomic():
            fact = ExtractedFact.objects.select_for_update().get(pk=fact.pk)
            # Checked under the fact's lock, so a double click or two reviewers at once still make one request
            # (the unique constraint one_unresolved_evidence_request_per_fact backs this up).
            if open_request_for(fact):
                raise EvidenceRequestError('This fact already has an open evidence request.')
            request = EvidenceRequest.objects.create(
                sprint=fact.sprint, fact=fact, requested_by=user, suggested_owner_role=fact.owner_role,
                assigned_to=assignee, description=description, evidence_needed=evidence_needed, reason=reason,
                due_date=due_date, fact_status_before=fact.status)
            FactReviewHistory.objects.create(fact=fact, action=FactReviewHistory.Action.EVIDENCE_REQUESTED,
                                             original_value=fact.value, user=user, reason=description)
            fact.status = ExtractedFact.Status.EVIDENCE_REQUESTED
            fact.reviewed_by = user
            fact.reviewed_at = timezone.now()
            fact.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
            _event(request, Event.CREATED, user, description, due_date=str(due_date) if due_date else None,
                   responsible_role=fact.owner_role, evidence_needed=evidence_needed, reason=reason)
            if assignee:
                _event(request, Event.ASSIGNED, user, '', **{'from': None, 'to': _person(assignee)})
    except IntegrityError:
        raise EvidenceRequestError('This fact already has an open evidence request.')
    return request


def assign(request, user, assigned_to, note=''):
    _require_unresolved(request)
    if not can_assign(user, request):
        raise EvidenceRequestError('Only the requester, an institution admin, IQAC or InGage staff can assign it.')
    assignee = _eligible(request.sprint, assigned_to)
    if assignee is None:
        raise EvidenceRequestError('Choose who should provide the evidence.')
    if assignee.pk == request.assigned_to_id:
        raise EvidenceRequestError('The request is already assigned to this person.')
    before = request.assigned_to
    with transaction.atomic():
        request.assigned_to = assignee
        request.save(update_fields=['assigned_to', 'updated_at'])
        _event(request, Event.ASSIGNED, user, (note or '').strip(), **{'from': _person(before), 'to': _person(assignee)})
    return request


def comment(request, user, note):
    note = (note or '').strip()
    if not note:
        raise EvidenceRequestError('Write a comment.')
    _event(request, Event.COMMENTED, user, note)
    return request


# -- submit -------------------------------------------------------------------------------------------

def submit_evidence(request, user, *, document_id=None, file=None, submitted_text='', source_context='',
                    document_type='', source_page='', source_snippet='', note='', run_extraction=True):
    """The assigned person submits one document or sourced text. AI assessment and ordinary extraction
    start automatically; neither can confirm the requested fact."""
    from apps.documents.services import DocumentValidationError, create_document_from_file

    _require_unresolved(request)
    if request.assigned_to_id != user.pk:
        raise EvidenceRequestError('Only the person this request is assigned to can submit evidence.')
    submitted_text = (submitted_text or '').strip()
    source_context = (source_context or '').strip()
    choices = sum(bool(x) for x in (document_id, file, submitted_text))
    if choices != 1:
        raise EvidenceRequestError('Upload a file, choose one existing document, or submit text (choose one).')
    if submitted_text and not source_context:
        raise EvidenceRequestError('Give the source or context for the submitted text.')
    uploaded = False
    document = None
    with transaction.atomic():
        if file:
            try:
                document = create_document_from_file(
                    sprint=request.sprint, file_obj=file, document_type=document_type or EVIDENCE_DOCUMENT_TYPE,
                    owner_role=user.role, title=f'Evidence: {request.fact.field_name}'[:255], uploaded_by=user)
            except DocumentValidationError as exc:
                raise EvidenceRequestError(_flatten(exc.errors))
            uploaded = True
        elif document_id:
            document = Document.objects.filter(pk=document_id, sprint=request.sprint).first()
            if document is None:
                raise EvidenceRequestError('That document is not in this sprint.')
            if request.evidence.filter(document=document).exists():
                raise EvidenceRequestError('That document is already linked to this request.')
        link = EvidenceRequestDocument.objects.create(
            request=request, document=document if not submitted_text else None,
            submitted_text=submitted_text, source_context=source_context[:2000], uploaded_for_request=uploaded,
            source_page=str(source_page or '')[:50], source_snippet=(source_snippet or '').strip(),
            note=(note or '').strip(), submitted_by=user)
        request.status = Status.SUBMITTED
        request.save(update_fields=['status', 'updated_at'])
        _event(request, Event.EVIDENCE_SUBMITTED, user, link.note, evidence_id=str(link.id),
               submission_type='text' if submitted_text else 'document',
               document_id=str(document.id) if document else None,
               document=document.original_filename or document.title if document else None,
               uploaded=uploaded, source_page=link.source_page)
    if submitted_text:
        from .tasks import analyze_text_evidence_submission
        try:
            analyze_text_evidence_submission.delay(str(link.id))
        except Exception as exc:
            from .evidence_analysis import _fail
            _fail(link, f'Could not queue AI assessment: {exc}')
    else:
        _start_extraction(request.sprint, document, link=link)
    return link


class RetryInProgress(EvidenceRequestError):
    """An AI assessment of this submission is already queued or running: nothing new was started."""


#: A run still "processing" after this long is treated as lost (e.g. a worker restart) and may be retried.
STALE_ASSESSMENT_MINUTES = 30


def request_assessment_retry(request, user, evidence_id):
    """A reviewer retries a FAILED AI assessment of one submission -- the same submission, its saved page text
    or pasted text, request and fact; no new upload, no extraction, no OCR. Exactly one run is queued per retry:
    a second click while it is queued or running raises RetryInProgress and changes nothing. The result stays
    advisory: only a reviewer's decision (review()) changes the fact or its gaps."""
    from datetime import timedelta

    from .ownership import check_fact
    _require_unresolved(request)
    if not can_review(user, request):
        raise EvidenceRequestError(check_fact(user, request.fact)[1] or 'You cannot retry the assessment of this evidence.')
    with transaction.atomic():
        link = (EvidenceRequestDocument.objects.select_for_update()
                .filter(pk=evidence_id, request=request).first())
        if link is None:
            raise EvidenceRequestError('Choose a submission of this request.')
        if link.submitted_by_id == user.pk:
            raise EvidenceRequestError('Someone other than the person who submitted the evidence must handle it.')
        if link.status != EvidenceRequestDocument.Status.SUBMITTED:
            raise EvidenceRequestError('That evidence has already been reviewed.')
        AS = EvidenceRequestDocument.AnalysisStatus
        stale = (link.analysis_status == AS.PROCESSING and link.analysis_started_at is not None
                 and link.analysis_started_at < timezone.now() - timedelta(minutes=STALE_ASSESSMENT_MINUTES))
        if link.analysis_status in (AS.PENDING, AS.PROCESSING) and not stale:
            raise RetryInProgress('An AI assessment of this evidence is already running. Wait for it to finish.')
        if link.analysis_status == AS.READY:
            raise EvidenceRequestError('This evidence already has an AI assessment ready for review.')
        previous_error = link.analysis_error if not stale else 'The previous assessment did not finish.'
        link.analysis_status = AS.PENDING
        link.analysis_retry_count += 1
        link.analysis_retry_requested_at, link.analysis_retry_requested_by = timezone.now(), user
        link.save(update_fields=['analysis_status', 'analysis_retry_count', 'analysis_retry_requested_at',
                                 'analysis_retry_requested_by'])
        request.status = Status.PROCESSING
        request.save(update_fields=['status', 'updated_at'])
        _event(request, Event.ANALYSIS_RETRY, user, evidence_id=str(link.id), retry=link.analysis_retry_count,
               previous_error=(previous_error or '')[:300])
        transaction.on_commit(lambda: _queue_retry(link))
    return link


def _queue_retry(link):
    from .tasks import retry_evidence_assessment
    try:
        retry_evidence_assessment.delay(str(link.id))
    except Exception as exc:
        from .evidence_analysis import _fail
        _fail(link, f'Could not queue the AI assessment retry: {exc}')


def _start_extraction(sprint, document, *, link=None):
    """Use the regular sprint extraction job; its page read also feeds request assessment."""
    from apps.extraction.models import ExtractionJob
    from apps.extraction.views import SprintExtractionJobListCreateView, dispatch_job

    jobs = SprintExtractionJobListCreateView._prepare_jobs(sprint, [document])
    if jobs:
        job = dispatch_job(jobs[0])
        if job.status == ExtractionJob.Status.FAILED and link is not None:
            from .evidence_analysis import _fail
            _fail(link, job.error_message or 'The document extraction job could not be queued.')
        return job
    active_job = ExtractionJob.objects.filter(
        sprint=sprint, document=document,
        status__in=[ExtractionJob.Status.PENDING, ExtractionJob.Status.RUNNING, ExtractionJob.Status.RETRYING],
    ).first()
    if active_job:
        if active_job.current_step == ExtractionJob.Step.PREPARING_REVIEW_WORKSPACE and link is not None:
            from .tasks import analyze_existing_document_evidence
            try:
                analyze_existing_document_evidence.delay(str(link.id))
            except Exception as exc:
                from .evidence_analysis import _fail
                _fail(link, f'Could not queue AI assessment: {exc}')
        return None  # the existing extraction pipeline will assess pending request evidence after its page read
    completed = ExtractionJob.objects.filter(sprint=sprint, document=document,
                                             status=ExtractionJob.Status.COMPLETED).exists()
    if completed and link is not None:
        from .tasks import analyze_existing_document_evidence
        try:
            analyze_existing_document_evidence.delay(str(link.id))
        except Exception as exc:
            from .evidence_analysis import _fail
            _fail(link, f'Could not queue AI assessment: {exc}')
        return None
    if link is not None:
        from .evidence_analysis import _fail
        _fail(link, 'No extraction job could be started for this document.')
    return None


def _flatten(errors):
    if isinstance(errors, dict):
        return ' '.join(f'{k}: {_flatten(v)}' for k, v in errors.items())
    if isinstance(errors, (list, tuple)):
        return ' '.join(_flatten(e) for e in errors)
    return str(errors)


# -- review -------------------------------------------------------------------------------------------

DECISIONS = ('accept', 'accept_corrected', 'return', 'reject', 'withdraw')


def can_review(user, request):
    """Deciding on evidence confirms, corrects or keeps a fact, so it follows the fact's ownership rule
    (apps/facts/ownership.py): its owner role, an Institution Admin or InGage staff."""
    from .ownership import check_fact
    return user.role in REVIEW_ROLES and check_fact(user, request.fact)[0]


def can_withdraw(user, request):
    """Withdrawing changes no fact: the fact's owners, the requester, or a coordinator may."""
    from .ownership import is_coordinator
    return (can_review(user, request) or user.pk == request.requested_by_id
            or is_coordinator(user, request.sprint.institution_id))


def review(request, user, decision, *, evidence_id=None, reason='', corrected_value=None,
           has_corrected_value=False, source_page=None, source_snippet=None, return_to_assignee=True):
    """A reviewer's explicit decision -- the only way a request is resolved."""
    if decision not in DECISIONS:
        raise EvidenceRequestError(f'decision must be one of {", ".join(DECISIONS)}.')
    _require_unresolved(request)
    from .ownership import check_fact
    if decision == 'withdraw' and not can_withdraw(user, request):
        raise EvidenceRequestError('Only the requester, a coordinator (Institution Admin, IQAC Coordinator, '
                                   'InGage staff) or the fact\'s owner role can withdraw this request.')
    if decision != 'withdraw' and not can_review(user, request):
        raise EvidenceRequestError(check_fact(user, request.fact)[1] or 'You cannot decide evidence for this fact.')
    reason = (reason or '').strip()

    if decision == 'withdraw':
        if not reason:
            raise EvidenceRequestError('Give a reason for withdrawing the request.')
        return _withdraw(request, user, reason)

    link = request.evidence.filter(pk=evidence_id).select_related('document').first() if evidence_id else None
    if link is None:
        raise EvidenceRequestError('Choose the submitted evidence you are deciding on.')
    if link.status != EvidenceRequestDocument.Status.SUBMITTED:
        raise EvidenceRequestError('That evidence has already been reviewed.')
    if link.submitted_by_id == user.pk:
        raise EvidenceRequestError('Someone other than the person who submitted the evidence must review it.')

    if decision in ('return', 'reject'):
        if not reason:
            raise EvidenceRequestError('Explain what is missing or why the evidence was rejected.')
        return _return_or_reject(request, user, link, decision, reason)
    if decision == 'accept_corrected' and not has_corrected_value:
        raise EvidenceRequestError('Enter the corrected value.')
    page = link.source_page if source_page is None else str(source_page)[:50]
    snippet = link.source_snippet if source_snippet is None else (source_snippet or '').strip()
    if (page and link.document_id and link.document.page_count and page.isdigit()
            and not 1 <= int(page) <= link.document.page_count):
        raise EvidenceRequestError(f'Page {page} is outside the document ({link.document.page_count} pages).')
    return _accept(request, user, link, decision, reason, page, snippet, corrected_value)


def _accept(request, user, link, decision, reason, page, snippet, corrected_value):
    from apps.gaps.services import resolve_evidence_gaps

    corrected = decision == 'accept_corrected'
    now = timezone.now()
    with transaction.atomic():
        fact = ExtractedFact.objects.select_for_update().get(pk=request.fact_id)
        original_value = fact.value
        evidence_source = (link.document.original_filename or link.document.title) if link.document_id else \
            f'text submission ({link.source_context[:160]})'
        FactReviewHistory.objects.create(
            fact=fact, action=FactReviewHistory.Action.CORRECTED if corrected else FactReviewHistory.Action.CONFIRMED,
            original_value=original_value, new_value=corrected_value if corrected else None, user=user,
            reason=f'Evidence accepted: {evidence_source}'
                   f'{f", page {page}" if page else ""}.' + (f' {reason}' if reason else ''))
        fields = ['status', 'reviewed_by', 'reviewed_at', 'source_document', 'source_page', 'source_snippet',
                  'updated_at']
        if corrected:
            fact.value = corrected_value
            fields.append('value')
        fact.status = ExtractedFact.Status.CORRECTED if corrected else ExtractedFact.Status.CONFIRMED
        fact.reviewed_by, fact.reviewed_at = user, now
        fact.source_document, fact.source_page = link.document, page
        fact.source_snippet = snippet or link.analysis_quote or link.submitted_text[:2000]
        fact.save(update_fields=fields)
        resolved_gap_ids = resolve_evidence_gaps(fact, request=request, link=link, user=user)

        link.status = EvidenceRequestDocument.Status.ACCEPTED
        link.review_reason, link.reviewed_by, link.reviewed_at = reason, user, now
        link.save(update_fields=['status', 'review_reason', 'reviewed_by', 'reviewed_at'])
        request.status = Status.ACCEPTED_CORRECTED if corrected else Status.ACCEPTED
        request.resolution_note, request.resolved_by, request.resolved_at = reason, user, now
        request.save(update_fields=['status', 'resolution_note', 'resolved_by', 'resolved_at', 'updated_at'])
        _event(request, Event.FACT_UPDATED, user, reason, evidence_id=str(link.id),
               document_id=str(link.document_id) if link.document_id else None,
               original_value=original_value,
               reviewed_value=corrected_value if corrected else fact.value,
               reviewer_id=str(user.id), reviewed_at=now.isoformat(), source_page=page,
               source_snippet=fact.source_snippet)
        if resolved_gap_ids:
            _event(request, Event.GAPS_RESOLVED, user, 'Only this fact\'s unconfirmed and low-confidence gaps were resolved.',
                   gap_ids=[str(gap_id) for gap_id in resolved_gap_ids])
        _event(request, Event.ACCEPTED_CORRECTED if corrected else Event.ACCEPTED, user, reason,
               evidence_id=str(link.id), document_id=str(link.document_id) if link.document_id else None, source_page=page,
               **({'corrected_value': corrected_value} if corrected else {}))
    return request


def _return_or_reject(request, user, link, decision, reason):
    now = timezone.now()
    with transaction.atomic():
        link.status = EvidenceRequestDocument.Status.RETURNED if decision == 'return' else EvidenceRequestDocument.Status.REJECTED
        link.review_reason, link.reviewed_by, link.reviewed_at = reason, user, now
        link.save(update_fields=['status', 'review_reason', 'reviewed_by', 'reviewed_at'])
        request.status = Status.RETURNED
        request.save(update_fields=['status', 'updated_at'])
        action = Event.EVIDENCE_RETURNED if decision == 'return' else Event.EVIDENCE_REJECTED
        _event(request, action, user, reason, evidence_id=str(link.id),
               document_id=str(link.document_id) if link.document_id else None, status=request.status)
        from .evidence_analysis import _request_status
        _request_status(request)
    return request


def _withdraw(request, user, reason):
    now = timezone.now()
    with transaction.atomic():
        fact = ExtractedFact.objects.select_for_update().get(pk=request.fact_id)
        if fact.status == ExtractedFact.Status.EVIDENCE_REQUESTED:
            FactReviewHistory.objects.create(fact=fact, action=FactReviewHistory.Action.REQUEST_WITHDRAWN,
                                             original_value=fact.value, user=user, reason=reason)
            fact.status = request.fact_status_before
            fact.save(update_fields=['status', 'updated_at'])
        request.status = Status.WITHDRAWN
        request.resolution_note, request.resolved_by, request.resolved_at = reason, user, now
        request.save(update_fields=['status', 'resolution_note', 'resolved_by', 'resolved_at', 'updated_at'])
        _event(request, Event.WITHDRAWN, user, reason, fact_status=fact.status)
    return request


# -- suggestions --------------------------------------------------------------------------------------

def suggested_facts(request):
    """Facts extracted from this request's evidence documents that look relevant to the requested fact:
    the same field, or a shared AI-QIF indicator. Read-only suggestions for the reviewer -- deterministic,
    and never confirmed or copied onto the requested fact by themselves."""
    document_ids = list(request.evidence.values_list('document_id', flat=True))
    if not document_ids:
        return []
    key = request.fact.field_key.strip().lower()
    codes = set(request.fact.aiqif_mappings.values_list('indicator_code', flat=True))
    out = []
    candidates = (ExtractedFact.objects.filter(document_id__in=document_ids).exclude(pk=request.fact_id)
                  .prefetch_related('aiqif_mappings').select_related('document').order_by('field_key', 'source_page'))
    for fact in candidates:
        shared = sorted(codes & {m.indicator_code for m in fact.aiqif_mappings.all()})
        same_field = fact.field_key.strip().lower() == key
        if not (same_field or shared):
            continue
        out.append({'fact': fact, 'why': 'Same field' if same_field else f'Shares {", ".join(shared)}'})
    out.sort(key=lambda s: s['why'] != 'Same field')
    return out
