"""Baseline approval workflow -- see apps.scoring.models.Baseline.

Bootstraps, approves, provisionally approves, and returns-for-correction a
sprint's CRI baseline, reusing the existing scoring engine
(`cri_engine.run_scoring_engine`) for whatever ScoringRun a baseline
decision gets pinned to, rather than recomputing anything here.

Freshness (services/inputs.py): a PENDING baseline always previews the sprint as it is now -- when its run's
input fingerprint no longer matches the sprint, it is repointed at a run that does (the latest run if it matches,
otherwise a fresh calculation), recorded as REFRESHED. Approving names the run the reviewer saw
(`expected_scoring_run_id`); if the preview changed, nothing is approved and BaselineChanged (409) returns the
new preview for review. A decided baseline is never repointed.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from apps.gaps.models import GapItem
from apps.sprints.models import Sprint

from ..models import Baseline, BaselineDecisionHistory
from .cri_engine import run_scoring_engine
from .inputs import scoring_inputs_fingerprint


class BaselineChanged(APIException):
    """The pending baseline's score is not the one the reviewer saw: review the refreshed preview first."""
    status_code = status.HTTP_409_CONFLICT
    default_code = 'baseline_changed'
    default_detail = ('The baseline score changed since you loaded it (facts, gaps, tags or scoring inputs changed). '
                      'Review the updated score below, then approve again.')

#: Sprint statuses a baseline may legitimately be bootstrapped/decided from.
#: REVIEWING is included alongside SCORING so GET .../baseline/ still works
#: (computing a first-ever score on the spot, same as GET .../score/) even
#: if the caller never explicitly POSTed /score first.
_BOOTSTRAPPABLE_STATUSES = (Sprint.Status.REVIEWING, Sprint.Status.SCORING)


def _latest_baseline(sprint):
    return sprint.baselines.order_by('-created_at').first()


def _record(baseline, action, user, comments):
    BaselineDecisionHistory.objects.create(
        baseline=baseline, action=action,
        user=user if (user and user.is_authenticated) else None,
        comments=comments,
    )


def _current_run(sprint, fingerprint, user):
    """A ScoringRun matching `fingerprint`: the latest run when it does, else a fresh calculation."""
    latest = sprint.scoring_runs.order_by('-created_at').first()
    if latest is not None and latest.inputs_fingerprint == fingerprint:
        return latest
    return run_scoring_engine(sprint, triggered_by=user)


def _describe(run):
    return f'Raw CRI {run.overall_cri:.1f}, calculated {run.created_at:%d %b %Y %H:%M} (run {str(run.pk)[:8]})'


def refresh_pending_baseline(sprint, *, user=None):
    """Point the sprint's PENDING baseline at a run matching the current data. Returns (baseline, refreshed).
    A decided (or absent) baseline is returned untouched. Old runs are kept as they are."""
    with transaction.atomic():
        latest = _latest_baseline(sprint)
        if latest is None or latest.status != Baseline.Status.PENDING:
            return latest, False
        baseline = Baseline.objects.select_for_update().select_related('scoring_run').get(pk=latest.pk)
        if baseline.status != Baseline.Status.PENDING:  # decided while we waited for the lock
            return baseline, False
        fingerprint = scoring_inputs_fingerprint(sprint)
        if baseline.scoring_run.inputs_fingerprint == fingerprint:
            return baseline, False
        old = baseline.scoring_run
        baseline.scoring_run = _current_run(sprint, fingerprint, user)
        baseline.save(update_fields=['scoring_run', 'updated_at'])
        _record(baseline, BaselineDecisionHistory.Action.REFRESHED, user,
                f'The sprint data changed, so the preview was recalculated: {_describe(old)} -> '
                f'{_describe(baseline.scoring_run)}.')
    return baseline, True


def is_current(baseline):
    """Whether the baseline's run still matches the sprint's scoring inputs (for a decided one: whether the
    Live CRI has moved on since the decision)."""
    return bool(baseline and baseline.scoring_run.inputs_fingerprint
                and baseline.scoring_run.inputs_fingerprint == scoring_inputs_fingerprint(baseline.sprint))


def get_or_create_pending_baseline(sprint, *, triggered_by=None):
    """Return the sprint's current baseline decision-cycle, bootstrapping a
    new PENDING one (against a ScoringRun of the current data) if none is
    currently open -- i.e. the sprint has never submitted a baseline, or its
    last one was RETURNED. An open PENDING one is refreshed first when the data
    changed since its run. Advances the sprint to BASELINE_PENDING the first
    time this fires, from REVIEWING or SCORING -- the same "a GET can have a
    legitimate bootstrap side effect" pattern
    apps.scoring.services.cri_engine.build_score_snapshot already uses for
    ScoringRun itself.
    """
    existing = _latest_baseline(sprint)
    if existing is not None and existing.status != Baseline.Status.RETURNED:
        return refresh_pending_baseline(sprint, user=triggered_by)[0]

    run = _current_run(sprint, scoring_inputs_fingerprint(sprint), triggered_by)
    # A returned revision's next cycle still revises the same decision.
    baseline = Baseline.objects.create(sprint=sprint, scoring_run=run, revises=existing.revises if existing else None)
    _record(baseline, BaselineDecisionHistory.Action.SUBMITTED, triggered_by, f'Preview: {_describe(run)}.')

    if sprint.status in _BOOTSTRAPPABLE_STATUSES:
        sprint.status = Sprint.Status.BASELINE_PENDING
        sprint.save(update_fields=['status', 'updated_at'])

    return baseline


