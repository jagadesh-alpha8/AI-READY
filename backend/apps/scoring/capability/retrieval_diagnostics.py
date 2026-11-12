"""Private, offline observed loss stages; semantic relevance still needs human judgement."""
from collections import Counter
from .evaluation import select_context, _normal


def candidate_audit(requirements, target, matching):
    """Label-only diagnostics. These pools never select production evidence."""
    matching = set(matching)
    def pool(rows, k, eligible):
        result = set()
        for r in rows:
            routes = ('lexical', 'semantic') if eligible else ('raw_lexical', 'profile_lexical', 'raw_semantic')
            for route in routes:
                scores = r[{'raw_lexical': 'raw_scores', 'profile_lexical': 'profile_scores',
                            'raw_semantic': 'similarity', 'lexical': 'lexical_scores', 'semantic': 'similarity'}[route]]
                result.update(n for n in r[route][:k] if scores[n] > 0)
        return result
    result = {}
    for k in (5, 10, 20, 60, 100):
        pools = {'target_requirement_raw_union': pool([target] if target else [], k, False),
                 'indicator_raw_union': pool(requirements, k, False),
                 'target_requirement_eligible_union': pool([target] if target else [], k, True),
                 'indicator_eligible_union': pool(requirements, k, True)}
        result[str(k)] = {name: bool(indices & matching) for name, indices in pools.items()}
        result[str(k)].update({name + '_size': len(indices) for name, indices in pools.items()})
    return result


def labelled_packet_oracle(rows, budget):
    """Construct a label-aware packet; not a retriever, score, or global optimum.

    Choose each label's shortest candidate and count unique source/heading spans.
    Fitting these targets shows physical feasibility only, not that other rubric
    requirements fit or that any passage is sufficient evidence for a decision.
    """
    from .evidence_retrieval import merged_spans
    groups = {}
    for row in rows:
        group = groups.setdefault(row['indicator'], {'spans': {}, 'labels': 0, 'missing_candidates': 0})
        group['labels'] += 1
        candidates = row['matching_candidates']
        if not candidates:
            group['missing_candidates'] += 1
            continue
        def spans(c):
            return merged_spans([(c['offset'], c['end'])] + [tuple(s) for s in c['context_spans']])
        best = min(candidates, key=lambda c: (sum(b - a for a, b in spans(c)), c['source_id'], c['offset']))
        sid = best['source_id']
        group['spans'][sid] = merged_spans(group['spans'].get(sid, []) + spans(best))
    return {code: {'labels': group['labels'], 'missing_candidates': group['missing_candidates'],
                   'label_aware_packet_chars': sum(b - a for spans in group['spans'].values() for a, b in spans),
                   'all_labelled_candidates_fit': not group['missing_candidates'] and
                       sum(b - a for spans in group['spans'].values() for a, b in spans) <= budget}
            for code, group in groups.items()}


