"""Display copies of capability runs: what the run list and the run detail read (issue 60).

On the live server the run list took about 36 s and each run detail 25-35 s, and nearly every screen calls both.
The list read every run's whole inputs (every frozen page's text); the detail read the 40 MB completed payload three
times, hashed it and the inputs on every request, and dropped the model traces only at the end.

The copy (CapabilityRunView) is derived data, never history:
- its list fields are written when the run is created (inputs are in memory then);
- `assessment` (the completed payload without traces), its digest and the diagnostics are written when the
  completed event is saved (the payload is in memory then);
- anything missing (runs from before migration 0020, or a write that failed) is rebuilt from the run on first read.
A failure here never stops a run: the event is saved first, and the copy is rebuilt from it.

The version marker (`marker`) names everything a detail response depends on that can change after the run is
written: the newest event, the newest stored explanations, whether the follow-up stage is closed, the execution
ledger (status, heartbeat, reservations), and the code and settings that shape the response. The front end reuses
its copy of a run only while the marker is unchanged.
"""
import hashlib
import logging
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.db.models.fields.json import KT
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.scoring.models import CapabilityExplanation, CapabilityRun, CapabilityRunEvent, CapabilityRunView
from .storage import digest

logger = logging.getLogger(__name__)
SCORING = Path(__file__).resolve().parent.parent


def light(payload):
    """The completed payload as screens read it: everything except the model traces."""
    return {k: v for k, v in (payload or {}).items() if k != 'traces'}


def list_fields(inputs):
    inputs = inputs or {}
    second = inputs.get('second_layer')
    protocol = inputs.get('assessment_protocol') or {}
    return {'stage': 'final' if isinstance(second, dict) else 'provisional',
            'provisional_run_id': (second.get('provisional_run_id') or '') if isinstance(second, dict) else '',
            'refines_run_id': inputs.get('refines_run_id') or '',
            'rubric_version': str((inputs.get('rubric') or {}).get('version') or '')[:200],
            'engine_version': str(inputs.get('engine_version') or '')[:200],
            'prompt_version': str(protocol.get('prompt_version') or '')[:200],
            'retrieval_version': str(protocol.get('retrieval_version') or '')[:200],
            'reference_period': inputs.get('reference_period') or ''}