def _require_pending(baseline):
    if baseline.status != Baseline.Status.PENDING:
        raise ValidationError(
            f"This baseline is '{baseline.status}', not 'pending' -- it has already been decided and is locked."
        )


def _require_baseline(sprint):
    baseline = _latest_baseline(sprint)
    if baseline is None:
        raise ValidationError('No baseline has been submitted for this sprint yet.')
    return baseline


def _processing_gate(sprint, baseline, override_reason):
    """Refuse a decision while included documents are failed, active, unprocessed or partially processed --
    unless the approver records why the baseline may still be decided (the override). Stores what the
    processing looked like either way, so the baseline and every report can show it."""
    from apps.extraction.services.completeness import describe, processing_summary, snapshot

    summary = processing_summary(sprint)
    reason = (override_reason or '').strip()
    if not summary['complete'] and not reason:
        raise ValidationError({
            'detail': f'{describe(summary)} Finish processing them (AI Processing Monitor: retry the failed and '
                      'partial ones), or give a reason to decide the baseline anyway.',
            'processing': snapshot(summary),
        })
    baseline.processing_snapshot = snapshot(summary)
    baseline.processing_incomplete = not summary['complete']
    baseline.processing_override_reason = reason if not summary['complete'] else ''
    return ['processing_snapshot', 'processing_incomplete', 'processing_override_reason']


def _expert_queue_gate(sprint):
    """No baseline decision while AI-QIF items wait for a Super Admin (apps/facts/aiqif_tagging.py): until then
    the coverage is provisional, and a provisional coverage must not become the official baseline."""
    from apps.facts.aiqif_tagging import queue_counts

    queue = queue_counts(sprint)
    if queue['total']:
        raise ValidationError({
            'detail': f'{queue["total"]} AI-QIF item(s) are waiting for a Super Admin (AI-QIF expert queue: '
                      f'{queue["tags"]} tag(s), {queue["facts"]} fact(s)). The AI-QIF coverage is provisional '
                      'until they are decided; the baseline can be decided after that.',
            'expert_queue': queue,
        })


def _with_override(comments, baseline):
    if not baseline.processing_incomplete:
        return comments
    note = (f'Decided with incomplete document processing: {baseline.processing_snapshot.get("description")} '
            f'Reason: {baseline.processing_override_reason}')
    return f'{comments}\n\n{note}'.strip()


def _locked_for_decision(sprint, expected_scoring_run_id, user):
    """The pending baseline, locked, pinned to the run the reviewer saw -- or BaselineChanged (after refreshing it,
    so the conflict carries the new preview). Call inside transaction.atomic()."""
    if not expected_scoring_run_id:
        raise ValidationError({'scoring_run_id': 'Send the scoring_run_id of the baseline score you reviewed.'})
    baseline = _require_baseline(sprint)
    baseline = Baseline.objects.select_for_update().select_related('scoring_run').get(pk=baseline.pk)
    _require_pending(baseline)
    if (str(baseline.scoring_run_id) != str(expected_scoring_run_id)
            or baseline.scoring_run.inputs_fingerprint != scoring_inputs_fingerprint(sprint)):
        raise BaselineChanged()
    return baseline


def _decide(sprint, user, expected_scoring_run_id, decide):
    """Refresh a stale preview (committed on its own), then decide in one locked transaction."""
    refresh_pending_baseline(sprint, user=user)
    try:
        with transaction.atomic():
            baseline = _locked_for_decision(sprint, expected_scoring_run_id, user)
            return decide(baseline)
    except BaselineChanged:
        refresh_pending_baseline(sprint, user=user)  # the data changed while we decided: show the new preview
        raise


def approve_baseline(sprint, *, user, comments='', processing_override_reason='', expected_scoring_run_id=None):
    """Full approval -- refused while any blocking gap is still unresolved
    (server-side enforcement of the same rule the frontend's approve button
    disables on; "approve provisionally" is the documented way past this).
    Approves exactly the run the reviewer saw (expected_scoring_run_id), or raises BaselineChanged."""
    return _decide(sprint, user, expected_scoring_run_id,
                   lambda baseline: _approve(sprint, baseline, user, comments, processing_override_reason))


