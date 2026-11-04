"""Requirement-level lexical/semantic candidates and exact-span context allocation."""
import hashlib
import math
import re
from collections import Counter
from time import perf_counter

from .evidence_queries import requirement_queries

STOP = set('the and for with that this from each institution institutional evidence documented '
           'identified stated explicit record records relevant defined actual demonstrates demonstrate '
           'requirement has have are its an of to in or a'.split())


def terms(text):
    return Counter(t for t in re.findall(r'[a-z0-9]{2,}', text.lower()) if t not in STOP)


def diverse(order, passages):
    """Consolidate same-page duplicates/overlap; retain independent cross-page provenance."""
    selected, rejected, fingerprints = [], {}, set()
    spans = {}
    for index in order:
        p = passages[index]
        fingerprint = (p.source['id'], p.embedding_text)
        page_spans = spans.setdefault(p.source['id'], [])
        if fingerprint in fingerprints:
            rejected[index] = 'duplicate_representation'
        elif any(start <= p.start and p.end <= end for start, end in page_spans):
            rejected[index] = 'contained_candidate'
        else:
            selected.append(index)
            fingerprints.add(fingerprint)
            page_spans.append((p.start, p.end))
    return selected, rejected


def merged_spans(spans):
    result = []
    for start, end in sorted(spans):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def expansion_exclusion(passage):
    """Reject instruction-only bodies from discovery, never from the protected baseline.

    Mixed passages and numerical tables remain candidates. This is a document
    structure check, not a judgement that a requirement is met.
    """
    from .passages import section_heading
    body = passage.text
    meaningful = []
    for line in body.splitlines():
        text = line.strip()
        # Rendered column cells can contain a complete narrative paragraph.
        # Remove only the generated wrapper; classify its payload normally.
        caption = re.match(r'^\[Table\s+\d+(?:\s+on\s+page\s+\d+)?\s+--\s+columns:\s*', text)
        if caption:
            text = text[caption.end():]
            if text.endswith(']'):
                text = text[:-1]
            text = text.strip(' |')
        if not text or re.fullmatch(r'[\d.\s]+', text):
            continue
        if re.search(r'File Description\s*:', text, re.I) and re.search(r'Document\s*:\s*(?:View Document|https?://)', text, re.I):
            continue
        if text.lower() in {'response:', 'response', 'view document', 'file description | document', '(none)'}:
            continue
        if section_heading(text) and (text.endswith(':') or text.startswith('#') or re.match(r'^\d+(?:\.\d+)+\s', text)):
            continue
        meaningful.append(text)
    return None if meaningful else 'instruction_or_heading_only'


