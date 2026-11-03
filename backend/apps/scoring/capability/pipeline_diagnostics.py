"""Offline stage-by-stage diagnosis of why requirements stay unknown; never a provider request.

Each function isolates one layer: ingestion (what page text reaches assessment), extraction
(where claim quotations actually occur), retrieval (whether selected windows reach pages the
extraction layer tagged for an indicator, and pages a person labelled as evidence), and scoring
(how much of the reported interval each cause accounts for). Signals that use current database
state rather than frozen run inputs say so. None of this changes a decision or a score.
"""
import re
from collections import Counter
from fractions import Fraction

from .context_diagnostics import condition_cause
from .engine import indicator_bounds
from .evaluation import _normal, select_context

PLACEHOLDER = re.compile(r'AIOSTABLEMARKER[a-j]+')
STAGES = ('page_missing', 'quote_not_in_any_text', 'quote_only_in_tables', 'not_retrieved', 'batch_blocked',
          'provider_failure', 'model_unknown', 'model_not_met', 'model_conflicting', 'validation_downgraded', 'credited')


def rendered_sources(sources, pages):
    """Sources carrying the canonical evidence text (evidence_text.evidence_pages) of their stored pages.

    `pages` lists every stored page of the sources' documents: {'id', 'document_id', 'page_number',
    'text', 'tables'}. Header/footer cleanup runs across each whole document, as extraction and
    assessment do. Current database state: valid for a run only while its pages are unchanged.
    """
    from apps.extraction.services.evidence_text import evidence_pages
    canonical = {}
    for document in {p['document_id'] for p in pages}:
        rows = sorted((p for p in pages if p['document_id'] == document), key=lambda p: p['page_number'])
        canonical.update({p['id']: p['text'] for p in evidence_pages(rows)})
    return [{**s, 'text': canonical.get(s['id'], s['text'])} for s in sources]


def ingestion_health(sources, rendered=None, manifest=None):
    """Page text that reaches assessment, and what table placeholders keep out of it."""
    marked = [s for s in sources if PLACEHOLDER.search(s['text'])]
    result = {'pages': len(sources), 'pages_with_table_placeholders': len(marked),
              'table_placeholders': sum(len(PLACEHOLDER.findall(s['text'])) for s in sources),
              'assessed_chars': sum(len(s['text']) for s in sources),
              'pages_under_300_chars': sum(len(s['text'].strip()) < 300 for s in sources),
              'text_sources': dict(Counter(s.get('text_source') for s in sources)),
              'rendered_chars': None, 'table_chars_missing': None, 'share_of_text_missing': None}
    if manifest is not None:
        result['manifest_page_statuses'] = dict(Counter(p['status'] for d in manifest for p in d['pages']))
        result['expected_pages'] = sum(d.get('expected_pages') or 0 for d in manifest)
    if rendered is not None:
        full = sum(len(s['text']) for s in rendered)
        result.update(rendered_chars=full, table_chars_missing=full - result['assessed_chars'],
                      share_of_text_missing=round(1 - result['assessed_chars'] / full, 3) if full else None)
        worst = sorted(((len(r['text']) - len(s['text']), s['page_number']) for s, r in zip(sources, rendered)), reverse=True)
        result['pages_missing_most_table_text'] = [{'page': p, 'chars': n} for n, p in worst[:10] if n > 0]
    return result


def quote_location(quote, pages, frozen, rendered=None):
    """Where a claim quotation occurs: the frozen page text, only once tables are rendered, or neither."""
    quote = _normal(quote or '')
    if not quote:
        return 'no_quotation'
    if any(quote in _normal(frozen[k]) for k in pages if k in frozen):
        return 'frozen_page_text'
    if rendered is not None and any(quote in _normal(rendered[k]) for k in pages if k in rendered):
        return 'only_with_tables'
    if not any(k in frozen for k in pages):
        return 'cited_page_not_in_sources'
    return 'not_in_page_text'