def _approve(sprint, baseline, user, comments, processing_override_reason):
    blocking_gaps = sprint.gaps.filter(status__in=GapItem.ACTIVE_STATUSES, priority=GapItem.Priority.BLOCKING)
    if blocking_gaps.exists():
        raise ValidationError(
            f'{blocking_gaps.count()} blocking gap(s) are still unresolved -- resolve them first, '
            'or use "approve provisionally" instead.'
        )
    _expert_queue_gate(sprint)
    processing_fields = _processing_gate(sprint, baseline, processing_override_reason)

    baseline.status = Baseline.Status.APPROVED
    baseline.approved_by = user if (user and user.is_authenticated) else None
    baseline.approved_at = timezone.now()
    baseline.comments = comments
    baseline.save(update_fields=['status', 'approved_by', 'approved_at', 'comments', 'updated_at', *processing_fields])
    _record(baseline, BaselineDecisionHistory.Action.APPROVED, user, _with_override(comments, baseline))

    sprint.status = Sprint.Status.BASELINE_APPROVED
    sprint.save(update_fields=['status', 'updated_at'])
    return baseline


def approve_baseline_provisional(sprint, *, user, comments='', processing_override_reason='',
                                 expected_scoring_run_id=None):
    """Provisional approval -- unlike approve_baseline, allowed even with
    unresolved blocking gaps still open; that's the whole point of
    'provisional'. Still advances the sprint the same way full approval
    does, so the pipeline isn't blocked on data that may never fully close
    out, but the baseline's own status (and every downstream report) keeps
    the 'provisional' label rather than silently reporting it as approved.
    Approves exactly the run the reviewer saw (expected_scoring_run_id), or raises BaselineChanged."""
    return _decide(sprint, user, expected_scoring_run_id,
                   lambda baseline: _approve_provisional(sprint, baseline, user, comments, processing_override_reason))


def _approve_provisional(sprint, baseline, user, comments, processing_override_reason):
    # Provisional approval may pass unresolved gaps, but not incomplete processing without a reason.
    _expert_queue_gate(sprint)
    processing_fields = _processing_gate(sprint, baseline, processing_override_reason)

    baseline.status = Baseline.Status.PROVISIONAL
    baseline.approved_by = user if (user and user.is_authenticated) else None
    baseline.approved_at = timezone.now()
    baseline.comments = comments
    baseline.save(update_fields=['status', 'approved_by', 'approved_at', 'comments', 'updated_at', *processing_fields])
    _record(baseline, BaselineDecisionHistory.Action.APPROVED_PROVISIONAL, user, _with_override(comments, baseline))

    sprint.status = Sprint.Status.BASELINE_APPROVED
    sprint.save(update_fields=['status', 'updated_at'])
    return baseline


def open_revision(sprint, *, user, reason):
    """Replace a decided baseline the explicit way: a new PENDING cycle on the current data, linked to the decision
    it revises (`revises`). The earlier decision and its run stay exactly as they were, and reports keep using it
    until the revision itself is decided."""
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'comments': 'Give the reason for revising the decided baseline.'})
    with transaction.atomic():
        latest = _require_baseline(sprint)
        decided = Baseline.objects.select_for_update().get(pk=latest.pk)
        if decided.status not in (Baseline.Status.APPROVED, Baseline.Status.PROVISIONAL):
            raise ValidationError(f"Only a decided baseline can be revised (this one is '{decided.status}').")
        run = _current_run(sprint, scoring_inputs_fingerprint(sprint), user)
        revision = Baseline.objects.create(sprint=sprint, scoring_run=run, revises=decided)
        _record(revision, BaselineDecisionHistory.Action.SUBMITTED, user,
                f'Revision of the {decided.get_status_display().lower()} baseline decided '
                f'{decided.approved_at:%d %b %Y} on {_describe(decided.scoring_run)}. Preview: {_describe(run)}. '
                f'Reason: {reason}')
        sprint.status = Sprint.Status.BASELINE_PENDING
        sprint.save(update_fields=['status', 'updated_at'])
    return revision


def return_baseline_for_correction(sprint, *, user, comments):
    """Sends the sprint back to REVIEWING so facts/gaps can be corrected --
    the next GET .../baseline/ opens a new PENDING baseline on a run of the
    data as it is then (a fresh calculation when it changed). Requires a reason: an
    unexplained return leaves whoever owns the corrections with nothing to
    act on."""
    if not comments or not comments.strip():
        raise ValidationError({'comments': 'A reason is required when returning a baseline for correction.'})

    with transaction.atomic():
        baseline = Baseline.objects.select_for_update().get(pk=_require_baseline(sprint).pk)
        _require_pending(baseline)
        return _return(sprint, baseline, user, comments)


def _return(sprint, baseline, user, comments):
    baseline.status = Baseline.Status.RETURNED
    baseline.comments = comments
    baseline.save(update_fields=['status', 'comments', 'updated_at'])
    _record(baseline, BaselineDecisionHistory.Action.RETURNED, user, comments)

    sprint.status = Sprint.Status.REVIEWING
    sprint.save(update_fields=['status', 'updated_at'])
    return baseline
