"""Tenant-scoped frozen evidence and atomic, append-only capability publication.

No inference here. Callers must authorize the institution before using these internal
services; matching institution/sprint IDs additionally prevents cross-tenant sources.
Carry-over is explicit: only current documents in this sprint are included. Renamed
replacements must use existing version lineage; never guess replacement by content.
"""
import hashlib
import json
import re

from django.db import connection, transaction

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.extraction.services.evidence_text import evidence_pages
from apps.scoring.models import CapabilityRun, CapabilityRunEvent
from apps.sprints.models import Sprint
from .engine import ENGINE_VERSION, assess, release
from .evaluation import validate_decisions
from .planning import actions_for, roadmap


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def evidence_snapshot(sprint):
    from .scope import report_timestamps
    from apps.facts.models import ExtractedFact
    from apps.facts.verification.grounding import parse_pages
    hints = {}
    for fact in ExtractedFact.objects.filter(sprint=sprint).exclude(status='rejected').filter(source_review_required=False).prefetch_related('aiqif_mappings'):
        document_id = str(fact.source_document_id or fact.document_id)
        quote = fact.source_snippet.strip()
        if not quote:
            continue
        # Contextual tags never count toward coverage; they would also crowd evidence out of retrieval.
        codes = sorted({m.indicator_code for m in fact.aiqif_mappings.all()
                        if m.review_status != 'rejected' and m.auto_decision != 'rejected_precedent'
                        and m.relationship != 'contextual'
                        and (m.status == 'mapped' or m.review_status == 'confirmed')})
        for number in parse_pages(fact.source_page):
            hints.setdefault((document_id, number), []).append((codes, quote))
    manifest, sources = [], []
    documents = Document.objects.filter(sprint=sprint, superseded_at__isnull=True).exclude(
        status=Document.Status.REJECTED).order_by('id')
    for document in documents:
        pages = list(DocumentPage.objects.filter(document=document).order_by('page_number'))
        rendered = {p['page_number']: p['text'] for p in evidence_pages([
            {'page_number': p.page_number, 'text': p.text, 'tables': p.tables} for p in pages])}
        manifest.append({'document_id': str(document.pk), 'filename': document.original_filename,
                         'drive_file_id': document.drive_file_id, 'source_path': document.source_path,
                         'checksum': document.checksum, 'version': document.version_number,
                         'previous_version_id': str(document.previous_version_id) if document.previous_version_id else None,
                         'status': document.status, 'expected_pages': document.page_count,
                         'pages': [{'page_id': str(p.pk), 'number': p.page_number, 'status': p.status,
                                    'text_hash': digest(p.text), 'tables_hash': digest(p.tables),
                                    'evidence_text_hash': digest(rendered[p.page_number]), 'text_source': p.text_source} for p in pages]})
        for page in pages:
            if page.status == DocumentPage.Status.OK and rendered[page.page_number].strip():
                page_hints = []
                text = rendered[page.page_number]
                for codes, quote in hints.get((str(document.pk), page.page_number), []):
                    # A tag proposes a location only when its quotation actually
                    # occurs in the canonical source. Never manufacture evidence.
                    match = re.search(r'\s+'.join(re.escape(part) for part in quote.split()), text)
                    if match:
                        page_hints.extend({'indicator_code': code, 'start': match.start(), 'end': match.end()}
                                          for code in codes)
                timestamps = list(report_timestamps({'id': str(page.pk), 'text': page.text}))
                footer = {}
                if len(timestamps) == 1 and timestamps[0]['quote'] not in text:
                    stamp = timestamps[0]
                    footer = {'report_timestamp': {'start': len(text) + 1,
                                                   'raw_start': stamp['start'], 'raw_end': stamp['end']}}
                    text += '\n' + stamp['quote']
                sources.append({**footer, 'retrieval_hints': sorted(page_hints, key=lambda h: (h['indicator_code'], h['start'], h['end'])),
                                'id': str(page.pk), 'document_id': str(document.pk),
                                'page_number': page.page_number, 'text': text,
                                'text_source': page.text_source})
    return manifest, sources


