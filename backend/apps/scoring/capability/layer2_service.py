"""Database side of the second assessment layer (layer2.py holds the logic). Skeleton.

The institution's flow, one item at a time:

    item = next_item(run_ref)                      # a follow-up the check asked, else the next open question
    response = submit(question, answer=..., document_ids=[...])   # or skip=True; a follow-up passes parent=
    check_response(response, model)                # search with the answer, check it, maybe ask one follow-up
    add_evidence(run_ref, rubric, document_ids=[...], note=..., picked=[...])   # optional additional evidence
    check_additional(item, rubric)
    result = rejudge_credit(export, service)       # credit path on the provisional packets plus new passages

Checks wait while an attached document is still being extracted (check_pending runs them later). Model calls here are
NOT metered against a run budget yet; commands cap them. Publishing the result as a run that refines the provisional
one is not built: rejudge_credit returns the merged records and the final score.
"""
import uuid

from django.db import transaction

from apps.scoring.models import AdditionalEvidence, CapabilityRun, DepthQuestion, DepthResponse

from . import depth, layer2
from .layer2 import Layer2Error


def _uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ sources


def document_sources(document_ids):
    """(frozen-source dicts for the documents' readable pages, ready). ready is False while any document is still
    waiting for or in extraction; its answer is checked later."""
    from apps.documents.models import Document
    from apps.extraction.models import DocumentPage
    from apps.extraction.services.evidence_text import evidence_pages
    ids = [i for i in (_uuid(d) for d in document_ids or []) if i]
    if len(ids) != len(list(document_ids or [])):
        raise Layer2Error('Unknown document.')
    documents = list(Document.objects.filter(pk__in=ids).order_by('id'))
    if len(documents) != len(set(ids)):
        raise Layer2Error('Unknown document.')
    sources, ready = [], True
    for document in documents:
        if document.status == Document.Status.FAILED:
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
    return sources, ready


def run_sources(run_ref):
    """The run's frozen pages (the corpus an answer is also searched in), or [] when the run is not in this database."""
    run = CapabilityRun.objects.filter(pk=run_ref).first() if _uuid(run_ref) else None
    return list((run.inputs or {}).get('sources') or []) if run else []


def extracted_indicators(document_ids):
    """Key indicators extraction tagged the documents' facts with (the extracted-evidence lane's own routing)."""
    from django.db.models import Q
    from apps.facts.models import ExtractedFact
    ids = [i for i in (_uuid(d) for d in document_ids or []) if i]
    codes = set()
    facts = (ExtractedFact.objects.filter(Q(document_id__in=ids) | Q(source_document_id__in=ids))
             .exclude(status='rejected').prefetch_related('aiqif_mappings'))
    for fact in facts:
        for m in fact.aiqif_mappings.all():
            if (m.review_status != 'rejected' and m.auto_decision != 'rejected_precedent'
                    and m.relationship != 'contextual' and (m.status == 'mapped' or m.review_status == 'confirmed')):
                codes.add(m.indicator_code)
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
                                        .exclude(follow_up_text='').filter(follow_ups__isnull=True).count()}


def submit(question, *, answer='', document_ids=(), skip=False, parent=None, user=None, via='college'):
    """Record one response. A skip is "don't know" and needs no check; anything else waits for check_response.
    parent: the response whose follow-up this answers (at most one answer per follow-up, never followed up again)."""
    answer = (answer or '').strip()
    documents = [str(d) for d in document_ids or []]
    if parent is not None:
        if parent.question_id != question.pk or parent.parent_id is not None or not parent.follow_up_text:
            raise Layer2Error('That response has no follow-up question to answer.')
        if parent.follow_ups.exists():
            raise Layer2Error('That follow-up has already been answered.')
    elif question.status != DepthQuestion.Status.OPEN:
        raise Layer2Error('This question has already been answered.')
    if not skip and not answer and not documents:
        raise Layer2Error('Give an answer, attach a document, or skip.')
    with transaction.atomic():
        response = DepthResponse.objects.create(
            question=question, parent=parent,
            kind=DepthResponse.Kind.DONT_KNOW if skip else DepthResponse.Kind.ANSWER,
            answer='' if skip else answer, document_ids=[] if skip else documents,
            status=DepthResponse.Status.CHECKED if skip else DepthResponse.Status.PENDING,
            submitted_via=via, submitted_by=user)
        if parent is None:
            question.status = DepthQuestion.Status.ANSWERED
            question.save(update_fields=['status'])
    return response