def extraction_health(ledger, sources, rendered=None):
    """Claim quotations against page text. A quotation absent from frozen text can never anchor a claim."""
    from apps.facts.verification.grounding import parse_pages
    frozen = {(s['document_id'], s['page_number']): s['text'] for s in sources}
    full = {(s['document_id'], s['page_number']): s['text'] for s in rendered} if rendered is not None else None
    locations, by_kind = Counter(), {}
    for claim in ledger.get('claims', []):
        source = claim['source']
        keys = [(source.get('document_id'), p) for p in parse_pages(source.get('page'))]
        where = quote_location(source.get('quote'), keys, frozen, full)
        locations[where] += 1
        by_kind.setdefault(claim.get('kind') or 'unclassified', Counter())[where] += 1
    return {'claims': sum(locations.values()), 'quotation_location': dict(locations),
            'by_kind': {k: dict(v) for k, v in by_kind.items()},
            'grounding_status': dict(Counter(c['verification'].get('grounding') or 'unset' for c in ledger.get('claims', []))),
            'note': 'Only frozen_page_text quotations can anchor a claim in an excerpt-scoped review packet.'}


FIDELITY_THRESHOLD = 0.9


def extraction_fidelity(health, threshold=FIDELITY_THRESHOLD):
    """Gate: the share of claim quotations that occur verbatim in the text assessment reads.

    Below the threshold, most reviewed claims cannot anchor in a review packet however good
    retrieval is. `with_tables` is the share once stored tables are rendered back in.
    """
    located = health['quotation_location']
    quoted = health['claims'] - located.get('no_quotation', 0)
    frozen = located.get('frozen_page_text', 0)
    tables = located.get('only_with_tables', 0)
    rate = round(frozen / quoted, 3) if quoted else None
    return {'threshold': threshold, 'claims_with_quotations': quoted, 'rate': rate,
            'rate_with_tables': round((frozen + tables) / quoted, 3) if quoted else None,
            'passes': rate is not None and rate >= threshold}


def tagged_pages(mappings):
    """indicator code -> {(document_id, page)} from AI-QIF tags (current database state).

    `mappings` rows: {'indicator_code', 'document_id', 'page', 'relationship', 'review_status'}.
    Contextual and rejected tags are excluded, as coverage excludes them.
    """
    from apps.facts.verification.grounding import parse_pages
    pages = {}
    for m in mappings:
        if m['relationship'] == 'contextual' or m['review_status'] == 'rejected':
            continue
        for p in parse_pages(m['page']):
            pages.setdefault(m['indicator_code'], set()).add((m['document_id'], p))
    return pages


def retrieval_against_tags(rubric, traces, tags, *, rendered=None):
    """Share of tagged evidence pages each indicator's selected windows reach; with `rendered`, also after tables return."""
    selected = {t['indicator']: {(s['document_id'], s['page_number']) for s in t['source_excerpts']} for t in traces}
    rows, total, hit, hit_rendered = [], 0, 0, 0
    for indicator in rubric['indicators']:
        code = indicator['code']
        wanted = tags.get(code, set())
        row = {'indicator': code, 'tagged_pages': len(wanted), 'selected_pages': len(selected.get(code, ())),
               'tagged_pages_selected': len(wanted & selected.get(code, set()))}
        if rendered is not None:
            again = {(s['document_id'], s['page_number']) for s in select_context(indicator, rendered)}
            row['tagged_pages_selected_with_tables'] = len(wanted & again)
            hit_rendered += row['tagged_pages_selected_with_tables']
        total += row['tagged_pages']
        hit += row['tagged_pages_selected']
        rows.append(row)
    return {'tagged_pages': total, 'tagged_pages_selected': hit,
            'tagged_pages_selected_with_tables': hit_rendered if rendered is not None else None, 'indicators': rows,
            'note': 'Tags are the extraction layer\'s own (mostly automatic) labels, not ground truth.'}


def retrieval_sweep(rubric, tags, sources, *, rendered=None, budgets=(18000, 36000, 72000)):
    """Tagged pages reached at each selection budget, against what selecting that share of text at random would reach.

    Recall that only tracks the share of text selected means ranking adds nothing; a fixed budget
    then cannot be tuned into reliable retrieval.
    """
    corpora = {'frozen': sources, **({'with_tables': rendered} if rendered is not None else {})}
    total = sum(len(tags.get(i['code'], ())) for i in rubric['indicators'])
    rows = []
    for budget in budgets:
        row = {'budget_chars': budget, 'tagged_pages': total}
        for label, corpus in corpora.items():
            size = sum(len(s['text']) for s in corpus) or 1
            hit = sum(len(tags.get(i['code'], set()) & {(s['document_id'], s['page_number'])
                                                         for s in select_context(i, corpus, max_chars=budget)})
                      for i in rubric['indicators'])
            row[label] = {'tagged_pages_selected': hit, 'chance_expectation': round(total * min(1, budget / size), 1)}
        rows.append(row)
    return rows