def gold_traces(rubric, sources, gold, ranker, budget=18000):
    indicators = {c['id']: i for i in rubric['indicators'] for c in i['conditions']}
    cache, result = {}, []
    for item in gold:
        indicator = indicators[item['condition_id']]
        if indicator['code'] not in cache:
            trace = {}
            select_context(indicator, sources, max_chars=budget, semantic_ranker=ranker, diagnostics=trace)
            cache[indicator['code']] = trace
        trace = cache[indicator['code']]
        passages = trace['passages']
        quote = _normal(item['quote'])
        def on_page(source):
            return source['document_id'] == item['document_id'] and source['page_number'] == int(item['page'])
        page_sources = [s for s in sources if on_page(s)]
        source_present = any(quote in _normal(s['text']) for s in page_sources)
        matching = [n for n, p in enumerate(passages) if on_page(p.source) and quote in _normal(p.text)]
        retrieved = any(on_page(s) and quote in _normal(s['text']) for s in trace['selected'])
        baseline_retrieved = any(on_page(s) and quote in _normal(s['text']) for s in trace.get('baseline_selected', []))
        requirement = next((r for r in trace['requirements'] if r['condition_id'] == item['condition_id']), None)
        attempts = [a for a in trace['packing_attempts'] if a['passage'] in matching]
        if retrieved:
            cause = 'retrieved'
        elif not page_sources:
            cause = 'source_page_missing'
        elif not source_present:
            cause = 'quote_not_in_searchable_page'
        elif not matching:
            cause = 'quote_not_in_candidate_body'
        elif all(n in trace.get('expansion_exclusions', {}) for n in matching):
            cause = 'discovery_candidate_filtered'
        elif any(a['outcome'] == 'budget_excluded' for a in attempts):
            cause = 'context_budget_excluded'
        elif requirement and all(n in requirement['suppressed']['fused'] for n in matching):
            cause = 'candidate_consolidated'
        elif requirement and any(n in requirement[route][:60] for n in matching
                                 for route in ('lexical', 'semantic', 'fused')):
            cause = 'requirement_allocation'
        else:
            cause = 'ranking_shortlist'
        probes = []
        def best_rank(route):
            positions = {index: n for n, index in enumerate(requirement[route], 1)}
            return min((positions[n] for n in matching if n in positions), default=None)
        def passage_data(index):
            p = passages[index]
            probe = ranker.input_diagnostics(p.embedding_text)
            contexts = [p.source['text'][a:b] for a, b in p.context_spans]
            expected = item.get('context_quotes') or []
            expected = [x for x in expected if isinstance(x, str)] if isinstance(expected, list) else []
            return {'passage': index, 'source_id': p.source['id'], 'page': p.source['page_number'],
                'offset': p.start, 'end': p.end, 'kind': p.kind, 'body': p.text,
                'expansion_exclusion': trace.get('expansion_exclusions', {}).get(index),
                'embedding_input': p.embedding_text, 'embedding_tokens': p.tokens,
                'tokenizer': probe, 'split_unit': p.split_unit, 'heading_clipped': p.heading_clipped,
                'context_spans': [list(span) for span in p.context_spans], 'context_text': contexts,
                'context_check': ('verified_labelled_context_present' if all(_normal(x) in _normal(p.embedding_text)
                    for x in expected) else 'labelled_context_missing') if expected else 'manual_review_required',
                'embedding_skipped': index in trace.get('expansion_exclusions', {}),
                'quote_in_tokenized_input': False if index in trace.get('expansion_exclusions', {}) else (quote in _normal(p.embedding_text[:probe['retained_chars']])
                                             if 'retained_chars' in probe else None)}
        if requirement:
            nearest = [{**passage_data(n), 'similarity': requirement['similarity'][n]}
                       for n in requirement['raw_semantic'][:5]]
            probes.append({'queries': requirement['queries'],
                'query_roles': requirement['query_roles'], 'evidence_query': requirement['evidence_query'],
                'encoder_queries': [ranker.query_input(q) for q in requirement['queries']],
                'encoder_query_tokens': [len(ranker.token_offsets(ranker.query_input(q))) for q in requirement['queries']],
                'anchor': requirement['anchor'], 'query_clipped': requirement['query_clipped'],
                'semantic_by_query': [{'query': query, 'encoder_input': ranker.query_input(query),
                    'role': role, 'nearest': [{**passage_data(n), 'similarity': values[n]} for n in sorted(
                        range(len(passages)), key=lambda n: (-values[n], passages[n].key))[:5]]}
                    for query, role, values in zip(requirement['queries'], requirement['query_roles'], requirement['variant_similarities'])],
                'lexical_rank': best_rank('raw_lexical'), 'boosted_lexical_rank': best_rank('lexical'),
                'contextual_lexical_rank': best_rank('contextual_lexical'),
                'profile_lexical_rank': best_rank('profile_lexical'),
                'terms_lexical_rank': best_rank('terms_lexical'), 'semantic_rank': best_rank('raw_semantic'),
                'diversified_semantic_rank': best_rank('semantic'), 'fused_rank': best_rank('fused'),
                'matching_scores': [{'passage': n, 'raw_bm25': requirement['raw_scores'][n],
                    'contextual_bm25': requirement['contextual_scores'][n],
                    'with_evidence_profile': requirement['profile_scores'][n],
                    'with_indicator_terms': requirement['terms_scores'][n],
                    'with_extraction_hint': requirement['lexical_scores'][n],
                    'hint_applied': requirement['hint_applied'][n], 'cosine': requirement['similarity'][n],
                    'query_cosines': [values[n] for values in requirement['variant_similarities']],
                    'consolidation': {route: reason[n] for route, reason in requirement['suppressed'].items() if n in reason}}
                    for n in matching], 'nearest_semantic': nearest})
        result.append({'condition_id': item['condition_id'], 'indicator': indicator['code'], 'document_id': item['document_id'],
            'page': int(item['page']), 'evidence_type': item.get('evidence_type', 'unlabelled'),
            'label_quote': item['quote'], 'source_quote_present': source_present, 'candidate_quote_present': bool(matching),
            'labelled_context_retrieved': (retrieved and all(any(
                _normal(context) in _normal(s['text']) for s in trace['selected'] if on_page(s))
                for context in item['context_quotes'] if isinstance(context, str)))
                if isinstance(item.get('context_quotes'), list) and item['context_quotes'] else None,
            'retrieved': retrieved, 'loss_stage': cause, 'queries': probes, 'packing_attempts': attempts,
            'loss_stage_is_observation_not_root_cause': True,
            'candidate_pool_recall': candidate_audit(trace['requirements'], requirement, matching),
            'baseline_retrieved': baseline_retrieved, 'discovery_gain': retrieved and not baseline_retrieved,
            'baseline_chars': trace.get('baseline_chars', 0), 'expansion_chars': trace.get('expansion_chars', 0),
            'matching_candidates': [passage_data(n) for n in matching],
            'retrieval_seconds': trace['elapsed_seconds'], 'cache': trace.get('cache', {})})
    return result


