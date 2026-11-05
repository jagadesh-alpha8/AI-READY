"""Offline requirement-owned evidence packets. Never an assessment or live selector.

Lexical features propose complementary spans, not entailment or sufficient support.
Labels and expected decisions are deliberately absent from this interface.
"""
from .evidence_retrieval import terms, merged_spans
from .selection_experiment import candidate_pools


def requirement_packets(trace, *, budget=18000, route='combined', expand=False, depth=60):
    requirements, passages = trace['requirements'], trace['passages']
    if route not in ('lexical', 'combined') or type(budget) is not int or budget < 100:
        raise ValueError('Invalid packet policy.')
    pool = candidate_pools(trace, depth)[route]
    if not requirements:
        return {'sources':[], 'packets':[], 'used_chars':0, 'budget':budget}
    # Reserve an equal budget for every assertion; no early assertion can consume
    # a neighbour's allowance. Repeated cross-requirement context pays separately.
    allowance, remainder = divmod(budget, len(requirements))
    packets = []
    for r_index, r in enumerate(requirements):
        limit = allowance + (r_index < remainder)
        assertion = set(terms(r['anchor']+' '+r['assertion']))
        profile = set(terms(r['evidence_query'])) - assertion
        weights = {**{t:1 for t in profile}, **{t:3 for t in assertion}}
        spans, used, covered, attempts, selected = {}, 0, set(), [], []
        features = {n:set(terms(passages[n].embedding_text)) & weights.keys() for n in pool}
        lexical = r['lexical_scores']; semantic = r['similarity']
        max_lexical = max((lexical[n] for n in pool), default=1) or 1
        def span_bundle(n):
            p=passages[n]
            intervals=p.spans
            if expand:
                # Same-page adjoining body spans only. Preserve gaps and source
                # identity; never turn indexing text into invented citation text.
                neighbours=[q for q in passages if q.source['id']==p.source['id'] and q is not p
                    and q.heading==p.heading and (q.end==p.start or q.start==p.end)]
                if neighbours:
                    nearest=min(neighbours,key=lambda q:(q.end-q.start,q.start))
                    intervals=intervals+nearest.spans
            return merged_spans(intervals)
        candidates={n:span_bundle(n) for n in pool}
        pending=set(pool)
        while pending:
            options=[]
            for n in pending:
                p=passages[n];sid=p.source['id']
                before=spans.get(sid,[]);after=merged_spans(before+candidates[n])
                cost=sum(b-a for a,b in after)-sum(b-a for a,b in before)
                novel=features[n]-covered
                # Complete current requirement query, plus bounded marginal
                # lexical coverage and route score. No corpus-specific terms.
                lexical_signal=lexical[n]/max_lexical
                route_signal=max(0,semantic[n]) if route=='combined' else 0
                gain=sum(weights[t] for t in novel)/max(1,sum(weights.values()))
                # Relevance selects the anchor; novelty is a bounded secondary
                # signal. Dividing by passage length promoted short headings
                # over substantive narrative in the first offline ablation.
                utility=lexical_signal+0.25*route_signal+(0.25*gain if selected else 0)
                if not cost or used+cost>limit:
                    attempts.append({'passage':n,'outcome':'covered' if not cost else 'budget_excluded','additional_chars':cost})
                else:
                    options.append((utility,passages[n].key,n,after,cost,novel))
            if not options:break
            _,_,n,after,cost,novel=min(options,key=lambda row:(-row[0],row[1]))
            p=passages[n];spans[p.source['id']]=after;used+=cost;covered.update(novel);selected.append(n);pending.remove(n)
            attempts.append({'passage':n,'outcome':'selected','additional_chars':cost})
            # At most four complementary candidate bundles per assertion.
            if len(selected)==4:break
        lookup={p.source['id']:p.source for p in passages}
        sources=[{**{k:v for k,v in lookup[sid].items() if k!='retrieval_hints'},
                  'text':lookup[sid]['text'][a:b],'text_offset':a}
                 for sid,intervals in spans.items() for a,b in intervals]
        packets.append({'condition_id':r['condition_id'],'sources':sources,'used_chars':used,
            'allowance':limit,'selected_candidates':selected,'covered_lexical_features':sorted(covered),
            'attempts':attempts,'note':'Lexical features are retrieval signals, not satisfied evidence roles.'})
    # Keep requirement ownership as well as a shared union for the old inclusion
    # metric. The sum of owned packet costs is the actual experimental allowance.
    all_spans={};lookup={p.source['id']:p.source for p in passages}
    for packet in packets:
        for s in packet['sources']:
            all_spans[s['id']]=merged_spans(all_spans.get(s['id'],[])+[(s['text_offset'],s['text_offset']+len(s['text']))])
    union=[{**{k:v for k,v in lookup[sid].items() if k!='retrieval_hints'},
            'text':lookup[sid]['text'][a:b],'text_offset':a} for sid,intervals in all_spans.items() for a,b in intervals]
    return {'sources':union,'packets':packets,'budget':budget,'route':route,'adjacent_expansion':expand,
        'used_chars':sum(p['used_chars'] for p in packets),'unique_chars':sum(len(s['text']) for s in union),
        'note':'Offline requirement-packet experiment. Shared union coverage can exceed actual requirement-owned coverage; report both. No evaluator calls or production policy change.'}