def retrieval_recall(rubric, sources, gold, *, selector=select_context, budget=18000):
    """Labelled-evidence recall of one retrieval method at a fixed budget, with window economy.

    An item is retrieved when a selected window of its requirement's indicator contains the
    labelled quotation; `page_hits` only needs the page. Unique coverage merges overlapping
    windows on the same page. `evidence_type` ('prose'/'table') groups items when the gold set has it.
    """
    indicators = {c['id']: i for i in rubric['indicators'] for c in i['conditions']}
    selections = {}
    items = []
    for item in gold:
        indicator = indicators[item['condition_id']] if item.get('condition_id') else next(
            i for i in rubric['indicators'] if i['code'] == item['indicator'])
        if indicator['code'] not in selections:
            selections[indicator['code']] = selector(indicator, sources, max_chars=budget)
        windows = selections[indicator['code']]
        quote = _normal(item['quote'])
        on_page = [w for w in windows if w['page_number'] == int(item['page'])
                   and (not item.get('document_id') or w['document_id'] == item['document_id'])]
        items.append({'condition_id': item.get('condition_id'), 'indicator': indicator['code'], 'page': int(item['page']),
                      'evidence_type': item.get('evidence_type', 'unlabelled'),
                      'retrieved': any(quote in _normal(w['text']) for w in on_page), 'page_selected': bool(on_page)})
    economy = {}
    for code, windows in selections.items():
        spans = {}
        for w in windows:
            spans.setdefault(w['id'], []).append((w['text_offset'], w['text_offset'] + len(w['text'])))
        unique = 0
        for ranges in spans.values():
            end = -1
            for start, stop in sorted(ranges):
                unique += max(0, stop - max(start, end))
                end = max(end, stop)
        selected = sum(len(w['text']) for w in windows)
        economy[code] = {'windows': len(windows), 'pages': len(spans), 'selected_chars': selected,
                         'unique_chars': unique, 'overlapping_chars': selected - unique}
    by_type = {}
    for row in items:
        group = by_type.setdefault(row['evidence_type'], {'items': 0, 'retrieved': 0, 'page_selected': 0})
        group['items'] += 1
        group['retrieved'] += row['retrieved']
        group['page_selected'] += row['page_selected']
    return {'budget_chars': budget, 'items': items, 'retrieved': sum(r['retrieved'] for r in items),
            'page_hits': sum(r['page_selected'] for r in items), 'of': len(items), 'by_type': by_type,
            'indicators': economy}


def interval_attribution(export, causes=None):
    """Points of the reported interval each unresolved requirement accounts for, grouped by cause and level.

    For each indicator, its width is split equally across its undecided conditions; this is exact
    for independent-condition rubrics. Upper falls below 100 only through not_met decisions.
    """
    rubric = export['rubric']
    records = {r['condition_id']: r for r in export['assessment']['records']}
    traces = {t['indicator']: t for t in export['assessment']['traces']}
    decisions = {cid: r['state'] for cid, r in records.items()}
    by_cause, by_level, by_indicator = Counter(), Counter(), []
    lower_total = upper_total = Fraction()
    for indicator in rubric['indicators']:
        low, high = indicator_bounds(indicator, decisions)
        scale = Fraction(100, 3) * Fraction(str(indicator['weight_units'])) / 1000
        lower_total += Fraction(low) * scale
        upper_total += Fraction(high) * scale
        open_ids = [c for c in indicator['conditions'] if decisions[c['id']] in ('unknown', 'conflicting')]
        width = (Fraction(high) - Fraction(low)) * scale
        for condition in open_ids:
            cause = (causes or {}).get(condition['id']) or condition_cause(records[condition['id']], traces[indicator['code']])
            share = width / len(open_ids)
            by_cause[cause] += share
            by_level[condition['level']] += share
        if width:
            by_indicator.append({'indicator': indicator['code'], 'points': float(round(width, 2)),
                                 'open_requirements': len(open_ids)})
    lost_upper = Fraction(100) - upper_total
    return {'lower': float(round(lower_total, 2)), 'upper': float(round(upper_total, 2)),
            'width': float(round(upper_total - lower_total, 2)),
            'width_by_cause': {k: float(round(v, 2)) for k, v in by_cause.most_common()},
            'width_by_level': {k: float(round(v, 2)) for k, v in sorted(by_level.items())},
            'upper_lost_to_not_met': float(round(lost_upper, 2)),
            'not_met_decisions': sum(s == 'not_met' for s in decisions.values()),
            'widest_indicators': sorted(by_indicator, key=lambda r: -r['points'])[:10]}