def trace_summary(rows):
    indicators = {row.get('indicator', str(n)): row for n, row in enumerate(rows)}
    return {'items': len(rows), 'source_quotes_present': sum(r['source_quote_present'] for r in rows),
            'candidate_quotes_present': sum(r['candidate_quote_present'] for r in rows),
            'retrieved': sum(r['retrieved'] for r in rows),
            'observed_stages': dict(Counter(r['loss_stage'] for r in rows)),
            'candidate_pool_recall': {str(k): {key: sum(row.get('candidate_pool_recall', {}).get(str(k), {}).get(key, False)
                 for row in rows) for key in ('target_requirement_raw_union', 'indicator_raw_union',
                     'target_requirement_eligible_union', 'indicator_eligible_union')} for k in (5, 10, 20, 60, 100)},
            'indicator_eligible_pool_sizes': {str(k): sorted(row.get('candidate_pool_recall', {}).get(str(k), {}).get(
                'indicator_eligible_union_size', 0) for row in indicators.values()) for k in (5, 10, 20, 60, 100)},
            'note': 'Loss stages describe observations, not root causes. A candidate rejected after context fills may be ranked poorly. '
                    'Relevant quotations are retrieval targets, not automatically sufficient evidence for a met decision.'}


def readable_report(result):
    lines = ['# Private retrieval diagnosis', '',
             'Existing labels are a debugging/regression set. No evaluator calls were made.',
             'Candidate recall, packet inclusion and assessment sufficiency are separate. Budget rejection does not establish that more context is the right fix.', '']
    if result.get('comparison_policy'):
        lines += ['Comparison budgets: ' + str(result['comparison_policy']), '',
                  'Expanded hybrid preserves the base BM25 selection. Compare it with expanded BM25 to separate ranking from added context.', '']
    for split, methods in result.get('sets', {}).items():
        lines += [f'## Retrieval counts: {split}', '', '| Method | Quotations retrieved | Requirements with a target | Lost vs base BM25 |', '|---|---:|---:|---:|']
        for name, measured in methods.items():
            coverage = measured.get('labelled_requirement_coverage', {})
            requirements = f"{coverage.get('requirements_with_any_target_retrieved', 0)}/{coverage.get('labelled_requirements', 0)}"
            lines.append(f"| {name} | {sum(row['retrieved'] for row in measured['items'])}/{len(measured['items'])} | {requirements} | {len(measured.get('versus_bm25_1800', {}).get('lost', []))} |")
        lines += ['']
    if result.get('aggregate_requirement_coverage'):
        lines += ['Distinct labelled requirement coverage across all sets (not assessment truth):',
                  str(result['aggregate_requirement_coverage']), '']
    if result.get('evidence_case_coverage'):
        lines += ['## Known support-bundle coverage', '',
                  'Review status: ' + result.get('evidence_case_review_status', 'unspecified'),
                  'Positive bundles are alternatives; missing a known bundle does not exclude unlabelled adequate evidence. Scope/period and evaluator decisions are not tested.', '',
                  '| Method | Positive cases with a known bundle | Cases with no verified positive |', '|---|---:|---:|']
        for name, measured in result['evidence_case_coverage'].items():
            lines.append(f"| {name} | {measured['positive_cases_with_known_support']}/{measured['positive_cases']} | {measured['cases_without_verified_positive']} |")
        lines += ['']
    for split, rows in result['gold_traces'].items():
        lines += [f'## {split}', '', str(result['trace_summary'][split]), '']
        if result.get('labelled_packet_oracle', {}).get(split):
            lines += ['Label-aware packet feasibility (diagnostic only; not production retrieval):',
                      str(result['labelled_packet_oracle'][split]), '']
        for row in rows:
            lines += [f"### {row['condition_id']} — page {row['page']}", '',
                      f"Observed stage: {row['loss_stage']}. Source quotation present: {row['source_quote_present']}. "
                      f"Candidate body contains it: {row['candidate_quote_present']}. Selected: {row['retrieved']}.", '',
                      'Labelled quotation:', '', '    ' + row['label_quote'].replace('\n', '\n    '), '']
            for query in row['queries']:
                lines += [f"BM25 rank: {query['lexical_rank']}; boosted rank: {query['boosted_lexical_rank']}; "
                          f"semantic rank: {query['semantic_rank']}; fused rank: {query['fused_rank']}.", '', 'Query roles: ' + ', '.join(query['query_roles']), '', 'Actual encoder queries:', '']
                lines += ['    ' + text.replace('\n', '\n    ') for text in query['encoder_queries']]
                lines += ['', 'Top semantic passages (manual relevance/entailment review):', '']
                for nearest in query['nearest_semantic']:
                    lines += [f"Page {nearest['page']}, offset {nearest['offset']}, cosine {nearest['similarity']:.4f}:", '',
                              '    ' + nearest['embedding_input'].replace('\n', '\n    '), '']
            for candidate in row['matching_candidates']:
                lines += [f"Matching candidate {candidate['passage']}: {candidate['embedding_tokens']} tokens; "
                          f"context: {candidate['context_check']}; split unit: {candidate['split_unit']}.", '',
                          '    ' + candidate['embedding_input'].replace('\n', '\n    '), '']
            lines += ['Packing attempts: ' + str(row['packing_attempts']), '']
    return '\n'.join(lines)
