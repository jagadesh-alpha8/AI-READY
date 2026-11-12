"""Offline matched-pool reranking experiment. Never selected by production policy.

Labels are measured only after selection. Callers supply a local scoring function;
this module imports no provider client and downloads no model.
"""
import math
from time import perf_counter
from .evidence_retrieval import merged_spans


def candidate_pools(trace, depth=60):
    if type(depth) is not int or not 1 <= depth <= 100:
        raise ValueError('Candidate depth must be from 1 to 100.')
    excluded = trace.get('expansion_exclusions', {})
    pools = {}
    for name, routes in (('lexical', ('lexical',)), ('combined', ('lexical', 'semantic'))):
        indices = set()
        for requirement in trace['requirements']:
            for route in routes:
                scores = requirement['lexical_scores' if route == 'lexical' else 'similarity']
                indices.update(n for n in requirement[route][:depth] if scores[n] > 0 and n not in excluded)
        pools[name] = sorted(indices, key=lambda n: trace['passages'][n].key)
    return pools


def pack_rankings(passages, rankings, budget):
    """Round-robin requirements, exact source spans, shared budget and no clipping."""
    if type(budget) is not int or budget < 100:
        raise ValueError('Packet budget must be an integer of at least 100 characters.')
    spans, used, attempts = {}, 0, []
    queues = [(cid, iter(order)) for cid, order in rankings.items()]
    while queues:
        pending = []
        for cid, order in queues:
            for index in order:
                p = passages[index]
                sid = p.source['id']
                before = spans.get(sid, [])
                after = merged_spans(before + p.spans)
                added = sum(b-a for a,b in after) - sum(b-a for a,b in before)
                outcome = 'already_covered' if not added else 'budget_excluded' if used + added > budget else 'selected'
                attempts.append({'condition_id': cid, 'passage': index, 'outcome': outcome,
                                 'additional_chars': added, 'used_chars': used})
                if outcome == 'selected':
                    spans[sid], used = after, used + added
                    pending.append((cid, order))
                    break
        queues = pending
    lookup = {p.source['id']: p.source for p in passages}
    packet = [{**{k:v for k,v in lookup[sid].items() if k != 'retrieval_hints'},
               'text': lookup[sid]['text'][a:b], 'text_offset': a}
              for sid, intervals in spans.items() for a,b in intervals]
    return {'sources': packet, 'used_chars': used, 'attempts': attempts}


def compare_pools(trace, score, *, budget=18000, depth=60, max_pairs=5000):
    """Same query/scorer and packing for lexical vs combined indicator pools.

    Score the union once per requirement and reuse scores for both arms. Strict
    output length and finiteness checks prevent partial/truncated score ledgers.
    """
    pools = candidate_pools(trace, depth)
    passages = trace['passages']
    union = pools['combined']
    pair_count = len(union) * len(trace['requirements'])
    if pair_count > max_pairs:
        raise ValueError('Offline reranker pair allowance exceeded.')
    scored, latencies = {}, {}
    for r in trace['requirements']:
        query = (r['anchor'] + ' ' + r['assertion']).strip()
        tick = perf_counter()
        values = list(score(query, [passages[n].embedding_text for n in union])) if union else []
        latencies[r['condition_id']] = perf_counter() - tick
        if len(values) != len(union) or any(not math.isfinite(v) for v in values):
            raise ValueError('Reranker must return one finite score for every candidate.')
        scored[r['condition_id']] = dict(zip(union, values))
    arms = {}
    for name, pool in pools.items():
        rankings = {cid: sorted(pool, key=lambda n: (-scores[n], passages[n].key))
                    for cid, scores in scored.items()}
        arms[name] = {**pack_rankings(passages, rankings, budget), 'rankings': rankings,
                      'candidate_count': len(pool), 'equivalent_scored_pairs': len(pool)*len(scored)}
    return {'budget': budget, 'depth': depth, 'actual_scored_pairs': pair_count,
            'queries': {r['condition_id']: (r['anchor'] + ' ' + r['assertion']).strip() for r in trace['requirements']},
            'scoring_seconds_by_requirement': latencies, 'arms': arms,
            'semantic_only_candidates': sorted(set(pools['combined']) - set(pools['lexical'])),
            'candidate_provenance': [{'passage': n, 'source_id': passages[n].source['id'],
                'start': passages[n].start, 'end': passages[n].end,
                'context_spans': passages[n].context_spans,
                'routes': [name for name, pool in pools.items() if n in pool]} for n in union],
            'note': 'Offline experiment; no baseline protection, gold-dependent selection or production mode change. '
                    'Scoring latency is shared; equivalent pair counts are not separately timed inference runs.'}