def check_response(response, model, *, attached=None, corpus=None, ranker=None, depth_spec=None):
    """Search with the answer and, for a depth question, check it against what was found (one model call, none when
    nothing was found). For a "nothing found" question no model call is made here: the windows go to the credit path,
    which judges them. Returns the response; it stays pending while an attached document is still being extracted."""
    if response.status == DepthResponse.Status.CHECKED:
        return response
    question = response.question
    if attached is None:
        attached, ready = document_sources(response.document_ids)
        if not ready:
            return response
    if corpus is None:
        corpus = run_sources(question.run_ref)
    asked = response.parent.follow_up_text if response.parent_id else question.text
    windows = layer2.search_with_answer(response.answer, attached, corpus, ranker=ranker, fallback_query=asked)
    first = response.parent_id is None
    if question.kind == DepthQuestion.Kind.DEPTH:
        result = layer2.check_answer(asked, response.answer, windows, dimensions_for(question, depth_spec), model,
                                     allow_follow_up=first)
    else:
        result = {'version': layer2.VERSION, 'model_called': False, 'supported': bool(windows), 'dimensions': [],
                  'passages': [], 'follow_up': None if (windows or not first) else layer2.NO_SUPPORT_FOLLOW_UP,
                  'note': 'Judged in the credit path, on the provisional packet plus these passages.'}
    response.windows = windows
    response.support_check = result
    response.supported = result['supported']
    response.follow_up_text = result['follow_up'] or ''
    response.status = DepthResponse.Status.CHECKED
    response.save(update_fields=['windows', 'support_check', 'supported', 'follow_up_text', 'status'])
    return response


def check_pending(run_ref, model, *, ranker=None, max_calls=None):
    """Check every waiting response of a run whose documents are ready. Returns counts."""
    corpus = run_sources(run_ref)
    spec = depth.spec()
    checked = waiting = calls = 0
    for response in (DepthResponse.objects.filter(question__run_ref=run_ref, status=DepthResponse.Status.PENDING)
                     .select_related('question', 'parent').order_by('created_at')):
        if max_calls is not None and calls >= max_calls:
            waiting += 1
            continue
        check_response(response, model, corpus=corpus, ranker=ranker, depth_spec=spec)
        if response.status == DepthResponse.Status.CHECKED:
            checked += 1
            calls += int(bool(response.support_check.get('model_called')))
        else:
            waiting += 1
    return {'checked': checked, 'waiting': waiting, 'model_calls': calls}


# ------------------------------------------------------------------ optional additional evidence


def add_evidence(run_ref, rubric, *, document_ids, note='', picked=(), user=None):
    """Record documents the institution thinks were missed. It must pick at least one readiness area, key indicator
    or requirement; extraction's tags are added when the documents are checked."""
    documents = [str(d) for d in document_ids or []]
    if not documents:
        raise Layer2Error('Attach at least one document.')
    routing = layer2.route_additional(rubric, picked)
    if not routing['indicators']:
        raise Layer2Error('Pick at least one readiness area, key indicator or requirement this evidence is for.')
    return AdditionalEvidence.objects.create(run_ref=str(run_ref), document_ids=documents, note=(note or '').strip(),
                                             picked=[str(p) for p in picked], routing=routing, submitted_by=user)


def check_additional(item, rubric, *, attached=None, extracted=None, ranker=None):
    """Route with extraction's tags added and take the passages the credit path will judge. The search covers the
    submitted documents only: they are the evidence. Stays pending while a document is being extracted."""
    if item.status == AdditionalEvidence.Status.CHECKED:
        return item
    if attached is None:
        attached, ready = document_sources(item.document_ids)
        if not ready:
            return item
    if extracted is None:
        extracted = extracted_indicators(item.document_ids)
    routing = layer2.route_additional(rubric, item.picked, extracted)
    names = ' '.join(i['name'] for i in rubric['indicators'] if i['code'] in routing['indicators'])
    item.routing = routing
    item.windows = layer2.search_with_answer(item.note, attached, [], ranker=ranker, fallback_query=names)
    item.status = AdditionalEvidence.Status.CHECKED
    item.save(update_fields=['routing', 'windows', 'status'])
    return item


