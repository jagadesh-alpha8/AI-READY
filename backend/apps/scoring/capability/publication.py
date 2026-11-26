"""Which result a college sees, and whether its reports are ready (build brief, part A; audit finding 5).

The published result. InGage staff choose which completed run of a sprint its college sees; nothing is published by
itself, a final result included (a final result's text is written after it is published, so it would show the plain
fallback first). Every choice is a CapabilityPublication row; the newest row of a sprint is the current one, and a
row with no run withdraws it. A college login (any role that is not InGage staff) may read a completed run only when
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

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

NOT_PUBLISHED = 'This result has not been published to your institution yet.'
READINESS_CACHE_SECONDS = 7 * 24 * 3600
THIN_STEPS = 3   # this many "start" steps (nothing in the documents to build on) earns staff a warning


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