@transaction.atomic
def create_run(*, institution_id, sprint_id, population=None, reference_period=None, execution_policy=None,
               scope_mode=None, refines_run_id=None, confirmed_source_institution=None):
    from .scope import intent, resolve
    mode, requested = intent(population, reference_period, scope_mode, refines_run_id, confirmed_source_institution)
    sprint, manifest, sources, labels, reviewed, profile = freeze_boundary(institution_id, sprint_id)
    batch = reviewed.get('review_batch')
    if batch and not requested.get('confirmed_source_institution'):
        for identity_case in reversed(batch['cases']):
            identity_decision = batch['decisions'].get(identity_case['id'])
            if (identity_case.get('kind') == 'identity' and identity_case.get('source_hash') == digest(manifest)
                    and identity_decision and identity_decision['action'] == 'identity'):
                requested['confirmed_source_institution'] = identity_decision['request']['source_institution']
                break
    try:
        scope = resolve(profile=profile, sources=labels, requested=requested, mode=mode)
    except ValueError as exc:
        from rest_framework.exceptions import ValidationError
        raise ValidationError(str(exc))
    if scope['institution']['identity_status'] == 'mismatch_requires_review':
        from rest_framework.exceptions import ValidationError
        raise ValidationError({'code': 'source_identity_confirmation_required',
            'detail': 'The source institution differs from the profile. Confirm which source institution this assessment concerns before using model credits.',
            'source_institutions': sorted({d['value'] for d in scope['source_declarations'] if d['kind'] == 'institution_identity'})})
    if refines_run_id:
        prior = CapabilityRun.objects.get(pk=refines_run_id, sprint=sprint)
        if not prior.events.filter(state='completed', payload__result__isnull=False).exists():
            raise ValueError('Refinement requires a completed assessment in this sprint.')
    from .semantic_retrieval import configured_policy
    try:
        retrieval_policy = configured_policy()
    except ValueError as exc:
        from rest_framework.exceptions import ValidationError
        raise ValidationError({'code': 'retrieval_configuration_invalid', 'detail': str(exc)}) from exc
    rubric = release()
    from .evaluation import PROMPT_VERSION, RETRIEVAL_VERSION, SYSTEM_PROMPT, DECISION_SCHEMA
    inputs = {'institution_id': str(sprint.institution_id), 'sprint_id': str(sprint.pk),
              'profile': profile, 'scope': scope,
              'refines_run_id': str(refines_run_id) if refines_run_id else None,
              'population': scope['population_label'], 'reference_period': scope['period_label'],
              'carry_over_policy': 'current_sprint_only_explicit_document_lineage',
              'rubric': rubric, 'rubric_snapshot_hash': digest(rubric),
              'engine_version': ENGINE_VERSION, 'retrieval_policy': retrieval_policy,
              'assessment_protocol': {'prompt_version': PROMPT_VERSION, 'retrieval_version': RETRIEVAL_VERSION,
                                      'prompt_hash': hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
                                      'schema_hash': hashlib.sha256(json.dumps(DECISION_SCHEMA, sort_keys=True).encode()).hexdigest()},
              'manifest': manifest, 'sources': sources, 'reviewed_evidence': reviewed,
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
            offset = excerpt.get('text_offset', 0)
            if (source is None or type(offset) is not int or offset < 0
                    or source['text'][offset:offset + len(excerpt.get('text', ''))] != excerpt.get('text', '')):
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
        checked = validate_decisions(indicator, {'conditions': subset}, run.inputs['sources'],
                                     reviewed_evidence=run.inputs.get('reviewed_evidence'))
        # Revalidation must not erase why the evaluator already downgraded a row.
        original = {r['condition_id']: r for r in subset}
        for row in checked:
            prior = original[row['condition_id']]
            if row['state'] == 'unknown' and not row['validation_issue'] and prior.get('validation_issue'):
                row['validation_issue'] = prior['validation_issue']
                if 'withheld_state' in prior:
                    row['withheld_state'] = prior['withheld_state']
            # The structured cause travels with the issue; a re-check of an already
            # withheld row must not relabel a processing failure as an assessed unknown.
            if (row['state'] == 'unknown' and row.get('cause') == 'assessed' and prior.get('validation_issue')
                    and prior.get('cause') not in (None, 'assessed')):
                row['cause'] = prior['cause']
                if 'cause_detail' in prior:
                    row['cause_detail'] = prior['cause_detail']
        validated.extend(checked)
    decisions = {r['condition_id']: r['state'] for r in validated}
    result = assess(decisions, rubric)
    from .decision_causes import summary as cause_summary
    payload = {'records': validated, 'result': result, 'actions': actions_for(result),
               'decision_causes': cause_summary(validated),
               'pathways': [roadmap(decisions, t['name'], rubric) for t in rubric['tiers']],
               'inference': inference, 'traces': evaluation.get('traces', []),
               'inputs_hash': run.inputs_hash, 'engine_version': result['engine_version']}
    return CapabilityRunEvent.objects.create(run=run, state='completed', payload=payload)


def candidate_requirements(run):
    """Reassess every condition on updates, including previously unsupported ones.

    Conservative full invalidation avoids missing new contradictions through reverse
    citation-only matching. Context selection still bounds each indicator's input.
    """
    return [c['id'] for i in run.inputs['rubric']['indicators'] for c in i['conditions']]


def boundary_revision(sprint_id):
    """One PostgreSQL statement witnesses every mutable input at one MVCC instant.

    Comparing the full rows, not only timestamps/counts, catches page corrections,
    deletions and review disposition changes. JSONB gives deterministic key order.
    No locks or external calls. SQLite already has one atomic read snapshot.
    """
    if connection.vendor != 'postgresql':
        return None
    tables = [
        ('documents_document', 't.sprint_id = %s'),
        ('extraction_documentpage', 't.document_id IN (SELECT id FROM documents_document WHERE sprint_id = %s)'),
        ('facts_extractedfact', 't.sprint_id = %s'),
        ('facts_factaiqifmapping', 't.fact_id IN (SELECT id FROM facts_extractedfact WHERE sprint_id = %s)'),
        ('facts_factreviewhistory', 't.fact_id IN (SELECT id FROM facts_extractedfact WHERE sprint_id = %s)'),
        ('gaps_gapitem', 't.sprint_id = %s'),
        ('gaps_gapevent', 't.gap_id IN (SELECT id FROM gaps_gapitem WHERE sprint_id = %s)'),
        ('facts_reviewbatch', 't.sprint_id = %s'),
        ('institutions_institution', 't.id IN (SELECT institution_id FROM sprints_sprint WHERE id = %s)'),
    ]
    parts = [f'(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.id) FROM {table} t WHERE {where})'
             for table, where in tables]
    with connection.cursor() as cursor:
        cursor.execute('SELECT md5(jsonb_build_array(' + ','.join(parts) + ')::text)',
                       [str(sprint_id)] * len(parts))
        return cursor.fetchone()[0]


def label_sources(sources):
    """The same sources carrying their stored page text, for scope label scanning (scope.resolve).

    Evidence cleanup removes repeated page headers, and an SSR's repeated header ("Self Study Report
    of …") is what names the source institution and lets its footer date the report. The stored text
    keeps it. Declaration offsets therefore refer to stored page text, not the evidence text.
    """
    stored = {str(pk): text for pk, text in DocumentPage.objects.filter(
        pk__in=[s['id'] for s in sources]).values_list('pk', 'text')}
    return [{**s, 'text': stored.get(s['id'], s['text'])} for s in sources]


def freeze_boundary(institution_id, sprint_id):
    from .reviewed_evidence import snapshot
    # With PostgreSQL READ COMMITTED an outer caller may already have read rows.
    # A single-statement witness before/after copying proves a stable boundary;
    # retry boundedly if any transaction committed an input change during it.
    for _ in range(3):
        before = boundary_revision(sprint_id)
        sprint = Sprint.objects.select_related('institution').get(pk=sprint_id, institution_id=institution_id)
        manifest, sources = evidence_snapshot(sprint)
        labels = label_sources(sources)
        reviewed = snapshot(sprint)
        institution = sprint.institution
        profile = {'name': institution.name, 'institution_type': institution.institution_type,
                   'student_count': institution.student_count, 'faculty_count': institution.faculty_count}
        if before == boundary_revision(sprint_id):
            return sprint, manifest, sources, labels, reviewed, profile
    from rest_framework.exceptions import ValidationError
    raise ValidationError({'code': 'evidence_changed_during_snapshot',
                           'detail': 'Evidence changed repeatedly while it was being copied. Retry the explicit assessment start; no model work was dispatched.'})
