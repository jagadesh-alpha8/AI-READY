"""Database side of the second assessment layer (layer2.py holds the logic). Skeleton.

The institution's flow, one item at a time:

    item = next_item(run_ref)                      # a follow-up the check asked, else the next open question
    response = submit(question, answer=..., document_ids=[...])   # or skip=True; a follow-up passes parent=
    check_response(response, model)                # search with the answer, check it, maybe ask one follow-up
    add_evidence(run_ref, rubric, document_ids=[...], note=..., picked=[...])   # optional additional evidence
    check_additional(item, rubric)
    result = rejudge_credit(export_for_run(run_ref), service)   # credit path on the provisional packets plus new passages
    final_run = publish_final(result, service=service)            # the final result, as a run refining the provisional one

Checks wait while an attached document is still being extracted (check_pending runs them later). In production these
steps run as background jobs (second_layer_jobs.py), whose model calls are metered against the run's second-layer
budget; the management commands call them directly, unmetered, with a cap on calls.

The final result is a new run (refines_run_id = the provisional run, inputs.second_layer says how it was made) whose
frozen sources are the provisional run's plus the new documents' pages, published through storage.publish. Reports,
recommendations and plan evaluations of that run therefore use the final credit without change, and the provisional
run is never altered. Questions and answers stay keyed to the provisional run; the final run takes none of its own.
"""
import threading
import uuid

from django.conf import settings
from django.db import transaction

from apps.scoring.models import AdditionalEvidence, CapabilityRun, DepthQuestion, DepthResponse

from . import depth, layer2
from .layer2 import Layer2Error


RUN_RANKER = object()  # default for `ranker`: the provisional run's own retrieval ranker
_RANKERS, _RANKERS_LOCK = {}, threading.Lock()   # one ranker per run per process (building one loads the model)


def _uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


def _run(run_ref):
    return CapabilityRun.objects.filter(pk=run_ref).first() if _uuid(run_ref) else None


def is_final(run):
    return bool(run is not None and (run.inputs or {}).get('second_layer'))


def _refuse_final(run):
    if is_final(run):
        raise Layer2Error('This run is a second-layer final result; use its provisional run '
                          f"{run.inputs['second_layer']['provisional_run_id']}.")


def export_for_run(run_ref):
    """The provisional run's assessment export, built from this database (the shape rejudge_credit reads)."""
    run = _run(run_ref)
    if run is None:
        raise Layer2Error('Run %s is not in this database.' % run_ref)
    _refuse_final(run)
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    if event is None:
        raise Layer2Error('Run %s has no completed assessment.' % run_ref)
    inputs = run.inputs
    return {'run_id': str(run.pk), 'inputs_hash': run.inputs_hash, 'rubric': inputs['rubric'],
            'population': inputs.get('population'), 'reference_period': inputs.get('reference_period'),
            'scope': inputs.get('scope'), 'reviewed_evidence': inputs.get('reviewed_evidence'),
            'retrieval_policy': inputs.get('retrieval_policy'), 'assessment_event_id': event.pk,
            'assessment': event.payload}


def run_sprint_id(run_ref):
    run = _run(run_ref)
    return run.sprint_id if run else None


def ranker_for_run(run_ref):
    """(ranker or None, 'hybrid' or 'keyword', note): the embedding ranker of the provisional run's frozen retrieval
    policy, so the second layer searches the way the run did. Keyword-only when the run used keyword retrieval, is not
    in this database, or this worker lacks the run's embedding model (the note says which). Built once per run per
    process: each build loads the model, and its corpus index is reused across answers."""
    from .semantic_retrieval import SemanticRetrievalUnavailable, ranker_for
    run = _run(run_ref)
    if run is None:
        return None, 'keyword', 'Run not in this database.'
    key = str(run.pk)
    with _RANKERS_LOCK:
        if key in _RANKERS:
            return _RANKERS[key]
    try:
        ranker = ranker_for((run.inputs or {}).get('retrieval_policy'))
    except (SemanticRetrievalUnavailable, OSError, ImportError) as exc:
        return None, 'keyword', f'Embedding ranker unavailable ({type(exc).__name__}).'
    result = (ranker, ('hybrid' if ranker is not None else 'keyword'), '')
    with _RANKERS_LOCK:
        _RANKERS.clear()  # keep one: rankers hold the corpus vectors
        _RANKERS[key] = result
    return result


