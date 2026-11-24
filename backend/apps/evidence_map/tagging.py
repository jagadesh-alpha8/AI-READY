"""Tag a sprint's pages: the model calls, the stored rows and the job's bookkeeping.

Specification: `claude/ai-ready-evidence-map-spec.md` (claude.ai project). Pull request 1 of the build: this reads and
stores; no assessment reads the map yet.

- Pages are the rendered evidence text a run would freeze (scoring.capability.storage.evidence_snapshot), so a tag's
  quotation is checked against the text the judge reads.
- Identical pages (whitespace and case ignored) are tagged once. Pages already tagged under the same map version and
  model are skipped, so a stopped or failed pass resumes where it ended.
- Every request is metered as AI usage under the stage "evidence_map", with the sprint; the pass stops starting new
  requests once its spend reaches the cap (requests already in flight finish).
- A failed request never fails the pass: its pages are recorded as failed, with the error, and stay reachable through
  the keyword fill once packets read the map.
"""
import logging
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.db.models import F, Sum
from django.utils import timezone

from apps.extraction.exceptions import AIOutputTruncated, PermanentExtractionError, RecoverableExtractionError
from apps.extraction.usage import DB_WRITE_LOCK, usage_scope

from . import spec
from .models import MapJob, MapPage

logger = logging.getLogger(__name__)
STAGE = 'evidence_map'
EFFORTS = ('none', 'low', 'medium', 'high', 'xhigh', 'max')


def tagger_service():
    """The client tagging calls go through: EVIDENCE_MAP_AI_API_KEY / _MODEL / _BASE_URL when set, else the scoring
    model (scoring.capability.model_choice). Claude answers in JSON output at EVIDENCE_MAP_AI_EFFORT."""
    from apps.extraction.services.ai_service import get_ai_service
    key = getattr(settings, 'EVIDENCE_MAP_AI_API_KEY', '')
    if key:
        model = getattr(settings, 'EVIDENCE_MAP_AI_MODEL', '')
        if not model:
            raise ImproperlyConfigured('EVIDENCE_MAP_AI_API_KEY is set but EVIDENCE_MAP_AI_MODEL is not.')
        service = get_ai_service(api_key=key, model=model, base_url=getattr(settings, 'EVIDENCE_MAP_AI_BASE_URL', '')
                                 or None)
    else:
        from apps.scoring.capability.model_choice import scoring_service
        service = scoring_service()
    effort = getattr(settings, 'EVIDENCE_MAP_AI_EFFORT', None)
    if effort is not None and effort not in EFFORTS:
        raise ImproperlyConfigured(f'EVIDENCE_MAP_AI_EFFORT must be one of {", ".join(EFFORTS)} (or empty).')
    if hasattr(service, 'json_output'):
        service.json_output = True    # Claude 5.5 models think by default, which a forced tool call can't combine with
        service.effort = effort
    if hasattr(service, 'cache_system'):
        service.cache_system = True   # the rubric (about 36,000 tokens) is the same system prompt for every request
    return service


def sprint_documents(sprint):
    """[{'document_id', 'filename', 'type', 'pages': count, 'readable': [{'id', 'number', 'text'}], 'unreadable'}]
    in the order a run freezes them."""
    from apps.documents.models import Document
    from apps.scoring.capability.storage import evidence_snapshot
    manifest, sources = evidence_snapshot(sprint)
    types = dict(Document.objects.filter(sprint=sprint).values_list('pk', 'document_type'))
    by_document = {}
    for source in sources:
        by_document.setdefault(source['document_id'], []).append(
            {'id': source['id'], 'number': source['page_number'], 'text': source['text']})
    out = []
    for entry in manifest:
        readable = sorted(by_document.get(entry['document_id'], []), key=lambda p: p['number'])
        out.append({'document_id': entry['document_id'], 'filename': entry.get('filename') or '',
                    'type': types.get(entry['document_id']) or types.get(_uuid(entry['document_id'])) or '',
                    'pages': entry.get('expected_pages') or len(entry.get('pages') or []), 'readable': readable,
                    'unreadable': max(0, len(entry.get('pages') or []) - len(readable))})
    return out


