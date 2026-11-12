"""Targeted extra search after part judgment (off by default; CAPABILITY_FOLLOW_UP_SEARCH turns it on and the
choice is frozen in the run's retrieval policy).

After an indicator is judged, each part that every pass marked not_found gets one more search that uses the
part's own description as the query (keyword and embedding ranks fused), over the same pages retrieval used.
Text already in the packet is never sent again. If the search adds passages, only the conditions with such
parts are judged again, on the original packet plus the new passages, with the same number of passes.

The second judgment can add credit, never remove it: a condition takes the second result only when its credit
is higher than the first. Otherwise the first result stands and the second is kept in the trace for review.
That keeps the extra search from turning ordinary run-to-run variation into lost credit, at the price of
ignoring a contradiction that only the new passages show (the trace records it).

Bounded: at most MAX_PARTS parts searched, PICKS_PER_PART passages each and FOLLOW_UP_CHARS new characters per
indicator, and one extra judgment (per pass) per indicator.
"""
import hashlib
import math
from collections import Counter

VERSION = 'not-found-part-search-v1'
FOLLOW_UP_CHARS = 8000
PICKS_PER_PART = 2
MAX_PARTS = 8
MIN_PIECE = 200        # characters; a smaller uncovered remainder of a passage is not worth sending
CANDIDATES = 60        # ranks per route that enter fusion, as in evidence_retrieval
SEARCHABLE = ('unknown',)


def targets(records, spec):
    """[(condition id, part)] for parts every pass marked not_found, in conditions whose state is unknown.

    Conditions that already have some evidence come first (one more part may complete them), then rubric order.
    Conditions that were not evaluated (a request or validation failure) are skipped."""
    from .decision_causes import NOT_EVALUATED
    chosen = []
    for order, record in enumerate(records):
        if record.get('state') not in SEARCHABLE or record.get('cause') == NOT_EVALUATED or not record.get('parts'):
            continue
        parts = {p['id']: p for p in spec[record['condition_id']]['parts']}
        missing = [p for p in record['parts']
                   if p['finding'] == 'not_found' and p.get('second_finding', 'not_found') == 'not_found']
        evidenced = sum(1 for p in record['parts'] if p['finding'] != 'not_found' or
                        p.get('second_finding', 'not_found') != 'not_found')
        for part in missing:
            chosen.append((-evidenced, order, record['condition_id'], parts[part['id']]))
    chosen.sort(key=lambda row: (row[0], row[1]))
    return [(cid, part) for _, _, cid, part in chosen[:MAX_PARTS]]


def _covered(context):
    spans = {}
    for window in context:
        if window.get('evidence_role') == 'report_timestamp':
            continue
        start = window.get('text_offset', 0)
        spans.setdefault(window['id'], []).append((start, start + len(window['text'])))
    return spans


def _uncovered(start, end, covered):
    """Pieces of [start, end) not inside any covered span."""
    pieces, cursor = [], start
    for a, b in sorted(covered):
        if b <= cursor or a >= end:
            continue
        if a > cursor:
            pieces.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < end:
        pieces.append((cursor, end))
    return pieces


def _index(ranker, passages):
    """Keyword statistics for the corpus, built once per corpus and kept on the ranker."""
    from .evidence_retrieval import terms
    key = getattr(ranker, '_store_key', None) or id(passages)
    cached = getattr(ranker, '_follow_up_index', None)
    if cached is None or cached[0] != key:
        words = [terms(p.embedding_text) for p in passages]
        lengths = [sum(w.values()) for w in words]
        cached = (key, words, lengths, sum(lengths) / len(lengths) if lengths else 1,
                  Counter(t for w in words for t in w))
        ranker._follow_up_index = cached
    return cached[1:]


