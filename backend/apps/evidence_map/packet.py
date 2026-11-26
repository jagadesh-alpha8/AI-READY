"""Building a judge's packet from the evidence map (allocation evidence-map-then-keyword-v1). No model calls.

Specification: claude.ai project doc claude/ai-ready-evidence-map-spec.md, "Building a packet". In short:
- pages the map tagged for the indicator go first, as windows around the tag's quotation: direct tags, then
  supporting, the requirements taking turns; with the same-area band (CAPABILITY_MAP_SAME_AREA), then pages tagged
  direct or supporting for the other indicators of the same area, nearest to a requirement's words first; then a
  little context from documents already in the packet; then the extracted-evidence lane (ignoring review status);
  then today's keyword selector fills the rest;
- at least `fill_share` of the cap is kept for the keyword fill, so every page stays reachable (the map orders, it
  never excludes); pages tagged topical for the indicator go to the back of the fill;
- the judge sees plain windows: no tier, strength or tag goes into the request. Each window's step and tag are kept
  in a separate trace.

Frozen per run: `freeze(sources, ...)` copies the tags for the run's pages into the run's inputs, so re-tagging never
changes an existing run, and the packet depends only on the run's documents and its frozen map.
"""
import math
import re
from collections import Counter

from . import spec

ALLOCATION = 'evidence-map-then-keyword-v1'
#: The same packet with a semantic step in the fill (semantic.py; CAPABILITY_MAP_FILL=semantic).
SEMANTIC_ALLOCATION = 'evidence-map-then-semantic-v1'
ALLOCATIONS = (ALLOCATION, SEMANTIC_ALLOCATION)
#: The same-area band (26 Nov): the tagger often finds a page and its area but names a sibling indicator (Self-Study
#: Report, per-area map: 17 of 83 credited pages). A packet then also takes the area's other strong tags, after its
#: own, in at most SAME_AREA_SHARE of the tagged share they leave, so the keyword fill keeps its third. Uncapped, the
#: band crowded out keyword fill that reached credited pages (60,000: 90 -> 84 full credit). Frozen per run as
#: retrieval_policy.same_area.
SAME_AREA_VERSION = 'same-area-1'
SAME_AREA_STRENGTHS = ('direct', 'supporting')
SAME_AREA_SHARE = (1, 3)   # of the tagged share left after the indicator's own tags (26 Nov sweep: 1/3 and 1/2 best)
CAP_CHARS = 60000          # starting value (spec); CAPABILITY_MAP_CAP_CHARS
FILL_SHARE = (1, 3)        # at least a third of the cap for the keyword fill
WINDOW_CHARS = 2400
CONTEXT_SHARE = (1, 10)    # context tags: at most a tenth of the cap
SEMANTIC_SHARE = (1, 2)    # semantic step: at most half of what the fill has (semantic.SHARE)
STEPS = ('direct', 'supporting', 'same_area_direct', 'same_area_supporting', 'context', 'extracted_evidence', 'keyword_fill_unread', 'semantic_fill', 'keyword_fill',
         'keyword_fill_topical')


# ------------------------------------------------------------------ freezing


def freeze(sources, *, map_version, model):
    """{'pages': {text hash: {'page_type', 'tags'}}, 'coverage': {...}} for the run's pages, from the stored map.

    Identical pages share one entry. A page without a stored row (or whose row failed) is untagged: it stays
    reachable through the keyword fill, and the coverage says how many."""
    from .models import MapPage
    hashes = {spec.text_hash(s['text']) for s in sources if (s.get('text') or '').strip()}
    rows = MapPage.objects.filter(map_version=map_version, model=model, text_hash__in=hashes)
    pages, status = {}, Counter()
    for row in rows:
        status[row.status] += 1
        if row.status == MapPage.Status.TAGGED:
            pages[row.text_hash] = {'page_type': row.page_type, 'tags': row.tags}
    coverage = {'pages': len(hashes), 'tagged': status[MapPage.Status.TAGGED], 'failed': status[MapPage.Status.FAILED],
                'skipped': status[MapPage.Status.SKIPPED],
                'untagged': len(hashes) - sum(status.values())}
    return {'pages': pages, 'coverage': coverage}


# ------------------------------------------------------------------ scoring and windows


def _tokens(text):
    return re.findall(r'[a-z0-9]+', (text or '').lower())


