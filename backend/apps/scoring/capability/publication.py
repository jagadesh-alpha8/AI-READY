"""Which result a college sees, and whether its reports are ready (build brief, part A; audit finding 5).

The published result. Since 26 Nov 2026 (Siddharth: "shouldn't the report be auto generated post sprint?") results
publish themselves (CAPABILITY_AUTO_PUBLISH, on by default; keep_going below): when a Stage 1 run completes, and after
every second-layer job of it, the result the college should see (the final result once there is one, else the Stage 1
run) has its report text written, one job at a time (next steps, then explanations), and is published as soon as its
reports pass the draft gate below; a published Stage 1 result then has its follow-up questions planned, and depth
answers judged as they are checked (_follow_up). A Stage 1 result never replaces a published final result, and once staff withdraw
a result nothing is published automatically until staff publish one again. Staff can still publish an older result or
withdraw one. Every choice is a CapabilityPublication row (published_by empty when automatic); the newest row of a
sprint is the current one, and a row with no run withdraws it. A college login (any role that is not InGage staff) may read a completed run only when
it is the published run or, when that run is a final result, its Stage 1 run (the Reports page offers both, and the
follow-up questions belong to the Stage 1 run). Runs that have not completed carry no score and stay readable, so
a college still sees its own run in progress. Staff read every run.

The draft gate. A run's summary and detailed reports are ready when, for its completed assessment:
- the score explanations are stored, written by the current version, and no area's text is the plain fallback;
- the next steps are stored, written by the current version, and every step the reports show was written for the
  college (none is on the plain checklist).
A requirement's or key indicator's explanation on plain wording is a warning, not a block: its fallback is still a
true sentence, and a rule with no fallback anywhere would keep nearly every detailed report a draft. A college login
cannot download a report that is not ready; staff can, and it is marked Draft on every page.
"""
import logging

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

NOT_PUBLISHED = 'This result has not been published to your institution yet.'
READINESS_CACHE_SECONDS = 7 * 24 * 3600
THIN_STEPS = 3   # this many "start" steps (nothing in the documents to build on) earns staff a warning
AUTO_NOTE = 'Published automatically: its reports passed the draft checks.'


class PublicationError(ValueError):
    pass


def is_staff(user):
    return bool(getattr(user, 'is_cross_institution', False))


# ------------------------------------------------------------------ the published result

def current(sprint_id):
    """The sprint's newest publication row, or None when nothing was ever published."""
    from apps.scoring.models import CapabilityPublication
    return (CapabilityPublication.objects.filter(sprint_id=sprint_id).select_related('published_by')
            .order_by('-id').first())


def published_run_id(sprint_id):
    row = current(sprint_id)
    return str(row.run_id) if row and row.run_id else None


def _stage_of(run_id):
    """(stage, provisional run id) from the run's display copy, never its inputs."""
    from .run_view import ensure
    view = ensure(run_id, complete=False)
    return view.stage, (view.provisional_run_id or None) if view.stage == 'final' else None


def describe(row):
    """The current publication as the run list and the staff panel show it, or None when nothing is published."""
    if row is None or row.run_id is None:
        return None
    stage, provisional = _stage_of(row.run_id)
    user = row.published_by
    return {'run_id': str(row.run_id), 'stage': stage, 'provisional_run_id': provisional,
            'published_at': row.created_at, 'published_by': (user.get_full_name() or user.email) if user else None,
            'note': row.note}


def visible_run_ids(sprint_id):
    """The completed runs a college login may read: the published run and, for a final result, its Stage 1 run."""
    run_id = published_run_id(sprint_id)
    if run_id is None:
        return set()
    stage, provisional = _stage_of(run_id)
    return {run_id, provisional} if provisional else {run_id}


def require_visible(user, execution):
    """Refuse a college login a completed run that is not published to it (PermissionDenied). Staff read every run;
    runs that have not completed carry no score and stay readable."""
    if is_staff(user) or execution.status != 'completed':
        return
    if str(execution.run_id) not in visible_run_ids(execution.sprint_id):
        raise PermissionDenied(NOT_PUBLISHED)