def search(part, sources, ranker, context, limit=FOLLOW_UP_CHARS, picks=PICKS_PER_PART, taken=None):
    """New exact windows for one part: [(source, start, end)] not already in `context` or `taken`."""
    from .evidence_retrieval import terms, expansion_exclusion
    passages = ranker.passages(sources)
    if not passages or limit < MIN_PIECE:
        return []
    words, lengths, average, frequency = _index(ranker, passages)
    query = Counter({t: 1 for t in terms(part['full'])})
    lexical = []
    for n, (w, length) in enumerate(zip(words, lengths)):
        score = sum(math.log(1 + (len(words) - frequency[t] + .5) / (frequency[t] + .5)) *
                    w[t] * 2.2 / (w[t] + 1.2 * (.25 + .75 * length / (average or 1)))
                    for t in query.keys() & w.keys())
        if score > 0:
            lexical.append((score, n))
    similarity = ranker.similarities(passages, [part['full']])[0]
    ties = lambda n: (hashlib.sha256(passages[n].embedding_text.encode()).hexdigest(), passages[n].source['id'], passages[n].start)
    eligible = [n for n in range(len(passages)) if not expansion_exclusion(passages[n])]
    lexical_order = [n for _, n in sorted(lexical, key=lambda row: (-row[0], ties(row[1])))
                     if not expansion_exclusion(passages[n])][:CANDIDATES]
    semantic_order = sorted([n for n in eligible if float(similarity[n]) > 0],
                            key=lambda n: (-float(similarity[n]), ties(n)))[:CANDIDATES]
    fused = Counter()
    for order in (lexical_order, semantic_order):
        for position, n in enumerate(order, 1):
            fused[n] += 1 / (60 + position)
    covered = _covered(context)
    for source_id, start, end in taken or []:
        covered.setdefault(source_id, []).append((start, end))
    chosen, used = [], 0
    for n in sorted(fused, key=lambda n: (-fused[n], ties(n))):
        if len(chosen) >= picks:
            break
        passage = passages[n]
        sid = passage.source['id']
        pieces = [(a, b) for a, b in _uncovered(passage.start, passage.end, covered.get(sid, [])) if b - a >= MIN_PIECE]
        if not pieces:
            continue
        a, b = max(pieces, key=lambda span: span[1] - span[0])
        if used + (b - a) > limit:
            continue
        chosen.append((passage.source, a, b))
        covered.setdefault(sid, []).append((a, b))
        used += b - a
    return chosen


def extra_windows(records, spec, sources, ranker, context):
    """(windows to add, audit) for one judged indicator."""
    wanted = targets(records, spec)
    windows, taken, audit = [], [], []
    remaining = FOLLOW_UP_CHARS
    for cid, part in wanted:
        found = search(part, sources, ranker, context, limit=remaining, taken=taken)
        for source, start, end in found:
            taken.append((source['id'], start, end))
            remaining -= end - start
            windows.append({**{k: v for k, v in source.items() if k != 'retrieval_hints'},
                            'text': source['text'][start:end], 'text_offset': start,
                            'evidence_role': 'follow_up_search'})
        audit.append({'condition_id': cid, 'part_id': part['id'],
                      'added': [{'source_id': s['id'], 'start': a, 'end': b} for s, a, b in found]})
    conditions = sorted({row['condition_id'] for row in audit if row['added']})
    return windows, {'version': VERSION, 'searched_parts': audit, 'conditions': conditions,
                     'added_chars': sum(len(w['text']) for w in windows)}


def keep_higher(first, second):
    """Per condition, the second record only where its credit is higher. Returns (records, replaced ids)."""
    better = {r['condition_id']: r for r in second}
    merged, replaced = [], []
    for record in first:
        twin = better.get(record['condition_id'])
        if twin is not None and twin.get('credit', 0.0) > record.get('credit', 0.0):
            merged.append({**twin, 'follow_up': {'version': VERSION, 'replaced': True,
                                                 'previous_state': record['state'], 'previous_credit': record['credit']}})
            replaced.append(record['condition_id'])
        elif twin is not None:
            merged.append({**record, 'follow_up': {'version': VERSION, 'replaced': False,
                                                   'second_state': twin['state'], 'second_credit': twin.get('credit', 0.0)}})
        else:
            merged.append(record)
    return merged, replaced
