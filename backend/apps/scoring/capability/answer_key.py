"""Score one saved assessment against a private answer key and locate the first stage that failed.

Offline: reads an assessment export (AIQIF-REPORT) and an answer key; no model calls, no database.

Answer key shape (kept outside the repository; it carries institutional quotations):
    {"version": "...", "document": {"match": "<substring of the scored document's filename>"},
     "conditions": {"AIQIF-C7.1.F1": {"expected": "met", "status": "confirmed",
                                      "evidence": [{"page": 77, "quote": "..."}], "note": "..."}, ...}}
`status` confirmed or draft is scored; needs_decision and needs_text are reported but not scored.

Stages, checked in order for each wrong decision (the four-boundary diagnosis):
    source_integrity  an evidence page was never frozen as a source (lost, unreadable or blank)
    packet_page       the frozen page never reached that indicator's evidence packet
    packet_passage    the page reached the packet but no excerpt contains the supporting quotation
    judgment          the supporting passage was in the packet, or the credit was not supported
"""
import re
from collections import Counter

SCORED = ('confirmed', 'draft')


def _norm(text):
    return re.sub(r'\s+', ' ', text or '').strip().casefold()


def _indicator(condition_id):
    return condition_id.rsplit('.', 1)[0]


def check(export, key):
    match = key.get('document', {}).get('match', '')
    documents = [m for m in export['source_manifest'] if match and match in (m.get('filename') or '')]
    if len(documents) != 1:
        raise ValueError(f'answer key document "{match}" matches {len(documents)} documents in the export')
    doc = documents[0]
    frozen = set(export['scope']['source_ids'])
    page_id = {p['number']: p['page_id'] for p in doc['pages']}
    number = {v: k for k, v in page_id.items()}
    records = {r['condition_id']: r for r in export['assessment']['records']}
    traces = {t['indicator']: t for t in export['assessment'].get('traces', [])}

    rows, outcomes, stages = [], Counter(), Counter()
    for cid, expected in sorted(key['conditions'].items()):
        record = records.get(cid)
        got = record['state'] if record else 'missing'
        want = expected['expected']
        row = {'condition_id': cid, 'expected': want, 'got': got, 'status': expected.get('status', 'draft'),
               'cited_pages': sorted({number[c['source_id']] for c in (record or {}).get('citations', [])
                                      if c.get('source_id') in number}),
               'cited_other_documents': sum(c.get('source_id') not in number for c in (record or {}).get('citations', []))}
        if got == want:
            row['outcome'] = 'correct'
        elif got == 'met' and not row['cited_pages'] and row['cited_other_documents']:
            # The key covers one document; a credit resting only on another document is outside its scope.
            row['outcome'], row['status'] = 'other_document_credit', 'out_of_scope'
        elif want == 'met':
            row['outcome'] = 'missed_credit'
        elif got == 'met':
            row['outcome'] = 'unsupported_credit'
        else:
            row['outcome'] = 'wrong_state'
        if row['outcome'] not in ('correct', 'other_document_credit'):
            row.update(_first_failure(expected, traces.get(_indicator(cid)), page_id, frozen, row['outcome']))
        rows.append(row)
        if row['status'] in SCORED:
            outcomes[row['outcome']] += 1
            if row['outcome'] != 'correct':
                stages[row['stage']] += 1
    scored = sum(outcomes.values())
    return {
        'version': 'answer-key-check-0.1',
        'run_id': export.get('run_id'),
        'answer_key': key.get('version'),
        'document': doc.get('filename'),
        'scored_conditions': scored,
        'correct': outcomes['correct'],
        'accuracy': round(outcomes['correct'] / scored, 4) if scored else None,
        'outcomes': dict(outcomes),
        'first_failed_stage': dict(stages),
        'not_scored': dict(Counter(r['status'] for r in rows if r['status'] not in SCORED)),
        'conditions': rows,
        'limitations': 'Accuracy is only as good as the answer key. Excerpt checks use the excerpts saved in the '
                       'export; a quotation split across two windows counts as missing from the packet.',
    }


def instability(results):
    """Conditions whose decision differs across checked runs, in run order."""
    by_condition = {}
    for result in results:
        for row in result['conditions']:
            by_condition.setdefault(row['condition_id'], (row['expected'], []))[1].append(row['got'])
    return [{'condition_id': cid, 'expected': expected, 'states': states}
            for cid, (expected, states) in sorted(by_condition.items()) if len(set(states)) > 1]


def _first_failure(expected, trace, page_id, frozen, outcome):
    if outcome != 'missed_credit' or not expected.get('evidence'):
        return {'stage': 'judgment', 'detail': 'The decision is not supported by the answer key evidence.'
                if outcome == 'unsupported_credit' else 'State differs from the answer key.'}
    in_packet = set(trace['source_ids']) if trace else set()
    excerpts = [(_norm(e.get('text')), e.get('id')) for e in (trace or {}).get('source_excerpts', [])]
    pages = [e['page'] for e in expected['evidence']]
    if not any(page_id.get(p) in frozen for p in pages):
        return {'stage': 'source_integrity', 'detail': f'No evidence page was frozen: {pages}'}
    if not any(page_id.get(p) in in_packet for p in pages):
        return {'stage': 'packet_page', 'detail': f'Frozen evidence pages {pages} never reached the packet'}
    for item in expected['evidence']:
        quote, pid = _norm(item['quote']), page_id.get(item['page'])
        if any(quote in text and source == pid for text, source in excerpts):
            return {'stage': 'judgment', 'detail': f'Supporting passage on p{item["page"]} was in the packet'}
    return {'stage': 'packet_passage', 'detail': 'Evidence page reached the packet, but no excerpt holds the supporting quotation'}
