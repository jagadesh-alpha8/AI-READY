"""Replay harness for the compact re-judge (compact.py), built from the marked yardstick. No college is needed.

Design: claude.ai project doc claude/ai-ready-compact-rejudge-design-27-nov.md, "The test" and "Pass marks, set
now". Answers are made from a template on the rubric's own part wording ("This page shows that ..."), with no model
call. Tests:

1. Agreement with Stage 1 on Stage 1's own evidence: compact-judge every credited requirement on its cited and tagged
   passages alone, and compare part findings with Stage 1's, by yardstick mark (pass mark 5).
2. Missed pages: marked direct and supporting pages that never reached a Stage 1 packet, sent with an accurate answer
   (pass mark 1); also how often the map tags the sent page for its requirement.
3. Irrelevant pages: pages marked not evidence, and pages from an unrelated area, including requirements at "partly
   shown" and at zero with the subject shown in full; the false-claim probe sends the same pages with a confident,
   wrong answer (pass marks 2, 3, 4).
4. Pointed pages: marked pages that were in the packet but not cited, pointed at; how often a direct page fails only
   because one pass did not cite it (pass mark 1).
5. Selection in long documents (offline, no model calls): a marked page sent inside its whole document; how often
   the page is among the selected ones at 12,000 and 40,000 characters.
6. Repeatability: tests 2 and 3 twice (pass mark 7).

Tests 1 to 4 and 6 make model calls (--live) and run in both packet modes. Without --live they print the cases and the
estimated cost from the run's configured prices; Vijay approves the spend before a live run.
"""
import gzip
import json
import random
from collections import Counter, defaultdict

from . import compact

EVIDENCE = ('direct', 'supporting')
MARKS = {'d': 'direct', 's': 'supporting', 't': 'topical', 'n': 'not_evidence'}
OUTPUT_TOKENS = 3000      # per judging pass, a generous estimate from runs 3 and 4
PASSES = 2.2              # two passes and a third on some


# ------------------------------------------------------------------ inputs