def publish(sprint, run_id, user, note=''):
    """Make a completed run the sprint's published result, or withdraw the published one (run_id None). Returns
    (row, changed). Publishing the run already published changes nothing."""
    from apps.scoring.models import CapabilityExecution, CapabilityPublication
    from apps.sprints.models import Sprint
    note = (note or '').strip()[:500]
    with transaction.atomic():
        Sprint.objects.select_for_update().get(pk=sprint.pk)   # two staff publishing at once: one after the other
        now = current(sprint.pk)
        if run_id is None:
            if now is None or now.run_id is None:
                return now, False
            return CapabilityPublication.objects.create(sprint=sprint, run=None, published_by=user, note=note), True
        execution = (CapabilityExecution.objects.filter(run_id=run_id, sprint=sprint).select_related('run')
                     .defer('run__inputs').first())
        if execution is None:
            raise PublicationError('This run is not part of this assessment.')
        from .run_view import ensure
        if execution.status != 'completed' or ensure(execution.run_id).event_id is None:
            raise PublicationError('Only a completed assessment can be published.')
        if now is not None and str(now.run_id) == str(run_id):
            return now, False
        return CapabilityPublication.objects.create(sprint=sprint, run=execution.run, published_by=user,
                                                    note=note), True


def history(sprint_id, limit=20):
    from apps.scoring.models import CapabilityPublication
    rows = CapabilityPublication.objects.filter(sprint_id=sprint_id).select_related('published_by').order_by('-id')
    return [{'run_id': str(r.run_id) if r.run_id else None, 'withdrawn': r.run_id is None,
             'at': r.created_at, 'by': (r.published_by.get_full_name() or r.published_by.email) if r.published_by else None,
             'note': r.note} for r in rows[:limit]]


# ------------------------------------------------------------------ the draft gate

def _cache():
    from django.core.cache import cache
    return cache


def readiness(execution):
    """Whether the run's summary and detailed reports are ready for the college (module docstring).

    {'ready', 'reasons': [why not], 'warnings': [what staff may want to fix], 'explanations': {...},
     'next_steps': {...}}. Kept in the cache under everything it depends on: the completed event, the newest stored
    explanations and next steps, and the deployed code."""
    from .run_view import _explanation_id, _next_steps_id, code_fingerprint, ensure
    from .storage import digest
    view = ensure(execution.run_id)
    if execution.status != 'completed' or view.event_id is None:
        return {'ready': False, 'reasons': ['The assessment has not completed.'], 'warnings': [],
                'explanations': None, 'next_steps': None}
    key = 'capability-readiness:' + digest([str(execution.run_id), view.event_id,
                                            str(_explanation_id(execution.run_id, view.event_id)),
                                            str(_next_steps_id(execution.run_id, view.event_id)), code_fingerprint()])
    try:
        cached = _cache().get(key)
    except Exception:   # the cache server is down: work it out as below
        cached = None
    if cached is not None:
        return cached
    out = _readiness(execution, view)
    try:
        _cache().set(key, out, READINESS_CACHE_SECONDS)
    except Exception:
        logger.warning('readiness cache unavailable', exc_info=True)
    return out