# ------------------------------------------------------------------ credit path


def credit_routes(run_ref):
    """Routes for layer2.credit_targets: checked answers to "nothing found" questions and checked additional evidence."""
    routes = []
    answers = (DepthResponse.objects.filter(question__run_ref=run_ref, question__kind=DepthQuestion.Kind.MISSING,
                                            status=DepthResponse.Status.CHECKED)
               .exclude(kind=DepthResponse.Kind.DONT_KNOW).select_related('question').order_by('created_at'))
    for response in answers:
        routes.append({'indicator': response.question.indicator_code, 'conditions': list(response.question.condition_ids),
                       'windows': response.windows, 'from': f'response:{response.pk}'})
    for item in AdditionalEvidence.objects.filter(run_ref=run_ref, status=AdditionalEvidence.Status.CHECKED):
        for code in item.routing.get('indicators', []):
            routes.append({'indicator': code, 'conditions': item.routing.get('conditions', {}).get(code),
                           'windows': item.windows, 'from': f'additional:{item.pk}'})
    return routes


def rejudge_credit(export, service, *, evaluate_fn=None, sources=None, routes=None, max_calls=36):
    """Re-judge the requirements new evidence was submitted for, on each one's provisional packet plus the new
    passages, with the main judge (part judgment, two passes, tie-break). Merge with layer2.merge_new_evidence.

    export: the provisional run's assessment export (run_id, rubric, population, reference_period, scope,
    assessment.records and assessment.traces). service: the model service for evaluate. Returns the merged records,
    the provisional and final scores, and an audit. Nothing is published (skeleton)."""
    try:
        run_ref, rubric, records = export['run_id'], export['rubric'], export['assessment']['records']
    except (KeyError, TypeError):
        raise Layer2Error('Not an assessment export: needs run_id, rubric and assessment.records.')
    traces = export['assessment'].get('traces') or []
    routes = credit_routes(run_ref) if routes is None else routes
    targets = layer2.credit_targets(records, rubric, routes)
    provisional = layer2.final_score(records, rubric)
    result = {'version': layer2.VERSION, 'run_ref': run_ref, 'routes': len(routes), 'provisional_score': provisional,
              'saved': False}
    if not targets:
        return {**result, 'targets': {}, 'context_audit': {}, 'merge': [], 'records': records,
                'final_score': provisional, 'traces': [], 'note': 'No new evidence to re-judge.'}
    contexts, context_audit = layer2.fixed_contexts(traces, targets)
    subset = layer2.subset_rubric(rubric, targets)
    if len(subset['indicators']) > max_calls:
        raise Layer2Error(f'{len(subset["indicators"])} key indicators to re-judge; the limit is {max_calls}.')
    if sources is None:
        documents = sorted({w['document_id'] for t in targets.values() for w in t['windows'] if w.get('document_id')})
        sources = run_sources(run_ref) + document_sources(documents)[0]
    if evaluate_fn is None:
        from .evaluation import evaluate as evaluate_fn
    outcome = evaluate_fn(sources, service=service, population=export.get('population') or 'Not recorded',
                          reference_period=export.get('reference_period') or 'Not recorded', rubric=subset,
                          scope=export.get('scope'), reviewed_evidence=export.get('reviewed_evidence'),
                          judgment='parts', agreement_passes=2, tie_break=True, max_calls=len(subset['indicators']),
                          fixed_contexts=contexts)
    packets = {t['indicator']: t.get('source_excerpts') or [] for t in traces}
    merged, merge_audit = layer2.merge_new_evidence(records, outcome['records'], packets)
    return {**result, 'targets': {code: t['conditions'] for code, t in targets.items()},
            'context_audit': context_audit, 'merge': merge_audit, 'records': merged,
            'final_score': layer2.final_score(merged, rubric), 'traces': outcome.get('traces', []),
            'note': 'Not published as a run yet: the run that refines the provisional one is still to be built.'}