def _resolve_document(item, manifest):
    if item.get('document_id'):
        return item['document_id']
    names = {d['filename']: d['document_id'] for d in manifest}
    if item.get('document') in names:
        return names[item['document']]
    return manifest[0]['document_id'] if len(manifest) == 1 else None


def retrieval_budget_needed(indicator, sources, page_key, quote, *, ceiling=200000):
    """Smallest selection budget (chars) at which this indicator's retrieval would include the quotation, if any.

    18,000 (the default) means a replay reaches it: the saved selection differs from today's retrieval.
    None means not even `ceiling` characters reach it.
    """
    def includes(budget):
        return any((s['document_id'], s['page_number']) == page_key and quote in _normal(s['text'])
                   for s in select_context(indicator, sources, max_chars=budget))
    if not includes(ceiling):
        return None
    low, high = 18000, ceiling
    if includes(low):
        return low
    while high - low > 1000:
        mid = (low + high) // 2
        low, high = (low, mid) if includes(mid) else (mid, high)
    return high


def gold_funnel(export, sources, gold, *, rendered=None):
    """First stage that loses each person-labelled piece of evidence.

    `gold` items: {'condition_id' or 'indicator', 'page', 'quote', optional 'document' (filename) or
    'document_id', 'note'}. The quotation should be copied from the PDF; it is matched
    whitespace-insensitively. An indicator-level item (evidence for the indicator, requirement not
    named) is credited when any of its requirements is met.
    `retrieved_with_tables` says whether retrieval over table-rendered pages would reach the quotation.
    """
    rubric = export['rubric']
    records = {r['condition_id']: r for r in export['assessment']['records']}
    traces = {t['indicator']: t for t in export['assessment']['traces']}
    frozen = {(s['document_id'], s['page_number']): s for s in sources}
    full = {(s['document_id'], s['page_number']): s for s in rendered} if rendered is not None else {}
    selected_with_tables = {}
    rows = []
    for item in gold:
        cid = item.get('condition_id')
        indicator = next(i for i in rubric['indicators']
                         if i['code'] == item.get('indicator') or any(c['id'] == cid for c in i['conditions']))
        trace = traces[indicator['code']]
        targets = [records[cid]] if cid else [records[c['id']] for c in indicator['conditions']]
        key = (_resolve_document(item, export['source_manifest']), int(item['page']))
        quote = _normal(item['quote'])
        row = {'condition_id': cid, 'indicator': indicator['code'], 'page': key[1], 'note': item.get('note', ''),
               'retrieval_budget_needed': None, 'retrieved_with_tables': None}
        if rendered is not None and key in full and quote in _normal(full[key]['text']):
            if indicator['code'] not in selected_with_tables:
                selected_with_tables[indicator['code']] = select_context(indicator, rendered)
            row['retrieved_with_tables'] = any((s['document_id'], s['page_number']) == key and quote in _normal(s['text'])
                                               for s in selected_with_tables[indicator['code']])
        if key not in frozen:
            row['stage'] = 'page_missing'
        elif quote not in _normal(frozen[key]['text']):
            row['stage'] = 'quote_only_in_tables' if key in full and quote in _normal(full[key]['text']) else 'quote_not_in_any_text'
        elif not any((s['document_id'], s['page_number']) == key and quote in _normal(s['text']) for s in trace['source_excerpts']):
            row['stage'] = 'not_retrieved'
            row['retrieval_budget_needed'] = retrieval_budget_needed(indicator, sources, key, quote)
        else:
            met = [r for r in targets if r['state'] == 'met']
            record = met[0] if met else targets[0]
            cause = condition_cause(record, trace)
            if not met and any(r.get('validation_issue') and not condition_cause(r, trace).startswith('not_evaluated') for r in targets):
                cause = 'validation_rejected'
            row['stage'] = ('batch_blocked' if cause.startswith('not_evaluated') else 'provider_failure' if cause == 'provider_failure'
                            else 'validation_downgraded' if cause == 'validation_rejected'
                            else 'credited' if record['state'] == 'met'
                            else {'not_met': 'model_not_met', 'conflicting': 'model_conflicting'}.get(record['state'], 'model_unknown'))
            row['model_reason'] = record['reason']
            row['scope_supported'], row['period_supported'] = record.get('scope_supported'), record.get('period_supported')
        rows.append(row)
    return {'items': rows, 'first_failure_counts': dict(Counter(r['stage'] for r in rows)),
            'retrieved_with_tables': dict(Counter(str(r['retrieved_with_tables']) for r in rows)),
            'stages_in_order': list(STAGES)}


