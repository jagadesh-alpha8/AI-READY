"""Why was (or wasn't) this page used? An answer for a college that says we ignored its evidence (#41).

For a run and one or more of its frozen pages: per key indicator, whether the page reached the judge's packet (from
the run's own traces, exactly), whether a credited requirement cites it, and, when retrieval is recomputed with the
run's frozen ranker and routing, where the page's best passage ranked for each requirement and where the packet
stopped. No model calls.

The recompute rebuilds each packet with the function the run used (evaluation._prepare: retrieval, then the
extracted-evidence lane under the run's frozen lane version and prompt ceiling) and compares it passage by passage
(page and offset) with the trace. When it does not reproduce the packet (a different worker, embedding model or code),
it says so, lists the passages that differ, and its ranks are indicative only.

A final run (one that refines a provisional run through the second layer) is read the way it was made: retrieval ran on
the provisional run's pages, so the recompute uses those; a re-judged key indicator's packet also holds the windows the
second layer added (answers' documents, searches with the institution's answers, additional evidence), which are
reported by role and never counted as retrieval. Test 13 (22 Nov): page-use-1 compared the final run's re-judged C2.1
packet, second-layer windows included, with retrieval alone, so it reported "does not reproduce" for C2.1 only, the one
key indicator test 13 re-judged; the prompt-ceiling check rebuilt all 36 provisional packets exactly.

The targeted extra search (follow_up.py) adds windows after the first judgment; they are reported, not recomputed.

An identical copy dropped by page deduplication is reported as such, with the kept page it was read as.
"""
VERSION = 'page-use-2'
SECOND_LAYER_ROLES = {'answer_attachment', 'answer_search', 'extraction_tag', 'credited_evidence', 'answer_points_to'}
AFTER_JUDGMENT_ROLES = {'follow_up_search'}
NOT_RETRIEVAL_ROLES = {'report_timestamp', 'reviewed_evidence', 'extracted_evidence'}
DIFFERENCES_SHOWN = 10


def _completed_payload(run):
    event = run.events.filter(state='completed').order_by('-created_at').first()
    if event is None:
        raise ValueError('The run has no completed assessment.')
    return event.payload


def _structure(sources, policy):
    if not any(policy.get(k) is not None for k in ('structure', 'deduplicate', 'repeat_skip')):
        return None
    from . import structure as document_structure
    return document_structure.build(sources, deduplicate_pages=policy.get('deduplicate') is not None,
                                    routing=policy.get('structure') is not None,
                                    repeat_skip=policy.get('repeat_skip') is not None)


def retrieval_sources(run):
    """The frozen pages retrieval read: a final run's pages less the ones the second layer added (publish_final)."""
    inputs = run.inputs or {}
    added = set(((inputs.get('second_layer') or {}).get('added_sources')) or [])
    return [s for s in inputs.get('sources') or [] if s['id'] not in added]


def resolve_pages(run, *, page_ids=None, document_id=None, page_number=None):
    """The frozen page ids asked about: by page id, or a document's pages (one page number, or all)."""
    sources = (run.inputs or {}).get('sources') or []
    if page_ids:
        known = {s['id'] for s in sources}
        missing = [p for p in page_ids if p not in known]
        if missing:
            raise ValueError(f'Not pages of this run: {", ".join(missing)}.')
        return list(page_ids)
    pages = [s['id'] for s in sources if str(s.get('document_id')) == str(document_id)
             and (page_number is None or str(s.get('page_number')) == str(page_number))]
    if not pages:
        raise ValueError('No frozen page of this run matches that document and page.')
    return pages


def _ranks(diagnostics, targets):
    """Per requirement: the best 1-based rank of a target passage in the route the packet was filled from, the deepest
    rank the packet took, and what happened when a target passage was tried."""
    passages = diagnostics.get('passages') or []
    target_idx = {n for n, p in enumerate(passages) if getattr(p, 'source', {}).get('id') in targets}
    out = []
    attempts = diagnostics.get('packing_attempts') or []
    for requirement in diagnostics.get('requirements') or []:
        route = 'fused' if requirement.get('fused') else 'lexical'
        order = requirement.get(route) or []
        position = {n: i + 1 for i, n in enumerate(order)}
        best = min((position[n] for n in target_idx if n in position), default=None)
        mine = [a for a in attempts if a.get('condition_id') == requirement.get('condition_id')]
        taken = [position[a['passage']] for a in mine if a['outcome'] == 'selected' and a['passage'] in position]
        tried = sorted({a['outcome'] for a in mine if a['passage'] in target_idx})
        out.append({'condition_id': requirement.get('condition_id'), 'route': route, 'best_rank': best,
                    'candidates_ranked': len(order), 'deepest_rank_taken': max(taken, default=None),
                    'target_attempt_outcomes': tried})
    return out


def _key(window):
    return window['id'], window.get('text_offset', 0), len(window.get('text') or '')


def _row(window):
    return {'id': window['id'], 'offset': window.get('text_offset', 0), 'chars': len(window.get('text') or ''),
            'role': window.get('evidence_role') or 'retrieved'}


