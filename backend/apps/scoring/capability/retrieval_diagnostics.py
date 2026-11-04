"""Private, offline gold-item traces. Never infer document absence from a retrieval miss."""
from .evaluation import select_context, _normal


def gold_traces(rubric, sources, gold, ranker, budget=18000):
    indicators = {c['id']: i for i in rubric['indicators'] for c in i['conditions']}
    cache, result = {}, []
    def key(row):
        return row[0]['id'], row[1]
    for item in gold:
        indicator = indicators[item['condition_id']]
        code = indicator['code']
        if code not in cache:
            trace = {}
            select_context(indicator, sources, max_chars=budget, semantic_ranker=ranker, diagnostics=trace)
            # Build ranks once per query, rather than searching every ranked list for every label.
            for ranking in trace['rankings']:
                ranking['positions'] = {route: {key(row): n for n, row in enumerate(ranking[route], 1)}
                                        for route in ('lexical', 'semantic', 'fused')}
            cache[code] = trace
        trace = cache[code]
        quote = _normal(item['quote'])
        def on_page(source):
            return source['document_id'] == item['document_id'] and source['page_number'] == int(item['page'])
        candidates = [r for r in trace['candidates'] if on_page(r[0]) and quote in _normal(r[2])]
        retrieved = any(on_page(s) and quote in _normal(s['text']) for s in trace['selected'])
        attempts = [a for a in trace['packing_attempts'] if (a['source_id'], a['offset']) in {key(r) for r in candidates}]
        cause = ('retrieved' if retrieved else 'quote_not_in_candidate_window' if not candidates else
                 'packing_budget_or_partial' if any(a['outcome'] in ('budget_exhausted', 'merge_exceeds_budget', 'selected_partial')
                                                    for a in attempts) else 'ranked_but_not_selected')
        # Gold labels never influence queries, ranking, fusion or passage selection.
        requirement = next(c for c in indicator['conditions'] if c['id'] == item['condition_id'])
        ranks = [r for r in trace['rankings'] if r['query'] == requirement['text']]
        probes = []
        for ranking in ranks:
            nearest = []
            for row in ranking['semantic'][:5]:
                nearest.append({'source_id': row[0]['id'], 'page': row[0]['page_number'], 'offset': row[1],
                                'text': row[2], 'similarity': ranking['similarity'].get(key(row))})
            probes.append({'query': ranking['query'],
                **{route + '_rank': min((ranking['positions'][route][key(r)] for r in candidates), default=None)
                   for route in ('lexical', 'semantic', 'fused')}, 'nearest_semantic': nearest})
        matched_inputs = []
        for row in candidates:
            probe = ranker.input_diagnostics(row[2])
            matched_inputs.append({'source_id': row[0]['id'], 'offset': row[1], 'text': row[2],
                'embedding_input': probe, 'quote_in_tokenized_prefix': (
                    quote in _normal(row[2][:probe['retained_chars']]) if 'retained_chars' in probe else None)})
        result.append({'condition_id': item['condition_id'], 'document_id': item['document_id'],
            'page': int(item['page']), 'evidence_type': item.get('evidence_type', 'unlabelled'),
            'retrieved': retrieved, 'loss_stage': cause, 'queries': probes, 'packing_attempts': attempts,
            'matching_candidates': matched_inputs})
    return result