def _uuid(value):
    import uuid
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def plan(sprint, *, shape='one', service=None, documents=None, limit_pages=None):
    """What a pass would do, without model calls or writes: the map version, the model, and the chunks to send."""
    rubric, profiles, parts = spec.rubric_sources()
    version = spec.map_version(shape, rubric, profiles, parts)
    prompts = spec.system_prompts(shape, rubric, profiles, parts)
    model = getattr(service, 'model', None) or _model_name()
    docs = sprint_documents(sprint)
    if documents:
        docs = [d for d in docs if any(term.lower() in d['filename'].lower() for term in documents)]
    seen, representatives, total = set(), {}, 0
    for doc in docs:
        for page in doc['readable']:
            total += 1
            page['hash'] = spec.text_hash(page['text'])
            if page['hash'] not in seen:
                seen.add(page['hash'])
                representatives[page['id']] = page['hash']
    done = set(MapPage.objects.filter(map_version=version, model=model, status=MapPage.Status.TAGGED,
                                      text_hash__in=list(seen)).values_list('text_hash', flat=True))
    work, chosen = [], 0
    for doc in docs:
        pages = [p for p in doc['readable'] if p['id'] in representatives and p['hash'] not in done]
        if limit_pages is not None:
            pages = pages[:max(0, limit_pages - chosen)]
        chosen += len(pages)
        # The page before each page in the document (readable pages only), for the context-only carry-over.
        previous = {p['number']: q for q, p in zip(doc['readable'], doc['readable'][1:])}
        for chunk in spec.chunks(pages):
            work.append({'document': doc, 'pages': chunk, 'previous': previous.get(chunk[0]['number'])})
    system_chars = sum(len(p) for _, p in prompts)
    return {'version': version, 'model': model, 'shape': shape, 'rubric': rubric, 'prompts': prompts,
            'pages_total': total, 'pages_unique': len(seen), 'pages_done': len(done), 'pages_to_tag': chosen,
            'pages_unreadable': sum(d['unreadable'] for d in docs), 'chunks': work,
            'requests': len(work) * len(prompts),
            'input_chars': sum(sum(len(p['text']) for p in w['pages']) * len(prompts) for w in work)
                           + len(work) * system_chars}


def _model_name():
    if getattr(settings, 'EVIDENCE_MAP_AI_API_KEY', ''):
        return getattr(settings, 'EVIDENCE_MAP_AI_MODEL', '')
    from apps.scoring.capability.model_choice import scoring_model
    return scoring_model()


def run(sprint, *, shape='one', concurrency=4, max_cost_usd=None, documents=None, limit_pages=None, service=None,
        log=None):
    """Tag the sprint's untagged pages. Returns the MapJob."""
    service = service or tagger_service()
    work = plan(sprint, shape=shape, service=service, documents=documents, limit_pages=limit_pages)
    cap = Decimal(str(max_cost_usd if max_cost_usd is not None else getattr(settings, 'EVIDENCE_MAP_MAX_COST_USD', 5)))
    if type(concurrency) is not int or not 1 <= concurrency <= 16:
        raise ValueError('concurrency must be a whole number from 1 to 16.')
    job = MapJob.objects.create(sprint=sprint, map_version=work['version'], model=work['model'], shape=shape,
                                pages_total=work['pages_total'], pages_to_tag=work['pages_to_tag'],
                                pages_skipped=work['pages_unreadable'], chunks_total=len(work['chunks']),
                                spend_cap_usd=cap)
    state = {'stop': False, 'checks': Counter()}
    lock = threading.Lock()
    say = log or (lambda message: None)

    def spent():
        from apps.extraction.models import AIUsage
        total = AIUsage.objects.filter(sprint=sprint, stage=STAGE, created_at__gte=job.started_at).aggregate(
            total=Sum('cost_usd'))['total']
        return Decimal(total or 0)

    def one(item):
        try:
            if state['stop']:
                return
            results, checks, requests = tag_chunk(service, work['prompts'], work['rubric'], item, sprint=sprint,
                                                  should_stop=lambda: state['stop'])
            save(job, item['pages'], results)
            cost = spent()
            with lock:
                state['checks'].update(checks)
                if cost >= cap:
                    state['stop'] = True
            tagged = sum(1 for r in results.values() if 'tags' in r)
            with DB_WRITE_LOCK:
                MapJob.objects.filter(pk=job.pk).update(
                    chunks_done=F('chunks_done') + 1, requests=F('requests') + requests,
                    pages_tagged=F('pages_tagged') + tagged, pages_failed=F('pages_failed') + len(results) - tagged,
                    spend_usd=cost)
            say(f'{item["document"]["filename"]} pages {item["pages"][0]["number"]}-{item["pages"][-1]["number"]}: '
                f'{tagged}/{len(results)} tagged, ${cost:.4f} so far')
        finally:
            if concurrency > 1:
                connections.close_all()   # each worker thread has its own database connection

    try:
        if concurrency == 1:
            for item in work['chunks']:
                one(item)
        else:
            import contextvars
            with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix='evidence-map') as pool:
                list(pool.map(lambda item: contextvars.copy_context().run(one, item), work['chunks']))
        status = MapJob.Status.STOPPED if state['stop'] else MapJob.Status.COMPLETED
        error = ''
    except Exception as exc:   # a bug or the database: the pages already stored stay stored
        logger.exception('evidence_map.run failed sprint=%s', sprint.pk)
        status, error = MapJob.Status.FAILED, f'{type(exc).__name__}: {exc}'[:2000]
    job.refresh_from_db()
    job.status, job.error, job.finished_at = status, error, timezone.now()
    job.checks = dict(state['checks'])
    job.spend_usd = spent()
    job.save(update_fields=['status', 'error', 'finished_at', 'checks', 'spend_usd'])
    return job