def _resolve_ranker(ranker, run_ref):
    if ranker is RUN_RANKER:
        return ranker_for_run(run_ref)
    return ranker, ('hybrid' if ranker is not None else 'keyword'), ''


def check_documents(document_ids, sprint_id):
    """The documents' ids, refused unless every one belongs to the sprint."""
    from apps.documents.models import Document
    ids = [i for i in (_uuid(d) for d in document_ids or []) if i]
    if len(ids) != len(list(document_ids or [])) or sprint_id is None or (
            Document.objects.filter(pk__in=ids, sprint_id=sprint_id).count() != len(set(ids))):
        raise Layer2Error("Every document must be uploaded to this run's sprint first.")
    return ids


# ------------------------------------------------------------------ sources


def document_sources(document_ids, sprint_id):
    """(frozen-source dicts for the documents' readable pages, ready, failed document ids). Every document must belong
    to the sprint. ready is False while any document is still waiting for or in extraction; its answer is checked
    later. A document whose extraction failed adds nothing and is reported."""
    from apps.documents.models import Document
    from apps.extraction.models import DocumentPage
    from apps.extraction.services.evidence_text import evidence_pages
    ids = check_documents(document_ids, sprint_id)
    sources, ready, failed = [], True, []
    for document in Document.objects.filter(pk__in=ids, sprint_id=sprint_id).order_by('id'):
        if document.status in (Document.Status.FAILED, Document.Status.REJECTED):
            failed.append(str(document.pk))   # never extracted: waiting for it would hold the answer for ever
            continue
        pages = list(DocumentPage.objects.filter(document=document).order_by('page_number'))
        if not pages or document.status == Document.Status.PROCESSING:
            ready = False
            continue
        rendered = {p['page_number']: p['text'] for p in evidence_pages([
            {'page_number': p.page_number, 'text': p.text, 'tables': p.tables} for p in pages])}
        for page in pages:
            if page.status == DocumentPage.Status.OK and rendered[page.page_number].strip():
                sources.append({'id': str(page.pk), 'document_id': str(document.pk), 'page_number': page.page_number,
                                'text': rendered[page.page_number], 'text_source': page.text_source})
    return sources, ready, failed


def run_sources(run_ref):
    """The run's frozen pages (the corpus an answer is also searched in), or [] when the run is not in this database."""
    run = _run(run_ref)
    return list((run.inputs or {}).get('sources') or []) if run else []


def run_rubric(run_ref):
    from .engine import release
    run = _run(run_ref)
    return (run.inputs or {}).get('rubric') or release() if run else release()


def provisional(run_ref):
    """(records by condition id, packets by key indicator) from the run's completed assessment in this database, or
    ({}, {}) when there is none. The packets are the traces' source_excerpts: exactly what the judge saw."""
    run = _run(run_ref)
    event = run.events.filter(state='completed', payload__result__isnull=False).last() if run else None
    if event is None:
        return {}, {}
    payload = event.payload or {}
    return ({r['condition_id']: r for r in payload.get('records') or []},
            {t['indicator']: t.get('source_excerpts') or [] for t in payload.get('traces') or []})


def support_roles():
    """Passage roles that can make a depth answer count (SECOND_LAYER_CORPUS_SUPPORT). True (default): what the
    attached documents show, what the search found among documents already submitted, and the credited evidence
    itself. False: only the attached documents."""
    if getattr(settings, 'SECOND_LAYER_CORPUS_SUPPORT', True):
        return None
    return {'answer_attachment'}