def _readiness(execution, view):
    from . import explanations, next_steps
    from .run_view import explanation_row, inputs_part, plan
    reasons, warnings = [], []

    row = explanation_row(execution.run_id, view.event_id)
    written = (row or {}).get('payload') or None
    exp = {'written': bool(written), 'version': (written or {}).get('version'), 'areas_on_plain_wording': [],
           'others_on_plain_wording': 0}
    if not written:
        reasons.append('The score explanations have not been written.')
    elif written.get('version') != explanations.VERSION:
        reasons.append(f"The score explanations were written by an earlier version ({written.get('version')}); "
                       'write them again.')
    else:
        exp['areas_on_plain_wording'] = sorted(code for code, entry in (written.get('areas') or {}).items()
                                               if (entry or {}).get('fallback'))
        exp['others_on_plain_wording'] = sum(1 for part in ('indicators', 'requirements')
                                             for entry in (written.get(part) or {}).values()
                                             if (entry or {}).get('fallback'))
        if exp['areas_on_plain_wording']:
            n = len(exp['areas_on_plain_wording'])
            reasons.append(f"The text of {n} area{'s' if n != 1 else ''} is on plain wording; write the explanations "
                           'again.')
        if exp['others_on_plain_wording']:
            n = exp['others_on_plain_wording']
            warnings.append(f"{n} practice or topic explanation{'s are' if n != 1 else ' is'} on plain wording.")
        topics = [e for e in (written.get('indicators') or {}).values() if e and not e.get('fallback')]
        unwritten = sum(1 for e in topics if not e.get('verdict'))
        if unwritten:
            warnings.append(f"{unwritten} topic verdict{'s are' if unwritten != 1 else ' is'} missing; the detailed "
                            'report prints those topics\' plain line.')

    steps_id, steps = next_steps.stored(execution.run_id, view.event_id)
    parts = inputs_part(execution.run_id, 'population', 'profile', 'manifest', 'rubric', 'reference_period',
                        'retrieval_policy')
    try:
        shown = next_steps.for_screens(execution.run_id, view.event_id, view.assessment, parts['manifest'],
                                       parts['profile'], plan(execution.run, view, parts), view.stage == 'final',
                                       view.provisional_run_id or None)
    except Exception:   # a run shaped in a way the reports don't expect: they can't be ready
        logger.exception('readiness: the next steps could not be shaped for run %s', execution.run_id)
        reasons.append('The steps the reports show could not be worked out for this run.')
        return {'ready': False, 'reasons': reasons, 'warnings': warnings, 'explanations': exp, 'next_steps': None}
    actions = shown['actions']
    unwritten = [a['key'] for a in actions if not a.get('generated')]
    starts = [a for a in actions if a.get('generated') and a.get('kind') == 'start']
    if len(starts) >= THIN_STEPS:
        # Nothing in the documents to build on for several areas: usually the documents, not the college (only
        # accreditation documents sent, no operational records). Worth asking before the report goes out.
        warnings.append(f"{len(starts)} of the {len(actions)} steps start from nothing in the documents "
                        f"({', '.join(a['area'] for a in starts)}). Consider asking the college for its operational "
                        'records in those areas before publishing.')
    if written and written.get('version') == explanations.VERSION:
        # A weak area's card lists its step's starting points (presentation.card_view); text written before the step
        # could not see them, so its verdict may name other things (explanations-0.5).
        from .presentation import CLOSEST_BELOW
        scores = {p.get('code'): p.get('score') for p in
                  (((view.assessment or {}).get('result') or {}).get('documented') or {}).get('pillars') or []}
        stale = [a['area'] for a in actions if a.get('generated') and a.get('kind') != 'start'
                 and (scores.get(a.get('area_code')) or 0) < CLOSEST_BELOW
                 and not ((written.get('areas') or {}).get(a.get('area_code')) or {}).get('closest_seen')]
        if stale:
            warnings.append(f"The card text of {', '.join(stale)} was written before its next step, so it may not "
                            "match the starting points the card lists: write the explanations again.")
    st = {'written': steps is not None, 'version': (steps or {}).get('version'), 'steps': len(actions),
          'written_steps': len(actions) - len(unwritten), 'start_steps': len(starts)}
    if actions and steps is None:
        reasons.append('The next steps have not been written.')
    elif actions and steps.get('version') != next_steps.VERSION:
        reasons.append(f"The next steps were written by an earlier version ({steps.get('version')}); write them "
                       'again.')
    elif unwritten:
        n = len(unwritten)
        reasons.append(f"{n} of the {len(actions)} next steps {'are' if n != 1 else 'is'} on the plain checklist; "
                       'write the next steps again.')
    return {'ready': not reasons, 'reasons': reasons, 'warnings': warnings, 'explanations': exp, 'next_steps': st}


# ------------------------------------------------------------------ publishing by itself

def automatic():
    return bool(getattr(settings, 'CAPABILITY_AUTO_PUBLISH', True))


def shown_target(provisional_run_id):
    """The run the college should see for a Stage 1 run: its final result once published, else the Stage 1 run."""
    from .layer2_service import final_run_id
    return final_run_id(str(provisional_run_id)) or str(provisional_run_id)


def publish_if_ready(run_id):
    """Publish a completed run by itself when its reports pass the draft gate. Returns the new row, or None when it
    is not ready, already published, would replace a final result with a Stage 1 one, or staff withdrew the result."""
    from apps.scoring.models import CapabilityExecution
    if not automatic():
        return None
    execution = (CapabilityExecution.objects.filter(run_id=run_id).select_related('sprint', 'run')
                 .defer('run__inputs').first())
    if execution is None or execution.status != 'completed' or not readiness(execution)['ready']:
        return None
    now = current(execution.sprint_id)
    if now is not None:
        if now.run_id is None and now.published_by_id is not None:
            return None   # staff withdrew the result: they choose the next one
        if str(now.run_id) == str(run_id):
            return None
        if now.run_id is not None and _stage_of(now.run_id)[0] == 'final' and _stage_of(run_id)[0] != 'final':
            return None   # never back from a final result to a Stage 1 one
    try:
        row, changed = publish(execution.sprint, str(run_id), None, AUTO_NOTE)
    except PublicationError:
        logger.warning('automatic publication refused for run %s', run_id, exc_info=True)
        return None
    if changed:
        logger.info('Run %s published automatically for sprint %s', run_id, execution.sprint_id)
    return row if changed else None