def load_export(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as f:
        return json.load(f)


def load_marks(path):
    """[(requirement, filename, page, mark)] from the yardstick: the 'map marks' text (#Dn=filename lines, then
    row|mark|requirement|Dn|page) or a tab-separated file with a header (requirement, filename, page, mark)."""
    rows, docs = [], {}
    with open(path, encoding='utf-8') as f:
        lines = [line.rstrip('\n') for line in f if line.strip()]
    if lines and '\t' in lines[0] and 'requirement' in lines[0].lower():
        head = [h.strip().lower() for h in lines[0].split('\t')]
        for line in lines[1:]:
            row = dict(zip(head, line.split('\t')))
            rows.append((row['requirement'], row['filename'], int(float(row['page'])),
                         MARKS.get(row['mark'][:1].lower(), row['mark'])))
        return rows
    for line in lines:
        if line.startswith('#'):
            key, value = line[1:].split('=', 1)
            docs[key] = value
            continue
        _, mark, requirement, doc, page = line.split('|')
        if requirement.count('.') < 2:
            continue
        rows.append(('AIQIF-' + requirement if not requirement.startswith('AIQIF-') else requirement,
                     docs.get(doc, doc), int(page), MARKS.get(mark, mark)))
    return rows


def sources_from_run(run_id):
    """The run's frozen pages, with file names (on the server, from the database)."""
    from ..models import CapabilityRun
    run = CapabilityRun.objects.get(pk=run_id)
    names = {str(m.get('document_id')): m.get('filename') for m in (run.inputs or {}).get('manifest') or []}
    return [{**s, 'filename': s.get('filename') or names.get(str(s.get('document_id')))}
            for s in (run.inputs or {}).get('sources') or []], (run.inputs or {}).get('evidence_map') or {}


def sources_from_export(export):
    """Pages rebuilt from the packets' windows, for a machine without the database. Pages no packet reached are
    missing and pages only partly reached are partial, so test 5 on these is indicative only (the report says so)."""
    names, numbers = {}, {}
    for entry in export.get('source_manifest') or []:
        for page in entry.get('pages') or []:
            names[page['page_id']] = entry.get('filename')
            numbers[page['page_id']] = page.get('number')
    spans = defaultdict(dict)
    meta = {}
    for trace in (export.get('assessment') or {}).get('traces') or []:
        for w in trace.get('source_excerpts') or []:
            if w.get('evidence_role') == 'report_timestamp':
                continue
            spans[w['id']][w.get('text_offset') or 0] = w['text']
            meta[w['id']] = w
    out = []
    for pid, pieces in spans.items():
        text, end, gaps = '', 0, 0
        for start in sorted(pieces):
            piece = pieces[start]
            if start > end:
                gaps += 1
                text += ' ' * (start - end)
                end = start
            if start + len(piece) > end:
                text += piece[end - start:]
                end = start + len(piece)
        out.append({'id': pid, 'document_id': meta[pid].get('document_id'), 'page_number': numbers.get(pid),
                    'filename': names.get(pid), 'text': text, 'starts_at_zero': 0 in pieces, 'gaps': gaps})
    return out


def template_answer(cid, record=None):
    """"This page shows that ...", on the wording of the first part the record does not show in full."""
    from .layer2 import _pass_values
    from .part_judgment import _load
    parts = (_load()[0]['conditions'].get(cid) or {}).get('parts') or []
    current = {p['id']: p for p in (record or {}).get('parts') or []}
    wanted = next((p for p in parts if 'full' not in _pass_values(current.get(p['id'], {}), 'credited_as')),
                  parts[0] if parts else None)
    text = (wanted or {}).get('full') or 'this requirement is met'
    return 'This page shows that ' + text[0].lower() + text[1:].rstrip('.') + '.'


def wrong_answer(cid):
    """The false-claim probe: a confident answer that names the page as the evidence."""
    return template_answer(cid) + ' This is our approved policy for it, reviewed every year.'


# ------------------------------------------------------------------ test 5 (offline)


def test5(export, sources, marks, tags_by_key=None, caps=(12000, 40000)):
    """How often a marked page sent inside its whole document is among the selected pages."""
    records = {r['condition_id']: r for r in (export.get('assessment') or {}).get('records') or []}
    by_doc = defaultdict(list)
    for s in sources:
        by_doc[s.get('filename')].append(s)
    for pages in by_doc.values():
        pages.sort(key=lambda s: s.get('page_number') or 0)
    from .part_judgment import _load
    spec = _load()[0]['conditions']
    out = {str(cap): Counter() for cap in caps}
    rows = []
    for cid, filename, number, mark in marks:
        if mark not in EVIDENCE:
            continue
        document = by_doc.get(filename) or []
        target = next((s for s in document if s.get('page_number') == number), None)
        if target is None:
            for cap in caps:
                out[str(cap)]['page_not_available'] += 1
            continue
        answer = template_answer(cid, records.get(cid))
        row = {'requirement': cid, 'filename': filename, 'page': number, 'mark': mark,
               'document_pages': len(document), 'document_chars': sum(len(s['text']) for s in document)}
        for cap in caps:
            _, pages = compact.build(cid, (spec.get(cid) or {}).get('parts') or [], records.get(cid), [],
                                     sent=document, pointed=[], answers=[answer], tags_by_key=tags_by_key or {},
                                     corpus=[], caps={'sent': cap, 'total': max(cap, compact.CAPS['total'])})
            hit = target['id'] in pages['groups']['sent']
            whole = row['document_chars'] <= cap
            out[str(cap)][f'{mark}_{"selected" if hit else "missed"}'] += 1
            out[str(cap)]['whole_document_fit' if whole else 'had_to_select'] += 1
            row[f'selected_at_{cap}'] = hit
        rows.append(row)
    return {'counts': {cap: dict(c) for cap, c in out.items()}, 'rows': rows}


# ------------------------------------------------------------------ the live tests (model calls)


def _packets(export):
    return {t['indicator']: list(t.get('source_excerpts') or []) for t in (export.get('assessment') or {}).get('traces')
            or []}


def _code(cid):
    return cid.rsplit('.', 1)[0]


def cases(test, export, sources, marks, tags_by_key=None, *, seed=27, limit=None):
    """The cases of a live test: [{'test', 'requirement', 'mark', 'sent', 'pointed', 'answers', 'probe'}]."""
    records = {r['condition_id']: r for r in (export.get('assessment') or {}).get('records') or []}
    packets = _packets(export)
    reached = {code: {w['id'] for w in packet} for code, packet in packets.items()}
    by_key = {(s.get('filename'), s.get('page_number')): s for s in sources}
    out = []
    if test == 1:
        for cid, record in sorted(records.items()):
            if (record.get('credit') or 0) > 0:
                out.append({'test': 1, 'requirement': cid, 'mark': None, 'sent': [], 'pointed': [], 'answers': [],
                            'stage1_only': True})
    for cid, filename, number, mark in marks:
        page = by_key.get((filename, number))
        if page is None or _code(cid) not in packets:
            continue
        in_packet = page['id'] in reached[_code(cid)]
        record = records.get(cid) or {}
        cited = {c.get('source_id') for p in record.get('parts') or [] for c in (p.get('citations') or [])
                 + (p.get('second_citations') or [])}
        if test == 2 and mark in EVIDENCE and not in_packet:
            out.append({'test': 2, 'requirement': cid, 'mark': mark, 'sent': [page], 'pointed': [],
                        'answers': [template_answer(cid, record)]})
        if test == 3 and mark == 'not_evidence':
            out.append({'test': 3, 'requirement': cid, 'mark': mark, 'sent': [page], 'pointed': [],
                        'answers': [template_answer(cid, record)]})
            out.append({'test': 3, 'requirement': cid, 'mark': mark, 'sent': [page], 'pointed': [],
                        'answers': [wrong_answer(cid)], 'probe': 'false_claim'})
        if test == 4 and mark in EVIDENCE and in_packet and page['id'] not in cited:
            window = next(w for w in packets[_code(cid)] if w['id'] == page['id'])
            out.append({'test': 4, 'requirement': cid, 'mark': mark, 'sent': [],
                        'pointed': [{**window, 'evidence_role': 'answer_points_to'}],
                        'answers': [template_answer(cid, record)]})
    if test == 3:
        # Pages from an unrelated area, on requirements at "partly shown" and at zero with the subject shown in full.
        rng = random.Random(seed)
        from .layer2 import _pass_values
        weak = [cid for cid, r in records.items() if 0 < (r.get('credit') or 0) < 1 or (
            not r.get('credit') and r.get('parts') and 'full' in _pass_values(r['parts'][0], 'credited_as'))]
        for cid in sorted(weak):
            area = cid.split('.')[0]
            others = [s for s in sources if s['id'] not in reached.get(_code(cid), set())
                      and not any(m[0].split('.')[0] == area and m[1] == s.get('filename')
                                  and m[2] == s.get('page_number') for m in marks)]
            if others:
                out.append({'test': 3, 'requirement': cid, 'mark': 'unrelated_area', 'sent': [rng.choice(others)],
                            'pointed': [], 'answers': [template_answer(cid, records.get(cid))]})
    return out[:limit] if limit else out


def packet_for(case, export, mode, tags_by_key=None, corpus=()):
    """(packet, statement or None) for a case in a packet mode ('compact' or 'whole')."""
    from . import layer2
    from .part_judgment import _load
    cid = case['requirement']
    code = _code(cid)
    stage1 = _packets(export).get(code) or []
    record = {r['condition_id']: r for r in export['assessment']['records']}.get(cid)
    if case.get('stage1_only'):
        if mode == 'whole':
            return stage1, None
        packet, _ = compact.build(cid, (_load()[0]['conditions'].get(cid) or {}).get('parts') or [], record, stage1,
                                  sent=[], pointed=[], answers=[], tags_by_key=tags_by_key or {}, corpus=list(corpus))
        return packet, None
    if mode == 'whole':
        windows = [{**compact._whole(s, 'answer_attachment')} for s in case['sent']] + list(case['pointed'])
        contexts, _ = layer2.fixed_contexts([{'indicator': code, 'source_excerpts': stage1}],
                                            {code: {'conditions': [cid], 'windows': windows}})
        return contexts[code], None
    packet, _ = compact.build(cid, (_load()[0]['conditions'].get(cid) or {}).get('parts') or [], record, stage1,
                              sent=case['sent'], pointed=case['pointed'], answers=case['answers'],
                              tags_by_key=tags_by_key or {}, corpus=list(corpus))
    return packet, case['answers']


def estimate(case_list, export, tags_by_key=None, corpus=(), modes=('compact', 'whole')):
    """{mode: {'requests', 'input_tokens', 'usd'}} from the run's configured prices (per million tokens)."""
    calls = ((export.get('assessment') or {}).get('inference') or {}).get('calls') or []
    prices = next((c.get('configured_prices') for c in calls if c.get('configured_prices')), None) or {
        'input': '1', 'output': '5'}
    out = {}
    for mode in modes:
        tokens, usd = 0, 0.0
        for case in case_list:
            packet, _ = packet_for(case, export, mode, tags_by_key, corpus)
            n = sum(len(w['text']) for w in packet) / 3.5 + 6000
            long = prices.get('long_context') or {}
            rate = long if long and n > float(long.get('threshold') or 1e12) else prices
            tokens += n * PASSES
            usd += PASSES * (n * float(rate['input']) + OUTPUT_TOKENS * float(rate['output'])) / 1e6
        out[mode] = {'requests': round(len(case_list) * PASSES), 'input_tokens': int(tokens), 'usd': round(usd, 2)}
    return out


def judge(case, export, mode, service, tags_by_key=None, corpus=(), typed=True):
    """The re-judge's record for a case (two passes, a third where they disagree), on the case's packet."""
    from .evaluation import evaluate
    cid = case['requirement']
    code = _code(cid)
    packet, answers = packet_for(case, export, mode, tags_by_key, corpus)
    rubric = export['rubric']
    indicator = next(i for i in rubric['indicators'] if i['code'] == code)
    subset = {**rubric, 'indicators': [{**indicator, 'conditions': [c for c in indicator['conditions']
                                                                     if c['id'] == cid]}]}
    statement = compact.statement_block([(a, True) for a in answers or []]) if typed and answers else None
    sources = {w['id']: w for w in packet}
    outcome = evaluate(list(sources.values()), service=service, population=export.get('population') or 'All',
                       reference_period=export.get('reference_period') or 'Not recorded', rubric=subset,
                       scope=export.get('scope'), judgment='parts', agreement_passes=2, tie_break=True, max_calls=1,
                       fixed_contexts={code: packet}, statements={code: statement} if statement else None)
    return (outcome.get('records') or [None])[0]


def summarise(results):
    """Counts per test, mode and mark: part findings, rises, failures by one pass."""
    from .layer2 import _pass_values
    out = defaultdict(Counter)
    for row in results:
        key = f"test {row['test']} {row['mode']}{' typed' if row.get('typed') else ''}{' ' + row['probe'] if row.get('probe') else ''}"
        twin = row.get('record') or {}
        for part in twin.get('parts') or []:
            found = _pass_values(part, 'credited_as')
            out[key][f"{row.get('mark')}:{'/'.join(str(f) for f in found)}"] += 1
            if 'contradicted' in _pass_values(part, 'finding'):
                out[key]['contradicted'] += 1
            if any(f == 'full' for f in found) and not all(f == 'full' for f in found):
                out[key]['split_full'] += 1
    return {k: dict(v) for k, v in out.items()}
