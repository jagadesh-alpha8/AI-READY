"""Why was (or wasn't) this page used? An answer for a college that says we ignored its evidence (#41).

For a run and one or more of its frozen pages: per key indicator, whether the page reached the judge's packet (from
the run's own traces, exactly), whether a credited requirement cites it, and, when retrieval is recomputed with the
run's frozen ranker and routing, where the page's best passage ranked for each requirement and where the packet
stopped. No model calls. The recompute is checked against the run's traces: when it does not reproduce the packet
(a different worker, embedding model or code), it says so and its ranks are indicative only.

An identical copy dropped by page deduplication is reported as such, with the kept page it was read as.
"""
from .evaluation import select_context

VERSION = 'page-use-1'
ROLES_NOT_RETRIEVED = {'report_timestamp', 'reviewed_evidence', 'extracted_evidence'}


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


def page_use(run, page_ids, *, indicators=None, ranker=None, recompute=True):
    inputs = run.inputs or {}
    sources, rubric = inputs.get('sources') or [], inputs['rubric']
    policy = inputs.get('retrieval_policy') or {}
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
    rows = []
    for indicator in rubric['indicators']:
        code = indicator['code']
        if indicators and code not in indicators:
            continue
        trace = traces.get(code) or {}
        excerpts = [e for e in trace.get('source_excerpts') or [] if e.get('id') in looked_for]
        ids = {c['id'] for c in indicator['conditions']}
        cited = sorted(r['condition_id'] for r in records if r['condition_id'] in ids and (r.get('credit') or 0) > 0
                       and any(c.get('source_id') in looked_for for p in r.get('parts') or []
                               for c in p.get('citations') or []))
        row = {'indicator': code, 'name': indicator['name'], 'in_packet': bool(excerpts),
               'packet_chars_from_page': sum(len(e.get('text') or '') for e in excerpts),
               'roles': sorted({e.get('evidence_role') or 'retrieved' for e in excerpts}),
               'credited_requirements_citing_it': cited}
        if recompute and trace:
            diagnostics = {}
            context = select_context(indicator, structure['sources'] if structure else sources,
                                     semantic_ranker=ranker, diagnostics=diagnostics, structure=structure)
            retrieved = {e['id'] for e in trace.get('source_excerpts') or []
                         if (e.get('evidence_role') or 'retrieved') not in ROLES_NOT_RETRIEVED}
            row['recompute'] = {'reproduced': {s['id'] for s in context} == retrieved,
                                'requirements': _ranks(diagnostics, looked_for)}
        rows.append(row)
    return {'version': VERSION, 'run_id': str(run.pk), 'pages': sorted(targets),
            'read_as_identical_copy_of': read_as, 'ranking': 'hybrid' if ranker is not None else 'keyword',
            'indicators': rows,
            'summary': {'indicators_with_page_in_packet': sum(r['in_packet'] for r in rows),
                        'indicators_citing_it': sum(bool(r['credited_requirements_citing_it']) for r in rows),
                        'indicators': len(rows)}}