def keep_going(provisional_run):
    """After a Stage 1 run completes, or any second-layer job of it completes: write what the shown result's reports
    still need, one job at a time, or publish it when they pass the draft gate. Never raises: the work that called it
    has already succeeded. A job that ends with text still on plain wording stops the chain (its readiness says why);
    each job is keyed by run and event, so the same job is never queued twice."""
    if not automatic():
        return None
    try:
        return _keep_going(provisional_run)
    except Exception:
        logger.exception('automatic publication: could not continue for run %s', getattr(provisional_run, 'pk', None))
        return None


def _keep_going(provisional_run):
    from apps.scoring.models import CapabilityExecution
    from . import explanations, next_steps
    from .execution import AssessmentConflict, AssessmentDisabled
    from .layer2_service import is_final
    from .run_view import ensure
    from .second_layer_jobs import enabled, start
    from rest_framework.exceptions import ValidationError
    if is_final(provisional_run):
        return None
    target = shown_target(provisional_run.pk)
    execution = CapabilityExecution.objects.filter(run_id=target).defer('run__inputs').first()
    if execution is None or execution.status != 'completed':
        return None
    state = readiness(execution)
    if state['ready']:
        row = publish_if_ready(target)
        if target == str(provisional_run.pk):
            return _follow_up(provisional_run, execution) or row
        return row
    exp, steps = state.get('explanations') or {}, state.get('next_steps') or {}
    # The next steps first: a weak area's card text is written from its step's starting points (explanations-0.5).
    if steps and (not steps.get('written') or steps.get('version') != next_steps.VERSION):
        operation = 'next_steps'
    elif not exp.get('written') or exp.get('version') != explanations.VERSION:
        operation = 'explain'
    else:
        return None   # written by the current versions but still not ready (text on plain wording): staff decide
    if not enabled():
        return None
    final = target != str(provisional_run.pk)
    event = ensure(target).event_id
    try:
        with transaction.atomic():   # start() locks the run
            job, _ = start(run=provisional_run, operation=operation, user=None,
                           key=f'auto-{operation}-{target}-{event}', options={'final': final})
        return job
    except AssessmentConflict:
        return None   # another job is running; its own completion continues from here
    except (AssessmentDisabled, ValidationError) as exc:
        logger.warning('automatic publication: %s could not start for run %s: %s', operation, provisional_run.pk,
                       getattr(exc, 'detail', exc))
        return None


def _follow_up(provisional_run, execution):
    """The follow-up stage runs itself too (26 Nov, with automatic publication): once the college sees its Stage 1
    result, its questions are planned; and depth answers checked since the last judging are judged, so that closing
    the stage (the college's "finish") never waits on a staff step. Nothing once the stage is closed or the result
    withdrawn. One job at a time: a busy run continues from that job's own completion."""
    from django.db.models import Max
    from apps.scoring.models import DepthQuestion, DepthResponse, SecondLayerJob
    from .execution import AssessmentConflict, AssessmentDisabled
    from .layer2_service import stage_closed
    from .second_layer_jobs import enabled, start
    from rest_framework.exceptions import ValidationError
    if not enabled() or stage_closed(provisional_run) or \
            str(published_run_id(execution.sprint_id) or '') != str(provisional_run.pk):
        return None
    run_ref = str(provisional_run.pk)
    if not DepthQuestion.objects.filter(run_ref=run_ref).exists():
        operation, key, options = 'questions', f'auto-questions-{run_ref}', {}
    else:
        latest = DepthResponse.objects.filter(question__run_ref=run_ref, question__kind=DepthQuestion.Kind.DEPTH,
                                              status=DepthResponse.Status.CHECKED).aggregate(x=Max('created_at'))['x']
        judged = SecondLayerJob.objects.filter(run=provisional_run, operation='depth', status='completed').aggregate(
            x=Max('finished_at'))['x']
        if latest is None or (judged is not None and judged >= latest):
            return None
        operation, key, options = 'depth', f'auto-depth-{run_ref}-{latest.isoformat()}', {}
    try:
        with transaction.atomic():
            job, _ = start(run=provisional_run, operation=operation, user=None, key=key, options=options)
        return job
    except AssessmentConflict:
        return None
    except (AssessmentDisabled, ValidationError) as exc:
        logger.warning('automatic follow-up: %s could not start for run %s: %s', operation, run_ref,
                       getattr(exc, 'detail', exc))
        return None