def tagged_pages(document_ids, indicator_code):
    """(document id, page number) pairs extraction tagged with the key indicator in these documents' facts."""
    from django.db.models import Q
    from apps.facts.models import ExtractedFact
    from apps.facts.verification.grounding import parse_pages
    ids = [i for i in (_uuid(d) for d in document_ids or []) if i]
    pages = set()
    facts = (ExtractedFact.objects.filter(Q(document_id__in=ids) | Q(source_document_id__in=ids))
             .exclude(status='rejected').prefetch_related('aiqif_mappings'))
    for fact in facts:
        if any(m.indicator_code == indicator_code and _counts(m) for m in fact.aiqif_mappings.all()):
            document = str(fact.source_document_id or fact.document_id)
            pages.update((document, n) for n in parse_pages(fact.source_page))
    return pages


def _counts(mapping):
    """The extracted-evidence lane's test for a tag that routes evidence (storage.evidence_snapshot)."""
    return (mapping.review_status != 'rejected' and mapping.auto_decision != 'rejected_precedent'
            and mapping.relationship != 'contextual'
            and (mapping.status == 'mapped' or mapping.review_status == 'confirmed'))


def extracted_indicators(document_ids):
    """Key indicators extraction tagged the documents' facts with (the extracted-evidence lane's own routing)."""
    from django.db.models import Q
    from apps.facts.models import ExtractedFact
    ids = [i for i in (_uuid(d) for d in document_ids or []) if i]
    codes = set()
    facts = (ExtractedFact.objects.filter(Q(document_id__in=ids) | Q(source_document_id__in=ids))
             .exclude(status='rejected').prefetch_related('aiqif_mappings'))
    for fact in facts:
        codes.update(m.indicator_code for m in fact.aiqif_mappings.all() if _counts(m))
    return codes


def dimensions_for(question, depth_spec=None):
    """The quality dimensions a depth question asked about: [{'id', 'name', 'ask', ...}]."""
    spec = depth_spec or depth.spec()
    _, dims = depth._condition_dimensions(spec, question.condition_ids[0])
    wanted = set(question.dimension_ids or [d['id'] for d in dims])
    return [d for d in dims if d['id'] in wanted]


# ------------------------------------------------------------------ one item at a time


def next_item(run_ref):
    """The next thing to show the institution: a follow-up the check asked (answered before moving on), else the open
    question with the lowest rank, else None. A follow-up whose answer is still being checked does not hold the queue."""
    waiting = (DepthResponse.objects.filter(question__run_ref=run_ref, parent__isnull=True,
                                            status=DepthResponse.Status.CHECKED)
               .exclude(follow_up_text='').filter(follow_ups__isnull=True)
               .select_related('question').order_by('question__rank', 'created_at').first())
    if waiting is not None:
        return {'type': 'follow_up', 'question': waiting.question, 'response': waiting, 'text': waiting.follow_up_text}
    question = DepthQuestion.objects.filter(run_ref=run_ref, status=DepthQuestion.Status.OPEN).order_by('rank').first()
    if question is not None:
        return {'type': 'question', 'question': question, 'response': None, 'text': question.text}
    return None


def progress(run_ref):
    questions = DepthQuestion.objects.filter(run_ref=run_ref)
    responses = DepthResponse.objects.filter(question__run_ref=run_ref)
    return {'questions': questions.count(),
            'open': questions.filter(status=DepthQuestion.Status.OPEN).count(),
            'answered': questions.exclude(status=DepthQuestion.Status.OPEN).count(),
            'checks_waiting': responses.filter(status=DepthResponse.Status.PENDING).count(),
            'follow_ups_open': responses.filter(parent__isnull=True, status=DepthResponse.Status.CHECKED)
                                        .exclude(follow_up_text='').filter(follow_ups__isnull=True).count(),
            'final_run_id': final_run_id(run_ref)}


def final_run_id(run_ref):
    """The newest final result published for this provisional run, or None."""
    final = CapabilityRun.objects.filter(inputs__second_layer__provisional_run_id=str(run_ref)).order_by('-created_at').first()
    return str(final.pk) if final else None