@lru_cache(maxsize=None)
def _files_digest(paths):
    h = hashlib.sha256()
    for path in paths:
        h.update(str(path.relative_to(SCORING)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


@lru_cache(maxsize=1)
def code_fingerprint():
    """The scoring app's code, rubric files and report templates, plus the settings that shape a run's response.
    A deploy that changes any of them changes every run's marker (so screens refetch once), never the data."""
    paths = tuple(sorted(p for p in SCORING.rglob('*') if p.is_file() and p.suffix in {'.py', '.json', '.html'}
                         and 'migrations' not in p.parts and not p.name.startswith('test')))
    names = ('CAPABILITY_STALE_SECONDS', 'CAPABILITY_ASSESSMENT_ENABLED', 'DEPTH_CREDIT_MODE', 'DEPTH_CREDIT_SHARE')
    return digest([_files_digest(paths), {n: str(getattr(settings, n, None)) for n in names}])[:24]


@lru_cache(maxsize=1)
def diagnostics_key():
    """The code diagnostics.explain() runs (it and the capability modules it imports, transitively). Kept narrow so a
    deploy that leaves them unchanged doesn't make every run's first open rebuild its diagnostics."""
    import re
    here = Path(__file__).resolve().parent
    seen, todo = set(), ['diagnostics']
    while todo:
        name = todo.pop()
        path = here / f'{name}.py'
        if name in seen or not path.exists():
            continue
        seen.add(name)
        todo += re.findall(r'from \.(\w+) import', path.read_text())
    return _files_digest(tuple(sorted(here / f'{n}.py' for n in seen)))[:24]


# --- writing the copy ---------------------------------------------------------------------------------------------

@receiver(post_save, sender=CapabilityRun, dispatch_uid='capability_run_view_create')
def _run_created(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        CapabilityRunView.objects.update_or_create(run_id=instance.pk, defaults=list_fields(instance.inputs))


@receiver(post_save, sender=CapabilityRunEvent, dispatch_uid='capability_run_view_event')
def _event_created(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    payload = instance.payload or {}
    if instance.state == 'partial' and payload.get('kind') == 'indicator':
        CapabilityRunView.objects.filter(run_id=instance.run_id).update(indicators_done=F('indicators_done') + 1)
    elif instance.state == 'completed' and 'result' in payload:
        try:
            with transaction.atomic():   # a savepoint: a failure here must never abort the publishing transaction
                run = instance.run
                CapabilityRunView.objects.update_or_create(run_id=run.pk, defaults={
                    **list_fields(run.inputs), **_completed_fields(run, instance)})
        except Exception:
            logger.exception('run view: could not store the copy of run %s; it is rebuilt on first read',
                             instance.run_id)


def _completed_fields(run, event):
    from .diagnostics import explain
    payload = event.payload
    return {'event_id': event.pk, 'assessment': light(payload), 'assessment_hash': digest(payload),
            'verified': digest(run.inputs) == run.inputs_hash and payload.get('inputs_hash') == run.inputs_hash,
            'diagnostics': explain(run.inputs, payload), 'diagnostics_key': diagnostics_key()}


def rebuild(run_id):
    """Rebuild a run's copy from the run itself: reads the inputs and the completed payload once."""
    run = CapabilityRun.objects.get(pk=run_id)
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    done = sum(1 for p in run.events.filter(state='partial').values_list('payload__kind', flat=True)
               if p == 'indicator')
    fields = {**list_fields(run.inputs), 'indicators_done': done}
    fields.update(_completed_fields(run, event) if event else
                  {'event_id': None, 'assessment': None, 'assessment_hash': '', 'verified': False, 'diagnostics': None,
                   'diagnostics_key': ''})
    view, _ = CapabilityRunView.objects.update_or_create(run_id=run.pk, defaults=fields)
    return view


def _completed_event_id(run_id):
    return (CapabilityRunEvent.objects.filter(run_id=run_id, state='completed', payload__result__isnull=False)
            .order_by('id').values_list('id', flat=True).last())


def ensure(run_id, *, complete=True):
    """The run's copy, rebuilt where it is missing or out of date. `complete`: the detail needs the completed parts
    (the copy of the payload, its digest, the diagnostics); the list needs only the list fields."""
    view = CapabilityRunView.objects.filter(run_id=run_id).first()
    if view is None:
        if not complete:
            # The list fields alone, read inside the database (never the whole inputs).
            row = CapabilityRun.objects.filter(pk=run_id).values(
                second=KT('inputs__second_layer__provisional_run_id'), refines=KT('inputs__refines_run_id'),
                rubric=KT('inputs__rubric__version'), engine=KT('inputs__engine_version'),
                prompt=KT('inputs__assessment_protocol__prompt_version'),
                retrieval=KT('inputs__assessment_protocol__retrieval_version'),
                period=KT('inputs__reference_period')).first()
            done = sum(1 for p in CapabilityRunEvent.objects.filter(run_id=run_id, state='partial')
                       .values_list('payload__kind', flat=True) if p == 'indicator')
            view, _ = CapabilityRunView.objects.get_or_create(run_id=run_id, defaults={
                'stage': 'final' if row['second'] else 'provisional', 'provisional_run_id': row['second'] or '',
                'refines_run_id': row['refines'] or '', 'rubric_version': (row['rubric'] or '')[:200],
                'engine_version': (row['engine'] or '')[:200], 'prompt_version': (row['prompt'] or '')[:200],
                'retrieval_version': (row['retrieval'] or '')[:200], 'reference_period': row['period'] or '',
                'indicators_done': done})
            return view
        return rebuild(run_id)
    if complete:
        stale = view.event_id is None and _completed_event_id(run_id) is not None
        unfinished = view.event_id is not None and (view.assessment is None or not view.assessment_hash
                                                    or view.diagnostics_key != diagnostics_key())
        if stale or unfinished:
            return rebuild(run_id)
    return view


# --- reading ----------------------------------------------------------------------------------------------------

def final_run_id(provisional_run_id):
    """The newest final result published from this provisional run: layer2_service.final_run_id, read from the
    display copies' column. Where any run lacks its copy, the authoritative lookup in the run inputs is used."""
    found = (CapabilityRunView.objects.filter(provisional_run_id=str(provisional_run_id))
             .order_by('-run__created_at').values_list('run_id', flat=True).first())
    if found is None and CapabilityRun.objects.filter(view__isnull=True).exists():
        from .layer2_service import final_run_id as by_inputs
        return by_inputs(provisional_run_id)
    return found


def explanation_row(run_id, event_id):
    """The newest stored explanations for the completed event (explanations.latest), without reading the event."""
    if event_id is None:
        return None
    return (CapabilityExplanation.objects.filter(run_id=run_id, event_id=event_id).order_by('-created_at')
            .values('pk', 'payload').first())


def _explanation_id(run_id, event_id):
    if event_id is None:
        return None
    return (CapabilityExplanation.objects.filter(run_id=run_id, event_id=event_id).order_by('-created_at')
            .values_list('pk', flat=True).first())


def closed(view):
    if view.stage == 'final':
        return True
    return final_run_id(view.run_id) is not None


def marker(execution, view, stalled, mode):
    """The version marker of one run's detail response (also its ETag)."""
    last_event = (CapabilityRunEvent.objects.filter(run_id=execution.run_id).order_by('-id')
                  .values_list('id', flat=True).first())
    final = None if view.stage == 'final' else final_run_id(view.run_id)
    return digest([str(execution.run_id), execution.status, execution.heartbeat_at.isoformat(),
                   execution.requests_reserved, str(execution.usd_reserved), bool(stalled), last_event,
                   str(_explanation_id(execution.run_id, view.event_id)), view.stage, str(final),
                   view.event_id, code_fingerprint(), mode])[:32]


def inputs_part(run_id, *keys):
    """Some top-level keys of a run's inputs, extracted in the database (never the whole inputs)."""
    from django.db.models.fields.json import KeyTransform
    return CapabilityRun.objects.filter(pk=run_id).values(**{k: KeyTransform(k, 'inputs') for k in keys}).first()


def plan(run, view, parts):
    """The deterministic plan (recommendations.build_inputs) from the copy: the integrity check was made once, when
    the copy was written. Without reviewed evidence and scope (the full detail and the reports carry those)."""
    from .recommendations import build_inputs
    shim_run = SimpleNamespace(pk=run.pk, inputs_hash=run.inputs_hash, inputs=parts)
    shim_event = SimpleNamespace(pk=view.event_id, payload=view.assessment)
    built = build_inputs(shim_run, shim_event, {}, verified_assessment_hash=view.assessment_hash)
    for key in ('reviewed_evidence', 'scope'):
        built.pop(key, None)
    return built
