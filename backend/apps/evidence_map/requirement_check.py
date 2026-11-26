"""The requirement check (check-1): tagging the other way round. No judge, no score.

Tagging reads each page and asks which requirements it serves. Its remaining misses on the VISTAS sprint (26 Nov,
map at 100,000 characters) were mostly pages it read and left without a strong tag for the indicator a judge later
credited (an AI auto-grading patent row, a list of uploaded documents). The check goes requirement by requirement
instead: for each requirement of an indicator, the pages a word search ranks closest to it that the map holds no
direct or supporting tag on for that indicator, PER_REQUIREMENT of them, are sent in one request per indicator, and
Claude is asked only whether each is evidence for that indicator.

What comes back is checked like a tagging answer (spec.validate); only direct and supporting tags for the indicator
asked about, with a quotation found on the page, are kept. They are added to the page's stored row with
`origin: requirement_check`, so packets use them as they use the tagger's; re-tagging keeps them (tagging.save).
Only pages the tagger read (a tagged row) are checked: an unread page has no row to add to, and the packet already
sends unread pages first. Each (indicator, page) pair is checked once per map version and model; the job's checks
record which were asked.
"""
import logging
from collections import Counter
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.extraction.exceptions import AIOutputTruncated, PermanentExtractionError, RecoverableExtractionError
from apps.extraction.usage import usage_scope

from . import packet, spec, tagging
from .models import MapJob, MapPage

logger = logging.getLogger(__name__)
VERSION = 'check-1'
ORIGIN = 'requirement_check'
SHAPE = 'check-1'               # the MapJob's shape field for a check pass
PER_REQUIREMENT = 3             # pages per requirement (starting value)
WINDOW_CHARS = packet.WINDOW_CHARS
KEEP = ('direct', 'supporting')
#: Words that say nothing about a requirement: a page sharing only these with it is not a candidate.
STOP = frozenset('a an and any are as at be been by for from has have in into is it its of on or that the their this '
                 'those to was were which with within an'.split())

NOTE = """THIS IS A SECOND CHECK FOR ONE INDICATOR
The pages below come from different documents. Each was read once already and not tagged
as evidence for the indicator below, but a word search ranks it close to one of its
requirements. Read each page again against this indicator only. Tag it when it is evidence
for any of its requirements, with the same strengths and rules as above; leave it untagged
when it is not. Most pages here are not evidence: tag only what a reviewer should read. A
page may show only the part of the page the search found closest, so it can begin or end
mid-sentence. Number the pages as they are numbered below."""


def system_prompt(indicator, profiles, parts):
    return spec.PROMPT + '\n\n' + NOTE + '\n\nREQUIREMENTS\n' + spec.indicator_block(indicator, profiles, parts)


def user_content(candidates):
    lines = ['PAGES FROM SEVERAL DOCUMENTS', '']
    for n, c in enumerate(candidates, 1):
        lines += [f'--- Page {n} --- (document: {c["filename"] or "(no name)"}, its page {c["page_number"]})',
                  c['text'], '']
    return '\n'.join(lines).rstrip() + '\n'


def _strong_for(tags, code):
    return any(t.get('indicator') == code and t.get('strength') in KEEP for t in tags or [])


def plan(sprint, *, map_version, model, per_requirement=PER_REQUIREMENT, indicators=None):
    """What a check pass would send: per indicator its candidate pages. No model calls, no writes."""
    from .tagging import sprint_documents
    rubric, profiles, parts = spec.rubric_sources()
    rows = {r.text_hash: r for r in MapPage.objects.filter(map_version=map_version, model=model,
                                                            status=MapPage.Status.TAGGED)}
    asked = set()
    for job in MapJob.objects.filter(sprint=sprint, map_version=map_version, model=model, shape=SHAPE):
        for code, hashes in ((job.checks or {}).get('asked') or {}).items():
            asked.update((code, h) for h in hashes)
    pages, seen = [], set()
    for doc in sprint_documents(sprint):
        for page in doc['readable']:
            h = spec.text_hash(page['text'])
            if h in seen:
                continue
            seen.add(h)
            pages.append({'hash': h, 'text': page['text'], 'filename': doc['filename'], 'page_number': page['number'],
                          'page_id': page['id']})
    frequency = Counter()
    for page in pages:
        frequency.update(set(packet._tokens(page['text'])))
    work = []
    for indicator in rubric['indicators']:
        code = indicator['code']
        if indicators and code not in indicators and spec.short(code) not in indicators:
            continue
        pool = [p for p in pages if p['hash'] in rows and (code, p['hash']) not in asked
                and not _strong_for(rows[p['hash']].tags, code)]
        chosen, ids = [], set()
        for condition in indicator['conditions']:
            query = [w for w in packet._tokens(condition['text'] + ' ' + (profiles.get(condition['id']) or {})
                                               .get('query', '')) if len(w) > 2 and w not in STOP]
            scored = []
            for page in pool:
                if page['hash'] in ids:
                    continue
                start, end = packet.window(page['text'], None, query, size=WINDOW_CHARS)
                score = packet.keyword_score(page['text'][start:end], query, frequency, len(pages))
                if score > 0:
                    scored.append((-score, page['hash'], start, end, page))
            for _, h, start, end, page in sorted(scored, key=lambda r: r[:3])[:per_requirement]:
                ids.add(h)
                chosen.append({**page, 'text': page['text'][start:end], 'offset': start,
                               'requirement': condition['id']})
        if chosen:
            work.append({'indicator': indicator, 'pages': chosen})
    return {'version': VERSION, 'map_version': map_version, 'model': model, 'work': work, 'rubric': rubric,
            'profiles': profiles, 'parts': parts, 'requests': len(work),
            'pages': sum(len(w['pages']) for w in work),
            'input_chars': sum(len(system_prompt(w['indicator'], profiles, parts)) + len(user_content(w['pages']))
                               for w in work)}