def submit(question, *, answer='', document_ids=(), skip=False, parent=None, user=None, via='college'):
    """Record one response. A skip is "don't know" and needs no check; anything else waits for check_response.
    parent: the response whose follow-up this answers (at most one answer per follow-up, never followed up again).
    The question (or the follow-up's parent) is locked while the response is recorded, so two submissions at once
    cannot both be accepted. Documents must belong to the run's sprint when the run is in this database."""
    answer = (answer or '').strip()
    documents = [str(d) for d in document_ids or []]
    if not skip and not answer and not documents:
        raise Layer2Error('Give an answer, attach a document, or skip.')
    if documents and not skip:
        sprint_id = run_sprint_id(question.run_ref)
        if sprint_id is not None:
            documents = check_documents(documents, sprint_id)
    with transaction.atomic():
        locked = DepthQuestion.objects.select_for_update().get(pk=question.pk)
        if parent is not None:
            parent = DepthResponse.objects.select_for_update().get(pk=parent.pk)
            if parent.question_id != locked.pk or parent.parent_id is not None or not parent.follow_up_text:
                raise Layer2Error('That response has no follow-up question to answer.')
            if parent.follow_ups.exists():
                raise Layer2Error('That follow-up has already been answered.')
        elif locked.status != DepthQuestion.Status.OPEN:
            raise Layer2Error('This question has already been answered.')
        response = DepthResponse.objects.create(
            question=locked, parent=parent,
            kind=DepthResponse.Kind.DONT_KNOW if skip else DepthResponse.Kind.ANSWER,
            answer='' if skip else answer, document_ids=[] if skip else documents,
            status=DepthResponse.Status.CHECKED if skip else DepthResponse.Status.PENDING,
            submitted_via=via, submitted_by=user)
        if parent is None:
            locked.status = DepthQuestion.Status.ANSWERED
            locked.save(update_fields=['status'])
            question.status = locked.status
    return response


def check_response(response, model, *, attached=None, corpus=None, ranker=RUN_RANKER, depth_spec=None, context=None):
    """Search with the answer and, for a depth question, check it against what was found (one model call, none when
    nothing was found). For a "nothing found" question no model call is made here: the windows go to the credit path,
    which judges them. Returns the response; it stays pending while an attached document is still being extracted.

    context: (records by condition id, packets by key indicator) of the provisional run (provisional(); read from the
    database when not given). The search leaves out the requirement's provisional packet and passages that mostly
    repeat it, so `windows` (what the credit path gets) is text the first pass did not see. The depth check also reads
    the credited evidence itself (credited_windows), so it can judge the answer against what earned the credit.
    The search uses the run's own ranker unless one is given; the check records which ranking was used, any attached
    document whose extraction failed, and which kinds of passage the support rests on."""
    if response.status == DepthResponse.Status.CHECKED:
        return response
    question = response.question
    failed = []
    if attached is None:
        sprint_id = run_sprint_id(question.run_ref)
        if sprint_id is None:
            raise Layer2Error('Run not found: documents are read only for a run in this database.')
        attached, ready, failed = document_sources(response.document_ids, sprint_id)
        if not ready:
            return response
    if corpus is None:
        corpus = run_sources(question.run_ref)
    records, packets = provisional(question.run_ref) if context is None else context
    packet = packets.get(question.indicator_code) or []
    record = records.get(question.condition_ids[0]) if question.condition_ids else None
    ranker, ranking, note = _resolve_ranker(ranker, question.run_ref)
    asked = response.parent.follow_up_text if response.parent_id else question.text
    first = response.parent_id is None
    if question.kind == DepthQuestion.Kind.DEPTH:
        quotes = layer2.anchored_query('', record)
        windows = layer2.search_with_answer(layer2.anchored_query(response.answer, record) if response.answer.strip()
                                            else '', attached, corpus, packet=packet, ranker=ranker,
                                            fallback_query=quotes or asked)
        result = layer2.check_answer(asked, response.answer, layer2.credited_windows(record, packet) + windows,
                                     dimensions_for(question, depth_spec), model, allow_follow_up=first,
                                     counts_from=support_roles())
    else:
        fallback = layer2.profile_query(run_rubric(question.run_ref), question.condition_ids) or asked
        windows = layer2.search_with_answer(response.answer, attached, corpus, packet=packet, ranker=ranker,
                                            fallback_query=fallback)
        roles = support_roles()
        counted = [w for w in windows if roles is None or w.get('evidence_role') in roles]
        result = {'version': layer2.VERSION, 'model_called': False, 'supported': bool(counted), 'dimensions': [],
                  'passages': [], 'follow_up': None if (counted or not first) else layer2.NO_SUPPORT_FOLLOW_UP,
                  'note': 'Judged in the credit path, on the provisional packet plus these passages.'}
        windows = counted
    cited = {p.get('evidence_role') for p in result.get('passages') or []}
    result['search'] = {'ranking': ranking, 'note': note, 'documents_failed': failed,
                        'packet_windows_left_out': len(packet), 'support_from': sorted(r for r in cited if r)}
    response.windows = windows
    response.support_check = result
    response.supported = result['supported']
    response.follow_up_text = result['follow_up'] or ''
    response.status = DepthResponse.Status.CHECKED
    response.save(update_fields=['windows', 'support_check', 'supported', 'follow_up_text', 'status'])
    return response


