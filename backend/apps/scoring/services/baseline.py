"""Baseline approval workflow -- see apps.scoring.models.Baseline.

Bootstraps, approves, provisionally approves, and returns-for-correction a
sprint's CRI baseline, reusing the existing scoring engine
(`cri_engine.build_score_snapshot`) for whatever ScoringRun a baseline
decision gets pinned to, rather than recomputing anything here.
"""
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.gaps.models import GapItem
from apps.sprints.models import Sprint

from ..models import Baseline, BaselineDecisionHistory
from .cri_engine import build_score_snapshot

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


def get_or_create_pending_baseline(sprint, *, triggered_by=None):
    """Return the sprint's current baseline decision-cycle, bootstrapping a
    new PENDING one (against a freshly-guaranteed ScoringRun) if none is
    currently open -- i.e. the sprint has never submitted a baseline, or its
    last one was RETURNED. Advances the sprint to BASELINE_PENDING the first
    time this fires, from REVIEWING or SCORING -- the same "a GET can have a
    legitimate bootstrap side effect" pattern
    apps.scoring.services.cri_engine.build_score_snapshot already uses for
    ScoringRun itself.
    """
    existing = _latest_baseline(sprint)
    if existing is not None and existing.status != Baseline.Status.RETURNED:
        return existing

    build_score_snapshot(sprint, bootstrap=True)  # guarantees a ScoringRun exists
    latest_run = sprint.scoring_runs.order_by('-created_at').first()

    baseline = Baseline.objects.create(sprint=sprint, scoring_run=latest_run)
    _record(baseline, BaselineDecisionHistory.Action.SUBMITTED, triggered_by, '')

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


def approve_baseline(sprint, *, user, comments=''):
    """Full approval -- refused while any blocking gap is still unresolved
    (server-side enforcement of the same rule the frontend's approve button
    disables on; "approve provisionally" is the documented way past this)."""
    baseline = _require_baseline(sprint)
    _require_pending(baseline)

    blocking_gaps = sprint.gaps.filter(status__in=GapItem.ACTIVE_STATUSES, priority=GapItem.Priority.BLOCKING)
    if blocking_gaps.exists():
        raise ValidationError(
            f'{blocking_gaps.count()} blocking gap(s) are still unresolved -- resolve them first, '
            'or use "approve provisionally" instead.'
        )

    baseline.status = Baseline.Status.APPROVED
    baseline.approved_by = user if (user and user.is_authenticated) else None
    baseline.approved_at = timezone.now()
    baseline.comments = comments
    baseline.save(update_fields=['status', 'approved_by', 'approved_at', 'comments', 'updated_at'])
    _record(baseline, BaselineDecisionHistory.Action.APPROVED, user, comments)

    sprint.status = Sprint.Status.BASELINE_APPROVED
    sprint.save(update_fields=['status', 'updated_at'])
    return baseline


def approve_baseline_provisional(sprint, *, user, comments=''):
    """Provisional approval -- unlike approve_baseline, allowed even with
    unresolved blocking gaps still open; that's the whole point of
    'provisional'. Still advances the sprint the same way full approval
    does, so the pipeline isn't blocked on data that may never fully close
    out, but the baseline's own status (and every downstream report) keeps
    the 'provisional' label rather than silently reporting it as approved."""
    baseline = _require_baseline(sprint)
    _require_pending(baseline)

    baseline.status = Baseline.Status.PROVISIONAL
    baseline.approved_by = user if (user and user.is_authenticated) else None
    baseline.approved_at = timezone.now()
    baseline.comments = comments
    baseline.save(update_fields=['status', 'approved_by', 'approved_at', 'comments', 'updated_at'])
    _record(baseline, BaselineDecisionHistory.Action.APPROVED_PROVISIONAL, user, comments)

    sprint.status = Sprint.Status.BASELINE_APPROVED
    sprint.save(update_fields=['status', 'updated_at'])
    return baseline


def return_baseline_for_correction(sprint, *, user, comments):
    """Sends the sprint back to REVIEWING so facts/gaps can be corrected --
    a fresh scoring run and a fresh GET .../baseline/ call are required to
    submit a new baseline decision-cycle afterward. Requires a reason: an
    unexplained return leaves whoever owns the corrections with nothing to
    act on."""
    if not comments or not comments.strip():
        raise ValidationError({'comments': 'A reason is required when returning a baseline for correction.'})

    baseline = _require_baseline(sprint)
    _require_pending(baseline)

    baseline.status = Baseline.Status.RETURNED
    baseline.comments = comments
    baseline.save(update_fields=['status', 'comments', 'updated_at'])
    _record(baseline, BaselineDecisionHistory.Action.RETURNED, user, comments)

    sprint.status = Sprint.Status.REVIEWING
    sprint.save(update_fields=['status', 'updated_at'])
    return baseline