def provisional_gold(mappings, rendered, *, limit_per_indicator=3):
    """Indicator-level labelled evidence drafted from the extraction layer's own tags, for people to review.

    `mappings` rows: {'indicator_code', 'relationship', 'review_status', 'auto_accepted', 'document_id',
    'page', 'quote', 'fact_id'}. Keeps direct/supporting tags that are confirmed or auto-accepted and
    whose quotation occurs in the cited page once tables are rendered. Not ground truth.
    """
    from apps.facts.verification.grounding import parse_pages
    text = {(s['document_id'], s['page_number']): _normal(s['text']) for s in rendered}
    ranked = sorted(mappings, key=lambda m: (m['relationship'] != 'direct', m['review_status'] != 'confirmed', m['fact_id']))
    items, per = [], Counter()
    for m in ranked:
        if (m['relationship'] == 'contextual' or m['review_status'] == 'rejected'
                or not (m['review_status'] == 'confirmed' or m['auto_accepted']) or per[m['indicator_code']] >= limit_per_indicator):
            continue
        quote = _normal(m['quote'] or '')
        page = next((p for p in parse_pages(m['page']) if quote and quote in text.get((m['document_id'], p), '')), None)
        if page is None:
            continue
        per[m['indicator_code']] += 1
        items.append({'indicator': m['indicator_code'], 'page': page, 'quote': quote, 'document_id': m['document_id'],
                      'note': f"provisional: {m['relationship']} tag, {'confirmed' if m['review_status'] == 'confirmed' else 'auto-accepted'}; fact {m['fact_id']}"})
    return items


def oracle_window(source, quote, size=3000):
    """A window of `source` containing `quote` (matched across any whitespace), or None."""
    words = quote.split()
    match = re.search(r'\s+'.join(re.escape(w) for w in words), source['text']) if words else None
    if match is None:
        return None
    start = max(0, min(match.start() - size // 3, len(source['text']) - size))
    return {**source, 'text': source['text'][start:start + size], 'text_offset': start}


def oracle_contexts(export, rendered, gold):
    """Per indicator: the run's own selected windows plus a window around each labelled quotation.

    Labelled windows come from table-rendered page text, so this asks: had ingestion and retrieval
    delivered this evidence, would the evaluator credit it? Offsets refer to rendered text; these
    contexts are diagnostic and never publishable.
    """
    pages = {(s['document_id'], s['page_number']): s for s in rendered}
    traces = {t['indicator']: t for t in export['assessment']['traces']}
    contexts, items = {}, {}
    for item in gold:
        code = item.get('indicator') or item['condition_id'].rsplit('.', 1)[0]
        key = (_resolve_document(item, export['source_manifest']), int(item['page']))
        window = oracle_window(pages[key], item['quote']) if key in pages else None
        context = contexts.setdefault(code, list(traces[code]['source_excerpts']))
        items.setdefault(code, []).append({**item, 'oracle_window_found': window is not None})
        if window and not any(w['id'] == window['id'] and w['text_offset'] == window['text_offset'] for w in context):
            context.append(window)
    return contexts, items