def check_pending(run_ref, model, *, ranker=RUN_RANKER, max_calls=None, skip_error=None):
    """Check every waiting response of a run whose documents are ready. Returns counts.

    skip_error: a test for exceptions that leave one response waiting (counted in 'failed') instead of stopping the
    rest, such as a malformed model reply; anything else (a spent budget, a cancelled job) stops the loop."""
    corpus = run_sources(run_ref)
    if ranker is RUN_RANKER:
        ranker = _resolve_ranker(ranker, run_ref)[0]
    context = provisional(run_ref)
    spec = depth.spec()
    checked = waiting = calls = failed = 0
    for response in (DepthResponse.objects.filter(question__run_ref=run_ref, status=DepthResponse.Status.PENDING)
                     .select_related('question', 'parent').order_by('created_at')):
        if max_calls is not None and calls >= max_calls:
            waiting += 1
            continue
        try:
            check_response(response, model, corpus=corpus, ranker=ranker, depth_spec=spec, context=context)
        except Exception as exc:
            if skip_error is None or not skip_error(exc):
                raise
            failed += 1
            continue
        if response.status == DepthResponse.Status.CHECKED:
            checked += 1
            calls += int(bool(response.support_check.get('model_called')))
        else:
            waiting += 1
    return {'checked': checked, 'waiting': waiting, 'model_calls': calls, 'failed': failed}


# ------------------------------------------------------------------ optional additional evidence


def add_evidence(run_ref, rubric, *, document_ids, note='', picked=(), user=None):
    """Record documents the institution thinks were missed. It must pick at least one readiness area, key indicator
    or requirement; extraction's tags are added when the documents are checked."""
    documents = [str(d) for d in document_ids or []]
    if not documents:
        raise Layer2Error('Attach at least one document.')
    sprint_id = run_sprint_id(run_ref)
    if sprint_id is not None:
        documents = check_documents(documents, sprint_id)
    routing = layer2.route_additional(rubric, picked)
    if not routing['indicators']:
        raise Layer2Error('Pick at least one readiness area, key indicator or requirement this evidence is for.')
    return AdditionalEvidence.objects.create(run_ref=str(run_ref), document_ids=documents, note=(note or '').strip(),
                                             picked=[str(p) for p in picked], routing=routing, submitted_by=user)


