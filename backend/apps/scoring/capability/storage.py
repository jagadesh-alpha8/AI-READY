"""Tenant-scoped frozen evidence and atomic, append-only capability publication.

No inference here. Callers must authorize the institution before using these internal
services; matching institution/sprint IDs additionally prevents cross-tenant sources.
Carry-over is explicit: only current documents in this sprint are included. Renamed
replacements must use existing version lineage; never guess replacement by content.
"""
import hashlib
import json

from django.db import transaction

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.scoring.models import CapabilityRun, CapabilityRunEvent
from apps.sprints.models import Sprint
from .engine import ENGINE_VERSION, assess, release
from .evaluation import validate_decisions
from .planning import actions_for, roadmap


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def evidence_snapshot(sprint):
    manifest, sources = [], []
    documents = Document.objects.filter(sprint=sprint, superseded_at__isnull=True).exclude(
        status=Document.Status.REJECTED).order_by('id')
    for document in documents:
        pages = list(DocumentPage.objects.filter(document=document).order_by('page_number'))
        manifest.append({'document_id': str(document.pk), 'filename': document.original_filename,
                         'checksum': document.checksum, 'version': document.version_number,
                         'previous_version_id': str(document.previous_version_id) if document.previous_version_id else None,
                         'status': document.status, 'expected_pages': document.page_count,
                         'pages': [{'page_id': str(p.pk), 'number': p.page_number, 'status': p.status,
                                    'text_hash': digest(p.text), 'text_source': p.text_source} for p in pages]})
        for page in pages:
            if page.status == DocumentPage.Status.OK and page.text.strip():
                sources.append({'id': str(page.pk), 'document_id': str(document.pk),
                                'page_number': page.page_number, 'text': page.text,
                                'text_source': page.text_source})
    return manifest, sources


@transaction.atomic
def create_run(*, institution_id, sprint_id, population, reference_period, execution_policy=None):
    if not isinstance(population, str) or not population.strip() or not isinstance(reference_period, str) or not reference_period.strip():
        raise ValueError('Population and reference period are required.')
    sprint = Sprint.objects.select_related('institution').get(pk=sprint_id, institution_id=institution_id)
    institution = sprint.institution
    manifest, sources = evidence_snapshot(sprint)
    rubric = release()
    inputs = {'institution_id': str(institution.pk), 'sprint_id': str(sprint.pk),
              'profile': {'name': institution.name, 'institution_type': institution.institution_type,
                          'student_count': institution.student_count, 'faculty_count': institution.faculty_count},
              'population': population, 'reference_period': reference_period,
              'carry_over_policy': 'current_sprint_only_explicit_document_lineage',
              'rubric': rubric, 'rubric_snapshot_hash': digest(rubric),
              'engine_version': ENGINE_VERSION, 'manifest': manifest, 'sources': sources,
              'execution_policy': execution_policy or {}}
    run = CapabilityRun.objects.create(sprint=sprint, inputs=inputs, inputs_hash=digest(inputs))
    CapabilityRunEvent.objects.create(run=run, state='queued')
    return run


@transaction.atomic
def checkpoint(*, institution_id, run_id, state, payload=None):
    run = CapabilityRun.objects.select_for_update().get(pk=run_id, sprint__institution_id=institution_id)
    previous = run.events.last().state
    transitions = {'queued': {'running', 'failed', 'cancelled'},
                   'running': {'partial', 'completed', 'failed', 'cancelled'},
                   'partial': {'partial', 'completed', 'failed', 'cancelled'}}
    if state not in transitions.get(previous, set()):
        raise ValueError('Invalid capability run transition.')
    # Never persist raw provider exception messages. Diagnostics use fixed codes.
    if state in {'failed', 'cancelled'}:
        payload = {'error_code': 'evaluation_failed' if state == 'failed' else 'cancelled',
                   'next_action': 'Start a new run to reassess the frozen evidence.'}
    elif state == 'completed':
        raise ValueError('Use publish to atomically validate and complete a run.')
    return CapabilityRunEvent.objects.create(run=run, state=state, payload=payload or {})


@transaction.atomic
def publish(*, institution_id, run_id, evaluation, inference):
    """Publish one coherent result; citations revalidated against frozen tenant pages.

    Inference must be captured by the provider wrapper (actual identity/settings and
    per-HTTP-call usage, including retries); the async wrapper is implemented in step 3.
    """
    run = CapabilityRun.objects.select_for_update().get(pk=run_id, sprint__institution_id=institution_id)
    if run.events.last().state not in {'running', 'partial'}:
        raise ValueError('Only an active run can be published.')
    if digest(run.inputs) != run.inputs_hash:
        raise ValueError('Frozen input integrity check failed.')
    if not all(key in inference for key in ('provider', 'model', 'settings', 'calls')):
        raise ValueError('Actual inference identity, settings and per-call usage are required.')
    frozen = {s['id']: s for s in run.inputs['sources']}
    for trace in evaluation.get('traces', []):
        if any(sid not in frozen for sid in trace.get('source_ids', [])):
            raise ValueError('Trace references a source outside this run.')
        for excerpt in trace.get('source_excerpts', []):
            source = frozen.get(excerpt.get('id'))
            if source is None or not source['text'].startswith(excerpt.get('text', '')):
                raise ValueError('Trace excerpt does not match frozen evidence.')
    rubric = run.inputs['rubric']
    rows = evaluation['records']
    expected = {c['id'] for i in rubric['indicators'] for c in i['conditions']}
    if len(rows) != len(expected) or {r['condition_id'] for r in rows} != expected:
        raise ValueError('Publication requires exactly all 216 condition decisions.')
    # Evaluator already checked scope/period; revalidation preserves its conservative output.
    validated = []
    for indicator in rubric['indicators']:
        subset = [dict(r) for r in rows
                  if r['condition_id'] in {c['id'] for c in indicator['conditions']}]
        validated.extend(validate_decisions(indicator, {'conditions': subset}, run.inputs['sources']))
    decisions = {r['condition_id']: r['state'] for r in validated}
    result = assess(decisions, rubric)
    payload = {'records': validated, 'result': result, 'actions': actions_for(result),
               'pathways': [roadmap(decisions, t['name'], rubric) for t in rubric['tiers']],
               'inference': inference, 'traces': evaluation.get('traces', []),
               'inputs_hash': run.inputs_hash, 'engine_version': ENGINE_VERSION}
    return CapabilityRunEvent.objects.create(run=run, state='completed', payload=payload)


def candidate_requirements(run):
    """Reassess every condition on updates, including previously unsupported ones.

    Conservative full invalidation avoids missing new contradictions through reverse
    citation-only matching. Context selection still bounds each indicator's input.
    """
    return [c['id'] for i in run.inputs['rubric']['indicators'] for c in i['conditions']]