def compare_packets(replay, case_pack, ranker, *, budget=18000, progress=None):
    """Measure shared-union and actual requirement-owned inclusion separately."""
    from .evidence_cases import validate_cases,packet_coverage
    from .evaluation import select_context,_normal
    from .pipeline_diagnostics import retrieval_recall
    from .storage import digest
    from time import perf_counter
    started=perf_counter();sources,rubric=replay['sources'],replay['rubric']
    cases=validate_cases(case_pack,rubric,sources)
    ids={c['condition_id'] for c in cases}
    indicators=[i for i in rubric['indicators'] if any(c['id'] in ids for c in i['conditions'])]
    arms={n:{} for n in ('bm25','lexical_owned','combined_owned','combined_adjacent')};experiments={}
    for indicator in indicators:
        trace={};select_context(indicator,sources,semantic_ranker=ranker,diagnostics=trace)
        code=indicator['code'];arms['bm25'][code]=select_context(indicator,sources,max_chars=budget)
        experiments[code]={}
        for name,route,expand in (('lexical_owned','lexical',False),('combined_owned','combined',False),('combined_adjacent','combined',True)):
            exp=requirement_packets(trace,budget=budget,route=route,expand=expand)
            experiments[code][name]=exp;arms[name][code]=exp['sources']
        if progress:progress(code)
    gold=[g for rows in replay['gold_sets'].values() for g in rows];measurements={}
    for name,by_code in arms.items():
        selector=lambda indicator,sources,**kw:by_code[indicator['code']]
        measured={'shared_union_quotes':retrieval_recall(rubric,sources,gold,selector=selector,budget=budget),
                  'shared_union_bundles':packet_coverage(cases,rubric,sources,selector=selector,budget=budget)}
        if name!='bm25':
            owned={p['condition_id']:p['sources'] for exps in experiments.values() for p in exps[name]['packets']}
            def hit(cid,cite):
                return any(s['document_id']==cite['document_id'] and s['page_number']==cite['page']
                    and _normal(cite['quote']) in _normal(s['text']) for s in owned[cid])
            measured['owned_quote_hits']=sum(hit(g['condition_id'],g) for g in gold)
            measured['owned_known_positive_cases']=sum(any(all(hit(c['condition_id'],cite) for cite in bundle['citations'])
                for bundle in c['positive_bundles']) for c in cases if c['positive_bundles'])
        measurements[name]=measured
    return {'version':'requirement-owned-packet-experiment-2','no_provider_calls':True,
            'source_hash':digest(sources),'rubric_hash':digest(rubric),'case_pack_hash':digest(case_pack),
            'budget':budget,'elapsed_seconds':perf_counter()-started,'measurements':measurements,'experiments':experiments,
            'limitations':['Known inspected support bundles are not independent assessment truth.',
                'Fixed per-assertion reservations may starve requirements needing more evidence.',
                'Lexical novelty is not evidentiary sufficiency. No production retrieval mode was changed.',
                'A hypothetical separate model call per owned packet would incur additional prompt overhead; no live cost equivalence is claimed.']}