def check_additional(item, rubric, *, attached=None, extracted=None, ranker=RUN_RANKER):
    """Route with extraction's tags added and take the passages the credit path will judge. The search covers the
    submitted documents only: they are the evidence. Stays pending while a document is being extracted."""
    if item.status == AdditionalEvidence.Status.CHECKED:
        return item
    failed = []
    if attached is None:
        sprint_id = run_sprint_id(item.run_ref)
        if sprint_id is None:
            raise Layer2Error('Run not found: documents are read only for a run in this database.')
        attached, ready, failed = document_sources(item.document_ids, sprint_id)
        if not ready:
            return item
    ranker, ranking, note = _resolve_ranker(ranker, item.run_ref)
    if extracted is None:
        extracted = extracted_indicators(item.document_ids)
    routing = layer2.route_additional(rubric, item.picked, extracted)
    # With no note, a large document is ranked with the requirements' records-language profiles, never rubric wording.
    wanted = [c['id'] for i in rubric['indicators'] if i['code'] in routing['indicators'] for c in i['conditions']
              if c['id'] in (routing['conditions'].get(i['code']) or [c['id']])]
    item.routing = {**routing, 'search': {'ranking': ranking, 'note': note, 'documents_failed': failed}}
    item.windows = layer2.search_with_answer(item.note, attached, [], ranker=ranker,
                                             fallback_query=layer2.profile_query(rubric, wanted))
    item.status = AdditionalEvidence.Status.CHECKED
    item.save(update_fields=['routing', 'windows', 'status'])
    return item


# ------------------------------------------------------------------ credit path


def credit_routes(run_ref):
    """Routes for layer2.credit_targets: checked answers to "nothing found" questions, depth answers the check found
    support for (a partly credited requirement can rise on them; credit_targets drops fully credited ones), and checked
    additional evidence."""
    routes = []
    depth_answers = (DepthResponse.objects.filter(question__run_ref=run_ref, question__kind=DepthQuestion.Kind.DEPTH,
                                                  status=DepthResponse.Status.CHECKED, supported=True)
                     .select_related('question').order_by('created_at'))
    for response in depth_answers:
        routes.append({'indicator': response.question.indicator_code, 'conditions': list(response.question.condition_ids),
                       'windows': response.windows, 'documents': list(response.document_ids), 'kind': 'depth',
                       'from': f'depth-response:{response.pk}'})
    answers = (DepthResponse.objects.filter(question__run_ref=run_ref, question__kind=DepthQuestion.Kind.MISSING,
                                            status=DepthResponse.Status.CHECKED)
               .exclude(kind=DepthResponse.Kind.DONT_KNOW).select_related('question').order_by('created_at'))
    for response in answers:
        routes.append({'indicator': response.question.indicator_code, 'conditions': list(response.question.condition_ids),
                       'windows': response.windows, 'documents': list(response.document_ids), 'kind': 'missing',
                       'from': f'response:{response.pk}'})
    for item in AdditionalEvidence.objects.filter(run_ref=run_ref, status=AdditionalEvidence.Status.CHECKED):
        for code in item.routing.get('indicators', []):
            routes.append({'indicator': code, 'conditions': item.routing.get('conditions', {}).get(code),
                           'windows': item.windows, 'documents': list(item.document_ids), 'kind': 'additional',
                           'from': f'additional:{item.pk}'})
    return routes