def _keep(indicator, candidates, response, rubric, counts):
    """{text hash: [tags]} from one answer: the indicator's direct and supporting tags with a quotation found on the
    full page."""
    chunk = [{'number': n, 'text': c['text']} for n, c in enumerate(candidates, 1)]
    checked = spec.validate(chunk, response, rubric)
    counts.update(checked['counts'])
    out = {}
    for n, result in checked['pages'].items():
        page = candidates[n - 1]
        for tag in result['tags']:
            if tag['indicator'] != indicator['code'] or tag['strength'] not in KEEP:
                counts['check_tag_not_kept'] += 1
                continue
            if not tag['quote_found']:
                counts['check_quote_not_found'] += 1
                continue
            out.setdefault(page['hash'], []).append({**tag, 'origin': ORIGIN, 'check_version': VERSION})
            counts['check_tags_kept'] += 1
    return out


def run(sprint, *, map_version, model=None, per_requirement=PER_REQUIREMENT, max_cost_usd=0.5, indicators=None,
        service=None, log=None):
    """Check the sprint's candidates, one request per indicator. Returns the MapJob (shape check-1)."""
    from .tagging import STAGE, _model_name, tagger_service
    say = log or (lambda message: None)
    service = service or tagger_service()
    model = model or getattr(service, 'model', None) or _model_name()
    work = plan(sprint, map_version=map_version, model=model, per_requirement=per_requirement, indicators=indicators)
    cap = Decimal(str(max_cost_usd))
    job = MapJob.objects.create(sprint=sprint, map_version=map_version, model=model, shape=SHAPE,
                                pages_to_tag=work['pages'], chunks_total=work['requests'], spend_cap_usd=cap)

    def spent():
        from apps.extraction.models import AIUsage
        total = AIUsage.objects.filter(sprint=sprint, stage=STAGE, created_at__gte=job.started_at).aggregate(
            total=Sum('cost_usd'))['total']
        return Decimal(total or 0)

    counts, asked, status, error = Counter(), {}, MapJob.Status.COMPLETED, ''
    try:
        for item in work['work']:
            if spent() >= cap:
                status = MapJob.Status.STOPPED
                break
            indicator, candidates = item['indicator'], item['pages']
            system = system_prompt(indicator, work['profiles'], work['parts'])
            try:
                with usage_scope(sprint=sprint, stage=STAGE):
                    response = service.extract_structured_data(system_prompt=system,
                                                               user_content=user_content(candidates),
                                                               response_schema=spec.SCHEMA,
                                                               schema_name=spec.SCHEMA_NAME)
            except (AIOutputTruncated, RecoverableExtractionError, PermanentExtractionError) as exc:
                counts['check_request_failed'] += 1
                say(f'{indicator["code"]}: request failed ({type(exc).__name__}); its pages stay unchecked')
                continue
            found = _keep(indicator, candidates, response, work['rubric'], counts)
            added = tagging.add_tags(map_version=map_version, model=model, found=found)
            asked[indicator['code']] = sorted({c['hash'] for c in candidates})
            MapJob.objects.filter(pk=job.pk).update(chunks_done=len(asked), requests=len(asked),
                                                    pages_tagged=sum(len(v) for v in asked.values()),
                                                    spend_usd=spent())
            say(f'{indicator["code"]}: {len(candidates)} pages checked, {added} tags added, ${spent():.4f} so far')
    except Exception as exc:   # the tags already added stay added
        logger.exception('evidence_map.requirement_check failed sprint=%s', sprint.pk)
        status, error = MapJob.Status.FAILED, f'{type(exc).__name__}: {exc}'[:2000]
    job.refresh_from_db()
    job.status, job.error, job.finished_at, job.spend_usd = status, error, timezone.now(), spent()
    job.checks = {**dict(counts), 'version': VERSION, 'asked': asked}
    job.save(update_fields=['status', 'error', 'finished_at', 'spend_usd', 'checks'])
    return job