def tag_chunk(service, prompts, rubric, item, *, sprint=None, should_stop=lambda: False):
    """({page number: {'page_type', 'tags'} or {'error'}}, checks, requests made) for one chunk, every prompt shape
    call included. A page is tagged only when every call listed it."""
    numbers = [p['number'] for p in item['pages']]
    per_page = {n: [] for n in numbers}
    errors, checks, requests = {}, Counter(), 0
    for area, system in prompts:
        got, err, counts, made = _ask(service, system, rubric, item, sprint=sprint, should_stop=should_stop)
        checks.update(counts)
        requests += made
        for n in numbers:
            if n in got:
                per_page[n].append(got[n])
            else:
                errors.setdefault(n, f'{area}: {err.get(n, "not listed in the answer")}')
    out = {}
    for n in numbers:
        if n in errors:
            out[n] = {'error': errors[n]}
        else:
            out[n] = spec.merge(per_page[n])
    return out, checks, requests


def _ask(service, system, rubric, item, *, sprint=None, should_stop=lambda: False, depth=0):
    """({number: result}, {number: error}, checks, requests) for one prompt over one chunk. A truncated answer is
    asked again in two halves; pages a valid answer left out are asked again once on their own."""
    pages = item['pages']
    if should_stop():
        return {}, {p['number']: 'stopped at the spend cap' for p in pages}, Counter(), 0
    content = spec.user_content(item['document'], pages, item.get('previous'))
    requests = 0
    try:
        requests += 1
        response = _call(service, system, content, sprint, item['document'])
    except AIOutputTruncated:
        if len(pages) == 1 or depth >= 3:
            return {}, {p['number']: 'answer truncated' for p in pages}, Counter({'truncated': 1}), requests
        half = len(pages) // 2
        first, second = pages[:half], pages[half:]
        out, errs, checks = {}, {}, Counter({'truncated_split': 1})
        for part, previous in ((first, item.get('previous')), (second, first[-1])):
            got, err, counts, made = _ask(service, system, rubric, {**item, 'pages': part, 'previous': previous},
                                          sprint=sprint, should_stop=should_stop, depth=depth + 1)
            out.update(got)
            errs.update(err)
            checks.update(counts)
            requests += made
        return out, errs, checks, requests
    except (RecoverableExtractionError, PermanentExtractionError) as exc:
        message = f'{type(exc).__name__}: {exc}'[:500]
        return {}, {p['number']: message for p in pages}, Counter({'request_failed': 1}), requests
    checked = spec.validate(pages, response, rubric)
    out, checks = dict(checked['pages']), Counter(checked['counts'])
    errs = {}
    if checked['missing'] and depth == 0:
        retry = [p for p in pages if p['number'] in checked['missing']]
        got, err, counts, made = _ask(service, system, rubric, {**item, 'pages': retry}, sprint=sprint,
                                      should_stop=should_stop, depth=1)
        out.update(got)
        errs.update(err)
        checks.update(counts)
        requests += made
    elif checked['missing']:
        errs.update({n: 'not listed in the answer' for n in checked['missing']})
    return out, errs, checks, requests


def _call(service, system, content, sprint, document):
    """One request, with one retry of a transient failure."""
    for attempt in range(2):
        try:
            with usage_scope(sprint=sprint, stage=STAGE):
                return service.extract_structured_data(system_prompt=system, user_content=content,
                                                       response_schema=spec.SCHEMA, schema_name=spec.SCHEMA_NAME)
        except AIOutputTruncated:
            raise
        except RecoverableExtractionError as exc:
            if attempt:
                raise
            time.sleep(min(30, max(1, exc.retry_after or 2)))


def save(job, pages, results):
    """Store one chunk's pages. A tagged row is never replaced by a failure."""
    with DB_WRITE_LOCK:
        for page in pages:
            result = results.get(page['number']) or {'error': 'no result'}
            key = dict(text_hash=page.get('hash') or spec.text_hash(page['text']), map_version=job.map_version,
                       model=job.model)
            if 'error' in result:
                if MapPage.objects.filter(**key, status=MapPage.Status.TAGGED).exists():
                    continue
                MapPage.objects.update_or_create(**key, defaults={'status': MapPage.Status.FAILED, 'tags': [],
                                                                  'page_type': '', 'error': result['error'][:2000],
                                                                  'page_id': page['id']})
            else:
                MapPage.objects.update_or_create(**key, defaults={'status': MapPage.Status.TAGGED,
                                                                  'tags': result['tags'],
                                                                  'page_type': result['page_type'], 'error': '',
                                                                  'page_id': page['id']})


def coverage(sprint, version, model, documents=None):
    """Per page of the sprint, what the map holds under (version, model): for exports and, later, for runs."""
    docs = documents if documents is not None else sprint_documents(sprint)
    hashes = {p['id']: spec.text_hash(p['text']) for d in docs for p in d['readable']}
    rows = {r.text_hash: r for r in MapPage.objects.filter(map_version=version, model=model,
                                                           text_hash__in=set(hashes.values()))}
    counts = Counter()
    for h in hashes.values():
        row = rows.get(h)
        counts[row.status if row else 'not_tagged'] += 1
    counts['unreadable'] = sum(d['unreadable'] for d in docs)
    return {'pages': len(hashes), **counts}, rows, hashes