def rejudge_credit(export, service, *, evaluate_fn=None, sources=None, routes=None, max_calls=36,
                   evaluate_options=None):
    """Re-judge the requirements new evidence was submitted for, on each one's provisional packet plus the new
    passages, with the main judge (part judgment, two passes, tie-break). Merge with layer2.merge_new_evidence.

    export: the provisional run's assessment export (run_id, rubric, population, reference_period, scope,
    retrieval_policy, assessment.records and assessment.traces). It must be scored under this worker's part rule
    (layer2.check_export_rule) and, when the run is in this database, be that run's export. service: the model service
    for evaluate. evaluate_options: further evaluate() arguments (a background job passes strict_errors so a spent
    budget stops the re-judgment instead of becoming a failed requirement, and the run's concurrency). Returns the
    merged records, the provisional and final scores, and an audit. Nothing is published (publish_final does)."""
    try:
        run_ref, rubric, records = export['run_id'], export['rubric'], export['assessment']['records']
    except (KeyError, TypeError):
        raise Layer2Error('Not an assessment export: needs run_id, rubric and assessment.records.')
    traces = export['assessment'].get('traces') or []
    run = _run(run_ref)
    _refuse_final(run)
    if run is not None and export.get('inputs_hash') and export['inputs_hash'] != run.inputs_hash:
        raise Layer2Error("The export's inputs do not match run %s in this database." % run_ref)
    routes = credit_routes(run_ref) if routes is None else routes
    targets = layer2.credit_targets(records, rubric, routes)
    provisional_score = layer2.final_score(records, rubric)
    result = {'version': layer2.VERSION, 'run_ref': run_ref, 'routes': len(routes),
              'provisional_score': provisional_score, 'saved': False}
    sprint_id = run_sprint_id(run_ref)
    frozen = run_sources(run_ref)
    frozen_documents = {s.get('document_id') for s in frozen}
    new_documents = sorted({d for t in targets.values() for d in t['documents'] if d not in frozen_documents}
                           | {w['document_id'] for t in targets.values() for w in t['windows']
                              if w.get('document_id') and w['document_id'] not in frozen_documents})
    new_pages = document_sources(new_documents, sprint_id)[0] if sprint_id is not None and new_documents else []
    if new_pages:
        # Pages extraction tagged for the indicator, in the new documents sent for that indicator, join its packet
        # whatever their wording. (The run's own documents went through the extracted-evidence lane in the first layer.)
        for code, target in targets.items():
            mine = [d for d in target['documents'] if d not in frozen_documents]
            pages = tagged_pages(mine, code) if mine else set()
            if pages:
                layer2.add_windows(target, layer2.page_windows(new_pages, pages), 'extraction_tag')
    targets = {code: t for code, t in targets.items() if t['windows']}
    if not targets:
        return {**result, 'targets': {}, 'context_audit': {}, 'merge': [], 'records': records, 'contradictions': [],
                'final_score': provisional_score, 'traces': [], 'new_sources': [], 'note': 'No new evidence to re-judge.'}
    layer2.check_export_rule(records, traces, targets)
    contexts, context_audit = layer2.fixed_contexts(traces, targets)
    subset = layer2.subset_rubric(rubric, targets)
    if len(subset['indicators']) > max_calls:
        raise Layer2Error(f'{len(subset["indicators"])} key indicators to re-judge; the limit is {max_calls}.')
    if sources is None:
        sources = frozen + new_pages
    if evaluate_fn is None:
        from .evaluation import evaluate as evaluate_fn
    # The run's own retrieval policy, so page aliases for reviewed evidence and the trace match the first pass; the
    # targeted extra search is not repeated (the packet already holds what it added).
    policy = {k: v for k, v in (export.get('retrieval_policy') or {}).items() if k != 'follow_up'} or None
    outcome = evaluate_fn(sources, service=service, population=export.get('population') or 'Not recorded',
                          reference_period=export.get('reference_period') or 'Not recorded', rubric=subset,
                          scope=export.get('scope'), reviewed_evidence=export.get('reviewed_evidence'),
                          retrieval_policy=policy, judgment='parts', agreement_passes=2, tie_break=True,
                          max_calls=len(subset['indicators']), fixed_contexts=contexts, **(evaluate_options or {}))
    packets = {t['indicator']: t.get('source_excerpts') or [] for t in traces}
    merged, merge_audit = layer2.merge_new_evidence(records, outcome['records'], packets, rubric=rubric)
    return {**result, 'targets': {code: t['conditions'] for code, t in targets.items()},
            'context_audit': context_audit, 'merge': merge_audit, 'records': merged,
            'contradictions': layer2.contradictions(merge_audit),
            'final_score': layer2.final_score(merged, rubric), 'traces': outcome.get('traces', []),
            'new_sources': new_pages, 'note': 'Publish with publish_final to make this the result reports use.'}


def _inference(service, provisional_event):
    """publish() needs inference identity. A metered service (a background job's) gives its per-call ledger; the
    command's unmetered client gives none. The provisional run's inference is kept beside it."""
    if hasattr(service, 'metadata'):
        return {**service.metadata(), 'second_layer_metered': True,
                'provisional': provisional_event.payload.get('inference')}
    return {'provider': getattr(service, 'provider', None) or (type(service).__name__ if service is not None else 'none'),
            'model': getattr(service, 'model', None) or 'unknown', 'settings': {}, 'calls': [],
            'second_layer_metered': False, 'provisional': provisional_event.payload.get('inference')}