def keyword_score(text, query, frequency, pages):
    """A plain BM25-style score of `text` for a query's words (orders candidates inside one requirement's turn)."""
    words = Counter(_tokens(text))
    length = sum(words.values()) or 1
    total = 0.0
    for term in set(query) & words.keys():
        inverse = math.log(1 + (pages - frequency[term] + .5) / (frequency[term] + .5))
        count = words[term]
        total += inverse * count * 2.2 / (count + 1.2 * (.25 + .75 * length / 2000))
    return total


def window(text, quote, query, *, size=WINDOW_CHARS):
    """(start, end) of the span sent for a tag: the whole page when it fits; else `size` characters around the
    located quotation, a third before and two thirds after; else the page's best window for the query."""
    if len(text) <= size:
        return 0, len(text)
    span = spec.locate(text, quote) if quote else None
    if span is not None:
        start = max(0, min(span[0] - size // 3, len(text) - size))
        return start, start + size
    best, best_start = -1.0, 0
    step = size // 2
    query = set(query)
    for start in range(0, max(1, len(text) - size + step), step):
        piece = _tokens(text[start:start + size])
        score = sum(1 for w in piece if w in query)
        if score > best:
            best, best_start = score, start
    start = min(best_start, max(0, len(text) - size))
    return start, start + size


class Packet:
    """Windows chosen so far: merges overlapping spans on a page and pays only for new characters."""

    def __init__(self, cap):
        self.cap = cap
        self.spans = []      # [source, start, end, trace]
        self.used = 0

    def pages(self):
        return {s[0]['id'] for s in self.spans}

    def documents(self):
        return {s[0].get('document_id') for s in self.spans}

    def add(self, source, start, end, trace, limit):
        """Add [start, end) of `source` if it fits under `limit` characters in all; True when anything was added."""
        joined = [s for s in self.spans if s[0]['id'] == source['id'] and s[1] < end and start < s[2]]
        if not joined:
            if self.used + (end - start) > limit:
                return False
            self.spans.append([source, start, end, [trace]])
            self.used += end - start
            return True
        low, high = min([start] + [s[1] for s in joined]), max([end] + [s[2] for s in joined])
        added = (high - low) - sum(s[2] - s[1] for s in joined)
        if added <= 0:
            joined[0][3].append({**trace, 'already_in_packet': True})
            return False
        if self.used + added > limit:
            return False
        first = joined[0]
        first[1], first[2] = low, high
        for other in joined[1:]:
            first[3].extend(other[3])
        first[3].append(trace)
        self.spans[:] = [s for s in self.spans if s is first or s not in joined]
        self.used += added
        return True

    def context(self):
        """Windows in the order they were filled, as the judge receives them (no step, tag or strength)."""
        out = []
        for source, start, end, _ in self.spans:
            item = {k: v for k, v in source.items() if k not in ('text', 'report_timestamp', 'retrieval_hints')}
            out.append({**item, 'text': source['text'][start:end], 'text_offset': start})
        return out

    def trace(self):
        return [{'id': s[0]['id'], 'document_id': s[0].get('document_id'), 'page_number': s[0].get('page_number'),
                 'text_offset': s[1], 'chars': s[2] - s[1], 'reasons': s[3]} for s in self.spans]


def _subtract(start, end, spans):
    """[start, end) minus the given spans, as a list of (start, end) pieces in order."""
    pieces = [(start, end)]
    for a, b in sorted(spans):
        pieces = [p for s, e in pieces for p in ((s, min(e, a)), (max(s, b), e)) if p[0] < p[1]]
    return pieces


def _uncovered(source, spans):
    """The source as the keyword fill should see it: unchanged when nothing of it is in the packet; with the held
    spans blanked out (same length, so offsets stay exact) when part of it is; None when all of it is."""
    text = source.get('text') or ''
    if not spans:
        return source
    left = _subtract(0, len(text), spans)
    if not any(text[s:e].strip() for s, e in left):
        return None
    chars = list(text)
    for a, b in spans:
        for i in range(max(0, a), min(len(chars), b)):
            if not chars[i].isspace():
                chars[i] = ' '
    return {**source, 'text': ''.join(chars)}


# ------------------------------------------------------------------ the builder


def area_of(code):
    """An indicator's area ('AIQIF-C1.1' -> 'AIQIF-C1')."""
    return (code or '').rsplit('.', 1)[0]


def build(indicator, sources, frozen_map, *, cap=CAP_CHARS, keyword_fill, lane=None, window_chars=WINDOW_CHARS,
          semantic=None, same_area=False):
    """(context, trace) for one indicator.

    sources: the run's pages as retrieval reads them (after deduplication). frozen_map: freeze()'s result.
    keyword_fill(sources, max_chars) -> windows: today's keyword selector, run over the pages not yet in the packet.
    lane(context, budget) -> (context, audit): the extracted-evidence lane, or None.
    semantic: a semantic.TagSearch (allocation evidence-map-then-semantic-v1), or None for the keyword fill alone.
    same_area: also take the area's other indicators' direct and supporting tags, after this indicator's own."""
    code = indicator['code']
    requirements = [c['id'] for c in indicator.get('conditions', [])]
    texts = {c['id']: c['text'] for c in indicator.get('conditions', [])}
    tagged_limit = cap - cap * FILL_SHARE[0] // FILL_SHARE[1]
    pages_map = frozen_map.get('pages') or {}
    frequency, readable = Counter(), [s for s in sources if (s.get('text') or '').strip()]
    for source in readable:
        frequency.update(set(_tokens(source['text'])))
    by_hash = {}
    tags_for, topical, area_tags_for = {}, set(), {}
    area = area_of(code)
    for source in readable:
        entry = pages_map.get(spec.text_hash(source['text']))
        if not entry:
            continue
        for tag in entry.get('tags') or []:
            if tag.get('indicator') != code:
                if same_area and tag.get('indicator') and area_of(tag['indicator']) == area \
                        and tag.get('strength') in SAME_AREA_STRENGTHS:
                    area_tags_for.setdefault(source['id'], []).append(tag)
                continue
            if tag.get('strength') == 'topical':
                topical.add(source['id'])
                continue
            tags_for.setdefault(source['id'], []).append(tag)
        by_hash.setdefault(spec.text_hash(source['text']), source)
    packet = Packet(cap)
    skipped = Counter()

    def candidates(strength, requirement):
        rows = []
        query = _tokens(texts.get(requirement) or indicator.get('name', ''))
        for source in readable:
            for tag in tags_for.get(source['id'], []):
                if tag['strength'] != strength:
                    continue
                if requirement is None and tag.get('requirements'):
                    continue
                if requirement is not None and requirement not in (tag.get('requirements') or []):
                    continue
                start, end = window(source['text'], tag.get('quote'), query, size=window_chars)
                score = keyword_score(source['text'][start:end], query, frequency, len(readable))
                rows.append((source, start, end, tag, score))
        return rows

    def fill_turns(strength):
        queues = {}
        for requirement in requirements + [None]:
            rows = candidates(strength, requirement)
            queues[requirement] = rows
        used_docs = {r: set() for r in queues}
        while any(queues.values()):
            for requirement in requirements + [None]:
                rows = queues[requirement]
                if not rows:
                    continue
                # A document not yet used for this requirement first; then keyword score; then text hash, offset.
                rows.sort(key=lambda r: (r[0].get('document_id') in used_docs[requirement], -r[4],
                                         spec.text_hash(r[0]['text']), r[1]))
                source, start, end, tag, _ = rows.pop(0)
                trace = {'step': strength, 'requirement': requirement, 'requirements': tag.get('requirements') or [],
                         'quote_found': tag.get('quote_found'), 'reason': tag.get('reason')}
                if tag.get('origin'):
                    trace['origin'] = tag['origin']
                if packet.add(source, start, end, trace, tagged_limit):
                    used_docs[requirement].add(source.get('document_id'))
                elif packet.used + (end - start) > tagged_limit:
                    skipped[strength] += 1
            if packet.used >= tagged_limit:
                skipped[strength] += sum(len(rows) for rows in queues.values())
                break

    fill_turns('direct')
    fill_turns('supporting')

    # The same-area band: the area's other strong tags, direct before supporting; inside a strength the requirements
    # take turns, each taking the window nearest its own words (keyword score), then text hash and offset.
    area_audit = None
    if same_area:
        area_audit = {'version': SAME_AREA_VERSION, 'candidates': sum(len(t) for t in area_tags_for.values()),
                      'chosen': 0, 'chars': 0}
        before = packet.used
        area_limit = packet.used + (tagged_limit - packet.used) * SAME_AREA_SHARE[0] // SAME_AREA_SHARE[1]
        seen = set()
        for strength in SAME_AREA_STRENGTHS:
            queues = {}
            for requirement in requirements:
                query = _tokens(texts.get(requirement) or indicator.get('name', ''))
                rows = []
                for source in readable:
                    for tag in area_tags_for.get(source['id'], []):
                        if tag['strength'] != strength:
                            continue
                        start, end = window(source['text'], tag.get('quote'), query, size=window_chars)
                        score = keyword_score(source['text'][start:end], query, frequency, len(readable))
                        rows.append((-score, spec.text_hash(source['text']), start, end, source, tag))
                queues[requirement] = sorted(rows, key=lambda r: r[:3])
            while any(queues.values()) and packet.used < area_limit:
                for requirement in requirements:
                    queue = queues[requirement]
                    while queue:
                        _, _, start, end, source, tag = queue.pop(0)
                        if (source['id'], start, end) in seen:
                            continue
                        seen.add((source['id'], start, end))
                        trace = {'step': 'same_area_' + strength, 'requirement': requirement,
                                 'tag_indicator': tag.get('indicator'), 'requirements': tag.get('requirements') or [],
                                 'quote_found': tag.get('quote_found'), 'reason': tag.get('reason')}
                        if packet.add(source, start, end, trace, area_limit):
                            area_audit['chosen'] += 1
                            break
                        if packet.used + (end - start) > area_limit:
                            skipped['same_area_' + strength] += 1
        area_audit['chars'] = packet.used - before

    # Context: only from documents already in the packet, the nearest page first, one per document.
    context_limit = min(tagged_limit, packet.used + cap * CONTEXT_SHARE[0] // CONTEXT_SHARE[1])
    documents = packet.documents()
    chosen_pages = {(s[0].get('document_id'), s[0].get('page_number')) for s in packet.spans}
    per_document = set()
    rows = []
    for source in readable:
        for tag in tags_for.get(source['id'], []):
            if tag['strength'] != 'context' or source.get('document_id') not in documents:
                continue
            numbers = [n for d, n in chosen_pages if d == source.get('document_id') and isinstance(n, int)]
            distance = min((abs((source.get('page_number') or 0) - n) for n in numbers), default=10 ** 6)
            rows.append((distance, spec.text_hash(source['text']), source, tag))
    for distance, _, source, tag in sorted(rows, key=lambda r: r[:2]):
        if source.get('document_id') in per_document:
            continue
        start, end = window(source['text'], tag.get('quote'), _tokens(indicator.get('name', '')), size=window_chars)
        if packet.add(source, start, end, {'step': 'context', 'requirements': tag.get('requirements') or [],
                                           'reason': tag.get('reason')}, context_limit):
            per_document.add(source.get('document_id'))

    context = packet.context()
    lane_audit = None
    if lane is not None:
        before = len(context)
        context, lane_audit = lane(context, max(0, tagged_limit - packet.used))
        lane_chars = sum(len(w['text']) for w in context[before:])
    else:
        lane_chars = 0

    # The fill, over every span not yet in the packet (rule 2: the map orders, it never excludes). A page already in
    # the packet joins it with its chosen spans blanked out, so the rest of a long tagged page can still be reached;
    # offsets are kept, and each fill window is trimmed back to text the packet does not hold yet. In bands:
    #   1. pages the tagger never read (failed, or no row): they have no other way in; keyword-ranked;
    #   2. with semantic search: tags for other indicators closest in meaning to a requirement (semantic.py), up to
    #      semantic.SHARE of what is left;
    #   3. pages the tagger read: keyword-ranked, as before;
    #   4. pages tagged topical for this indicator, last.
    covered = {}
    for w in context:
        if w.get('text_offset') is None:
            covered[w['id']] = [(0, 10 ** 9)]      # no offset: treat the whole page as held (the old behaviour)
        else:
            covered.setdefault(w['id'], []).append((w['text_offset'], w['text_offset'] + len(w.get('text') or '')))
    remaining = cap - packet.used - lane_chars
    fill = []
    originals = {s['id']: s for s in sources}
    unread = {s['id'] for s in sources if spec.text_hash(s.get('text') or '') not in pages_map}

    def take(step, source, start, end, base=None):
        """Add [start, end) of `source` to the fill, less what the packet already holds; the characters added. base: the
        selector's window, whose own fields (e.g. a report timestamp's role) are kept."""
        nonlocal remaining
        added = 0
        for a, b in _subtract(start, end, covered.get(source['id'], [])):
            piece = source['text'][a:b]
            if not piece.strip() or len(piece) > remaining:
                continue
            item = base if base is not None else {
                k: v for k, v in source.items() if k not in ('text', 'report_timestamp', 'retrieval_hints')}
            fill.append((step, {**item, 'text': piece, 'text_offset': a}))
            covered.setdefault(source['id'], []).append((a, b))
            remaining -= len(piece)
            added += len(piece)
        return added

    def keyword_band(step, wanted):
        pool = [p for p in (_uncovered(s, covered.get(s['id'])) for s in sources if wanted(s)) if p is not None]
        if remaining < 100 or not pool:
            return
        for w in keyword_fill(pool, remaining):
            source = originals.get(w['id'])
            if source is None or w.get('text_offset') is None:
                continue
            take(step, source, w['text_offset'], w['text_offset'] + len(w.get('text') or ''), base=w)

    keyword_band('keyword_fill_unread', lambda s: s['id'] in unread and s['id'] not in topical)
    semantic_audit = None
    if semantic is not None and remaining >= 100:
        semantic_audit = _semantic_band(indicator, readable, pages_map, code, topical, semantic, take,
                                        remaining * SEMANTIC_SHARE[0] // SEMANTIC_SHARE[1], window_chars)
    keyword_band('keyword_fill', lambda s: s['id'] not in unread and s['id'] not in topical)
    keyword_band('keyword_fill_topical', lambda s: s['id'] in topical)
    context = context + [w for _, w in fill]
    trace = {'allocation': SEMANTIC_ALLOCATION if semantic is not None else ALLOCATION, 'cap_chars': cap,
             'tagged_limit_chars': tagged_limit,
             'tagged_chars': packet.used, 'lane_chars': lane_chars,
             'fill_chars': sum(len(w.get('text') or '') for _, w in fill),
             'windows': packet.trace() + [{'id': w['id'], 'document_id': w.get('document_id'),
                                            'page_number': w.get('page_number'), 'text_offset': w.get('text_offset'),
                                            'chars': len(w.get('text') or ''), 'reasons': [{'step': step}]}
                                           for step, w in fill],
             'left_out_for_space': dict(skipped), 'topical_pages': len(topical),
             'tagged_pages': len(tags_for)}
    if lane_audit is not None:
        trace['evidence_lane'] = lane_audit
    if semantic_audit is not None:
        trace['semantic_fill'] = semantic_audit
    if area_audit is not None:
        trace['same_area'] = area_audit
    return context, trace


def _semantic_band(indicator, readable, pages_map, code, topical, semantic, take, limit, window_chars):
    """The semantic step of the fill: tags for other indicators, nearest in meaning to one of this indicator's
    requirements first, the requirements taking turns; each sent as the window around its quotation, up to `limit`
    characters. Returns an audit (candidates, chosen, characters)."""
    from . import semantic as tag_semantic
    queries = tag_semantic.queries_for(indicator)
    requirements = list(queries)
    candidates = []
    for source in readable:
        if source['id'] in topical:
            continue
        entry = pages_map.get(spec.text_hash(source['text'])) or {}
        for tag in entry.get('tags') or []:
            if tag.get('indicator') == code or tag.get('strength') not in tag_semantic.STRENGTHS:
                continue
            text = tag_semantic.tag_text(tag)
            if text:
                candidates.append((source, tag, text))
    if not candidates or not requirements:
        return {'candidates': len(candidates), 'chosen': 0, 'chars': 0}
    scores = semantic.similarities([queries[r] for r in requirements], [c[2] for c in candidates])
    # Per requirement: candidates by similarity, then page text hash and quote, so ties never depend on order.
    queues = {r: sorted(range(len(candidates)), key=lambda k: (-round(scores[i][k], 6),
                                                              spec.text_hash(candidates[k][0]['text']),
                                                              candidates[k][1].get('quote') or ''))
              for i, r in enumerate(requirements)}
    used, chosen, seen = 0, [], set()
    while used < limit and any(queues.values()):
        progressed = False
        for i, requirement in enumerate(requirements):
            queue = queues[requirement]
            while queue:
                k = queue.pop(0)
                if k in seen:
                    continue
                seen.add(k)
                source, tag, _ = candidates[k]
                query = _tokens(indicator['conditions'][i]['text'])
                start, end = window(source['text'], tag.get('quote'), query, size=window_chars)
                if used + (end - start) > limit:
                    continue
                added = take('semantic_fill', source, start, end)
                if added:
                    used += added
                    chosen.append({'id': source['id'], 'requirement': requirement, 'tag_indicator': tag.get('indicator'),
                                   'similarity': round(scores[i][k], 4)})
                    progressed = True
                    break
            if used >= limit:
                break
        if not progressed:
            break
    return {'candidates': len(candidates), 'chosen': len(chosen), 'chars': used, 'windows': chosen}