def compare_packets(traced, rebuilt):
    """(reproduced, differences): the trace's first-judgment packet against the rebuilt one, passage by passage.
    Windows added after the first judgment (second layer, targeted extra search) are left out of the trace's side."""
    first = [w for w in traced if (w.get('evidence_role') or 'retrieved') not in SECOND_LAYER_ROLES | AFTER_JUDGMENT_ROLES]
    in_run, in_rebuild = {_key(w): w for w in first}, {_key(w): w for w in rebuilt}
    only_run = [_row(in_run[k]) for k in in_run if k not in in_rebuild]
    only_rebuild = [_row(in_rebuild[k]) for k in in_rebuild if k not in in_run]
    differences = {'only_in_run': only_run[:DIFFERENCES_SHOWN], 'only_in_rebuild': only_rebuild[:DIFFERENCES_SHOWN],
                   'counts': {'only_in_run': len(only_run), 'only_in_rebuild': len(only_rebuild)}}
    return not only_run and not only_rebuild, differences


def page_use(run, page_ids, *, indicators=None, ranker=None, recompute=True):
    from .evaluation import _prepare, map_argument
    inputs = run.inputs or {}
    rubric = inputs['rubric']
    policy = inputs.get('retrieval_policy') or {}
    execution = inputs.get('execution_policy') or {}
    sources = retrieval_sources(run)
    second_layer = inputs.get('second_layer') or {}
    added = set(second_layer.get('added_sources') or [])
    payload = _completed_payload(run)
    traces = {t['indicator']: t for t in payload.get('traces') or []}
    records = payload.get('records') or []
    targets = set(page_ids)
    structure = _structure(sources, policy) if recompute else None
    read_as = {}
    if structure is not None:
        by_page = {(s['document_id'], s['page_number']): s['id'] for s in sources}
        for row in structure.get('dropped', []):
            dropped, kept = by_page.get(tuple(row['page'])), by_page.get(tuple(row['kept_page']))
            if dropped in targets and kept:
                read_as[dropped] = kept
    looked_for = targets | set(read_as.values())
    common = None
    if recompute:
        common = dict(sources=sources, semantic_ranker=ranker, gemini=True,
                      reviewed_evidence=inputs.get('reviewed_evidence'), population=inputs.get('population') or '',
                      reference_period=inputs.get('reference_period') or '', scope=inputs.get('scope'),
                      structure=structure, lane_version=policy.get('evidence_lane'), ceiling=policy.get('prompt_ceiling'),
                      judgment=execution.get('judgment', 'conditions'), keyword_chars=policy.get('keyword_chars'),
                      evidence_map=map_argument(policy, inputs.get('evidence_map')))
    rows = []
    for indicator in rubric['indicators']:
        code = indicator['code']
        if indicators and code not in indicators:
            continue
        trace = traces.get(code) or {}
        packet = trace.get('source_excerpts') or []
        excerpts = [e for e in packet if e.get('id') in looked_for]
        ids = {c['id'] for c in indicator['conditions']}
        cited = sorted(r['condition_id'] for r in records if r['condition_id'] in ids and (r.get('credit') or 0) > 0
                       and any(c.get('source_id') in looked_for for p in r.get('parts') or []
                               for c in p.get('citations') or []))
        later = sorted({e.get('evidence_role') for e in packet
                        if e.get('evidence_role') in SECOND_LAYER_ROLES | AFTER_JUDGMENT_ROLES})
        row = {'indicator': code, 'name': indicator['name'], 'in_packet': bool(excerpts),
               'packet_chars_from_page': sum(len(e.get('text') or '') for e in excerpts),
               'roles': sorted({e.get('evidence_role') or 'retrieved' for e in excerpts}),
               'credited_requirements_citing_it': cited,
               'rejudged_in_second_layer': code in (second_layer.get('targets') or {}) or any(
                   r in SECOND_LAYER_ROLES for r in later),
               'windows_added_after_first_judgment': later}
        if trace.get('evidence_map'):
            # Map mode: why the page is in the packet (the step and the tag that brought it), or that it isn't.
            row['map_reasons'] = [r for w in trace['evidence_map'].get('windows') or [] if w.get('id') in looked_for
                                  for r in w.get('reasons') or []]
        if recompute and trace:
            diagnostics = {}
            job = _prepare(indicator, **common, diagnostics=diagnostics)
            reproduced, differences = compare_packets(packet, job['context'])
            row['recompute'] = {'reproduced': reproduced, 'requirements': _ranks(diagnostics, looked_for),
                                **({} if reproduced else {'differences': differences})}
        rows.append(row)
    return {'version': VERSION, 'run_id': str(run.pk), 'pages': sorted(targets),
            'read_as_identical_copy_of': read_as, 'ranking': 'hybrid' if ranker is not None else 'keyword',
            'final_run_of': second_layer.get('provisional_run_id'),
            'pages_added_in_second_layer': sorted(targets & added),
            'indicators': rows,
            'summary': {'indicators_with_page_in_packet': sum(r['in_packet'] for r in rows),
                        'indicators_citing_it': sum(bool(r['credited_requirements_citing_it']) for r in rows),
                        'indicators': len(rows),
                        **({'reproduced': sum(r['recompute']['reproduced'] for r in rows if 'recompute' in r),
                            'recomputed': sum('recompute' in r for r in rows)} if recompute else {})}}
