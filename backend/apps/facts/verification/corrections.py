"""Owner corrections of a reviewed fact: proposed with a reason and a source, approved by someone else.

Rules (enforced here; the views only translate errors):
- Who may propose: anyone allowed to act on the fact (ownership.check_fact) -- its owner role, a coordinator or
  InGage staff of the fact's own college.
- What is required: a reason, and support -- a cited document of the same sprint with a page (and ideally the
  quote), or a calculation whose inputs are cited. The proposed value is verified against that source
  (engine.verify_snapshot) and the result shown to the approver; a failing check does not block the proposal,
  but the approver sees exactly what failed.
- Nothing changes on the fact when proposed. One pending proposal per fact.
- Who may approve or reject: a different person (never the submitter) who may also act on the fact. Approval
  is refused if the fact changed since the proposal (it is then marked stale and must be proposed again).
- Approval: a CORRECTED FactReviewHistory row naming the proposal, submitter and approver; the fact's value and
  citation become the proposal's (the original extraction stays in `original_*` and in the history); the
  fact's gaps follow the normal review rules (gaps.services.after_fact_review); conflict summaries refresh. The
  CRI changes at its next normal recalculation, not here.
"""
from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import REVIEW_ROLES
from apps.facts.models import ExtractedFact, FactCorrectionProposal, FactReviewHistory

from . import engine, normalize

Status = FactCorrectionProposal.Status
CORRECTABLE = (ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.CORRECTED)


class CorrectionError(Exception):
    pass


class CorrectionForbidden(CorrectionError):
    pass


def _may_act(user, fact):
    from apps.facts.ownership import check_fact
    if user.role not in REVIEW_ROLES:
        return False, 'Your role cannot review facts.'
    return check_fact(user, fact)


def _verify(fact, *, value, document, page, snippet, derivation):
    snapshot = engine.Snapshot.of(fact, value=value, source_document=document, source_page=page or '',
                                  source_snippet=snippet or '', derivation=derivation or {},
                                  normalized_value=None, confidence_score=None, extraction_method='correction')
    return engine.verify_snapshot(snapshot, exclude_ids=[]).as_dict()


def propose(fact, user, *, value, reason, source_document=None, source_page='', source_snippet='',
            derivation=None):
    allowed, why = _may_act(user, fact)
    if not allowed:
        raise CorrectionForbidden(why or 'You cannot act on this fact.')
    if fact.status not in CORRECTABLE:
        raise CorrectionError('Only a confirmed or corrected fact takes a correction proposal; review an '
                              'unreviewed fact directly (confirm, correct or reject).')
    from apps.facts.evidence_requests import open_request_for
    if open_request_for(fact):
        raise CorrectionError('This fact has an open evidence request; decide that request first.')
    reason = (reason or '').strip()
    if not reason:
        raise CorrectionError('Say why the value is wrong.')
    if source_document is not None and source_document.sprint_id != fact.sprint_id:
        raise CorrectionError('The supporting document must belong to this sprint.')
    if source_document is None and not (derivation or {}).get('inputs'):
        raise CorrectionError('Cite the supporting document and page (or a calculation from cited inputs).')
    if source_document is not None and not str(source_page or '').strip():
        raise CorrectionError('Give the page of the supporting document.')
    if normalize.same_value(value, fact.value, fact.data_type) and source_document == (
            fact.source_document or fact.document) and str(source_page) == str(fact.source_page):
        raise CorrectionError('The proposed value and source are the same as the fact\'s.')
    verification = _verify(fact, value=value, document=source_document, page=source_page, snippet=source_snippet,
                           derivation=derivation)
    with transaction.atomic():
        if FactCorrectionProposal.objects.select_for_update().filter(fact=fact, status=Status.PENDING).exists():
            raise CorrectionError('A correction is already awaiting approval for this fact.')
        proposal = FactCorrectionProposal.objects.create(
            fact=fact, sprint_id=fact.sprint_id, value_before=fact.value, status_before=fact.status,
            proposed_value=value, reason=reason, source_document=source_document,
            source_page=str(source_page or '')[:50], source_snippet=(source_snippet or '').strip(),
            derivation=derivation or {}, verification=verification, submitted_by=user)
        FactReviewHistory.objects.create(
            fact=fact, action=FactReviewHistory.Action.CORRECTION_PROPOSED, original_value=fact.value,
            new_value=value, user=user, reason=reason, decision_source=FactReviewHistory.DecisionSource.PERSON,
            details={'proposal_id': str(proposal.id), 'verification': verification.get('outcome'),
                     'source_document_id': str(source_document.id) if source_document else None,
                     'source_page': proposal.source_page})
    return proposal


def _require_reviewer(proposal, user):
    if proposal.status != Status.PENDING:
        raise CorrectionError('This correction has already been decided.')
    if proposal.submitted_by_id == user.pk:
        raise CorrectionForbidden('Someone other than the person who proposed the correction must decide it.')
    allowed, why = _may_act(user, proposal.fact)
    if not allowed:
        raise CorrectionForbidden(why or 'You cannot act on this fact.')