def publish_final(result, *, service=None, user=None, inference=None):
    """Publish a rejudge_credit result as the final result: a new run refining the provisional one, with the new
    documents' pages added to its frozen sources and the merged records published through storage.publish (which
    revalidates every citation and trace excerpt against those sources). Re-judged key indicators take their new
    traces; the rest keep the provisional ones. Idempotent: the same result publishes once. Returns the final run."""
    from apps.documents.models import Document
    from apps.extraction.models import DocumentPage
    from apps.extraction.services.evidence_text import evidence_pages
    from apps.scoring.models import CapabilityExecution, CapabilityRunEvent
    from .storage import checkpoint, digest, manifest_entry, publish
    provisional_run = _run(result.get('run_ref'))
    if provisional_run is None:
        raise Layer2Error('The provisional run is not in this database; a final result cannot be published.')
    _refuse_final(provisional_run)
    event = provisional_run.events.filter(state='completed', payload__result__isnull=False).last()
    if event is None:
        raise Layer2Error('The provisional run has no completed assessment.')
    new_sources = [s for s in result.get('new_sources') or []]
    signature = digest({'provisional_event': event.pk, 'records': result['records'], 'traces': result.get('traces') or [],
                        'new_sources': sorted(s['id'] for s in new_sources)})
    key = 'second-layer-' + signature[:48]
    sprint = provisional_run.sprint
    with transaction.atomic():
        CapabilityRun.objects.select_for_update().get(pk=provisional_run.pk)
        existing = CapabilityExecution.objects.filter(sprint=sprint, idempotency_key=key).select_related('run').first()
        if existing:
            return existing.run
        inputs = dict(provisional_run.inputs)
        frozen_ids = {s['id'] for s in inputs['sources']}
        added = [s for s in new_sources if s['id'] not in frozen_ids]
        documents = {str(d.pk): d for d in Document.objects.filter(pk__in={s['document_id'] for s in added}, sprint=sprint)}
        if len(documents) != len({s['document_id'] for s in added}):
            raise Layer2Error('A new document does not belong to this sprint.')
        manifest = list(inputs['manifest'])
        for doc_id in sorted(documents):
            # The same entry a full run freezes (reports and diagnostics read every field of it).
            pages = list(DocumentPage.objects.filter(document=documents[doc_id]).order_by('page_number'))
            rendered = {p['page_number']: p['text'] for p in evidence_pages([
                {'page_number': p.page_number, 'text': p.text, 'tables': p.tables} for p in pages])}
            manifest.append({**manifest_entry(documents[doc_id], pages, rendered), 'added_by': 'second_layer'})
        inputs.update(sources=list(inputs['sources']) + added, manifest=manifest, refines_run_id=str(provisional_run.pk),
                      second_layer={'version': layer2.VERSION, 'provisional_run_id': str(provisional_run.pk),
                                    'provisional_event_id': event.pk, 'provisional_score': result.get('provisional_score'),
                                    'final_score': result.get('final_score'), 'targets': result.get('targets') or {},
                                    'merge': result.get('merge') or [], 'contradictions': result.get('contradictions') or [],
                                    'context_audit': result.get('context_audit') or {}, 'routes': result.get('routes'),
                                    'result_hash': signature, 'added_sources': [s['id'] for s in added]})
        run = CapabilityRun.objects.create(sprint=sprint, inputs=inputs, inputs_hash=digest(inputs))
        CapabilityRunEvent.objects.create(run=run, state='queued')
        CapabilityExecution.objects.create(run=run, sprint=sprint, requested_by=user, idempotency_key=key,
                                           request_hash=signature, status='completed')
        checkpoint(institution_id=sprint.institution_id, run_id=run.pk, state='running')
        rejudged = {t.get('indicator') for t in result.get('traces') or []}
        traces = [t for t in event.payload.get('traces') or [] if t.get('indicator') not in rejudged] + list(
            result.get('traces') or [])
        publish(institution_id=sprint.institution_id, run_id=run.pk,
                evaluation={'records': result['records'], 'traces': traces},
                inference=inference or _inference(service, event))
    return run