def retrieve_evidence(indicator, sources, ranker, max_chars=18000, diagnostics=None, include_semantic=True, protect_baseline=None):
    started = perf_counter()
    if len({s['id'] for s in sources}) != len(sources):
        raise ValueError('Source IDs must be unique.')
    passages = ranker.passages(sources)
    if max_chars < 100 or not passages:
        if diagnostics is not None:
            diagnostics.update(passages=passages, requirements=[], selected=[], packing_attempts=[], elapsed_seconds=0)
        return []
    protect_baseline = include_semantic if protect_baseline is None else protect_baseline
    exclusions = {n: reason for n, p in enumerate(passages) if (reason := expansion_exclusion(p))}
    from .evaluation import RETRIEVAL_TERMS
    words = [terms(p.embedding_text) for p in passages]
    lengths = [sum(w.values()) for w in words]
    average = sum(lengths) / len(lengths) or 1
    frequency = Counter(t for w in words for t in w)
    topic = terms(RETRIEVAL_TERMS.get(indicator['code'], ''))
    ties = [(hashlib.sha256(p.embedding_text.encode()).hexdigest(), p.source['id'], p.start) for p in passages]

    def bm25(query):
        scores = []
        for w, length in zip(words, lengths):
            scores.append(sum(math.log(1 + (len(words) - frequency[t] + .5) / (frequency[t] + .5)) *
                              query[t] * w[t] * 2.2 / (w[t] + 1.2 * (.25 + .75 * length / average))
                              for t in query.keys() & w.keys()))
        return scores

    topic_scores = bm25(topic)
    requirements = requirement_queries(indicator, ranker)
    for requirement in requirements:
        assertion = Counter({t: 1 for t in terms(requirement['assertion'])})
        contextual = assertion + assertion + Counter({t: 1 for t in terms(requirement['anchor'])})
        raw = bm25(assertion)
        contextual_scores = bm25(contextual)
        profile_scores = bm25(Counter({t: 1 for t in terms(requirement['evidence_query'])}))
        with_profiles = [score + .5 * profile for score, profile in zip(contextual_scores, profile_scores)]
        with_terms = [score + .15 * hint for score, hint in zip(with_profiles, topic_scores)]
        hints = [any(h['indicator_code'] == indicator['code'] and p.start <= h['start']
                     and h['end'] <= p.end for h in p.source.get('retrieval_hints', [])) for p in passages]
        boosted = [score * 1.25 + 1 if hint else score for score, hint in zip(with_terms, hints)]
        semantic_variants = ranker.similarities(passages, requirement['queries']) if include_semantic else []
        similarity = [max((float(values[n]) for values in semantic_variants), default=0.) for n in range(len(passages))]
        def ordered(values):
            return sorted(range(len(passages)), key=lambda n: (-values[n], ties[n]))
        eligible = lambda order: [n for n in order if not protect_baseline or n not in exclusions]
        lexical, suppressed_lexical = diverse(eligible([n for n in ordered(boosted) if boosted[n] > 0]), passages)
        semantic, suppressed_semantic = diverse(eligible([n for n in ordered(similarity) if similarity[n] > 0]), passages) if include_semantic else ([], {})
        fused_scores = Counter()
        for weight, order in ((2, lexical[:60]), (1, semantic[:60])):
            for position, index in enumerate(order, 1):
                fused_scores[index] += weight / (60 + position)
        fused, suppressed_fused = diverse([n for n in ordered(fused_scores) if fused_scores[n] > 0], passages)
        requirement.update(raw_scores=raw, contextual_scores=contextual_scores,
            profile_scores=with_profiles, terms_scores=with_terms,
            lexical_scores=boosted, hint_applied=hints, similarity=similarity,
            variant_similarities=[[float(v) for v in values] for values in semantic_variants],
            raw_lexical=ordered(raw), contextual_lexical=ordered(contextual_scores), profile_lexical=ordered(with_profiles), lexical=lexical, semantic=semantic, fused=fused,
            raw_semantic=ordered(similarity), terms_lexical=ordered(with_terms),
            suppressed={'lexical': suppressed_lexical, 'semantic': suppressed_semantic, 'fused': suppressed_fused})

    # A candidate's heading is an exact additional source span and pays for its budget.
    source_spans, used, attempts = {}, 0, []
    baseline, baseline_used = [], 0
    if protect_baseline:
        from .evaluation import select_context
        baseline = select_context(indicator, sources,
            max_chars=min(max_chars, getattr(ranker, 'baseline_chars', 18000)))
        for source in baseline:
            sid, start = source['id'], source['text_offset']
            source_spans[sid] = merged_spans(source_spans.get(sid, []) + [(start, start + len(source['text']))])
        used = baseline_used = sum(b - a for spans in source_spans.values() for a, b in spans)
    def add(index, requirement, phase, limit):
        nonlocal used
        passage = passages[index]
        sid = passage.source['id']
        before = source_spans.get(sid, [])
        after = merged_spans(before + passage.spans)
        added = sum(b - a for a, b in after) - sum(b - a for a, b in before)
        if protect_baseline and index in exclusions:
            outcome = exclusions[index]
        elif not added:
            outcome = 'already_covered'
        elif used + added > max_chars:
            outcome = 'budget_excluded'
        elif used + added > limit:
            outcome = 'allocation_excluded'
        else:
            outcome = 'selected'
        if diagnostics is not None:
            attempts.append({'passage': index, 'condition_id': requirement['condition_id'], 'phase': phase,
                             'outcome': outcome, 'additional_chars': added, 'used_chars': used, 'limit_chars': limit})
        if outcome == 'selected':
            source_spans[sid], used = after, used + added
            return True
        return False

    def rounds(route, limit, one_round=False):
        queues = [(r, iter(r[route][:60])) for r in requirements]
        while queues:
            pending = []
            for requirement, order in queues:
                for index in order:
                    if route == 'lexical' and requirement['lexical_scores'][index] <= 0:
                        break
                    if route == 'semantic' and requirement['similarity'][index] <= 0:
                        break
                    if add(index, requirement, route, limit):
                        pending.append((requirement, order))
                        break
            if one_round:
                break
            queues = pending
    # Whole passages only: no prefix truncation to force a window into remaining budget.
    if protect_baseline:
        # No semantic quota and no eviction. Discovery competes only for the
        # explicitly separate remainder, with both routes contributing ranks.
        discovery_limit = baseline_used + max(0, max_chars - min(max_chars, getattr(ranker, 'baseline_chars', 18000)))
        if include_semantic:
            rounds('semantic', discovery_limit, one_round=True)
        rounds('fused', discovery_limit)
    else:
        rounds('lexical', max_chars)
    source_lookup = {s['id']: s for s in sources}
    selected = []
    for sid, spans in source_spans.items():
        source = source_lookup[sid]
        for start, end in spans:
            selected.append({**{k: v for k, v in source.items() if k != 'retrieval_hints'},
                             'text': source['text'][start:end], 'text_offset': start})
    if diagnostics is not None:
        diagnostics.update(passages=passages, requirements=requirements, selected=selected,
                           baseline_selected=baseline, baseline_chars=baseline_used,
                           expansion_chars=used - baseline_used if protect_baseline else 0,
                           expansion_exclusions=exclusions,
                           packing_attempts=attempts, used_chars=used,
                           elapsed_seconds=round(perf_counter() - started, 4), cache=dict(ranker.stats))
    return selected