def approve(proposal, user, *, note=''):
    from apps.gaps.services import after_fact_review
    from . import conflicts
    stale = False
    with transaction.atomic():
        proposal = FactCorrectionProposal.objects.select_for_update(of=('self',)).select_related(
            'fact__sprint', 'source_document', 'submitted_by').get(pk=proposal.pk)
        _require_reviewer(proposal, user)
        fact = ExtractedFact.objects.select_for_update().get(pk=proposal.fact_id)
        stale = fact.status != proposal.status_before or not normalize.same_value(
            fact.value, proposal.value_before, fact.data_type)
        if stale:  # recorded below, outside this block, so the refusal does not roll it back
            proposal.status = Status.STALE
            proposal.save(update_fields=['status'])
    if stale:
        raise CorrectionError('The fact changed after this correction was proposed; propose it again.')
    with transaction.atomic():
        proposal = FactCorrectionProposal.objects.select_for_update(of=('self',)).select_related(
            'fact__sprint', 'source_document', 'submitted_by').get(pk=proposal.pk)
        _require_reviewer(proposal, user)  # still pending at this moment
        fact = ExtractedFact.objects.select_for_update().get(pk=proposal.fact_id)
        now = timezone.now()
        note = (note or '').strip()
        submitter = proposal.submitted_by
        FactReviewHistory.objects.create(
            fact=fact, action=FactReviewHistory.Action.CORRECTED, original_value=fact.value,
            new_value=proposal.proposed_value, user=user, decision_source=FactReviewHistory.DecisionSource.PERSON,
            reason=f'Correction approved: {proposal.reason}' + (f' Approver: {note}' if note else ''),
            details={'proposal_id': str(proposal.id), 'submitted_by': str(proposal.submitted_by_id),
                     'submitted_by_name': (submitter.get_full_name() or submitter.email) if submitter else '',
                     'approved_by': str(user.pk),
                     'source_document_id': str(proposal.source_document_id) if proposal.source_document_id else None,
                     'source_page': proposal.source_page})
        fact.value = proposal.proposed_value
        fact.normalized_value = _normalized(proposal.proposed_value, fact.data_type)
        fact.status = ExtractedFact.Status.CORRECTED
        fact.reviewed_by, fact.reviewed_at = user, now
        fact.value_origin = ExtractedFact.ValueOrigin.CORRECTED
        if proposal.source_document_id:
            fact.source_document = proposal.source_document
            fact.source_page = proposal.source_page
            fact.source_snippet = proposal.source_snippet or fact.source_snippet
        if proposal.derivation:
            fact.derivation = {**proposal.derivation, 'source': 'correction'}
        fact.save(update_fields=['value', 'normalized_value', 'status', 'reviewed_by', 'reviewed_at',
                                 'value_origin', 'source_document', 'source_page', 'source_snippet', 'derivation',
                                 'updated_at'])
        proposal.status, proposal.reviewed_by, proposal.reviewed_at, proposal.review_reason = (
            Status.APPROVED, user, now, note)
        proposal.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_reason'])
        after_fact_review(fact, user=user, reason=f'Correction approved: {proposal.reason}')
        conflicts.refresh_for_field(fact.sprint_id, fact.field_key, user=user)
    engine.verify_fact(fact, source='correction')  # for display; the fact is reviewed, nothing is decided
    return proposal


def reject(proposal, user, *, reason):
    reason = (reason or '').strip()
    if not reason:
        raise CorrectionError('Say why the correction is rejected.')
    with transaction.atomic():
        proposal = FactCorrectionProposal.objects.select_for_update(of=('self',)).select_related(
            'fact__sprint').get(pk=proposal.pk)
        _require_reviewer(proposal, user)
        proposal.status, proposal.reviewed_by, proposal.reviewed_at, proposal.review_reason = (
            Status.REJECTED, user, timezone.now(), reason)
        proposal.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_reason'])
        FactReviewHistory.objects.create(
            fact=proposal.fact, action=FactReviewHistory.Action.CORRECTION_REJECTED,
            original_value=proposal.fact.value, new_value=proposal.proposed_value, user=user, reason=reason,
            decision_source=FactReviewHistory.DecisionSource.PERSON, details={'proposal_id': str(proposal.id)})
    return proposal


def withdraw(proposal, user):
    if proposal.status != Status.PENDING:
        raise CorrectionError('This correction has already been decided.')
    if proposal.submitted_by_id != user.pk:
        raise CorrectionForbidden('Only the person who proposed the correction can withdraw it.')
    proposal.status = Status.WITHDRAWN
    proposal.save(update_fields=['status'])
    return proposal


def _normalized(value, data_type):
    number = normalize.parse_number(value) if data_type in ('number', 'percentage', 'currency') else None
    if number is not None:
        return int(number) if number == number.to_integral() else float(number)
    return value
