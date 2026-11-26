"""Test 13's credited (requirement, page) pairs, keyed by document file name and page number so they match a
re-uploaded copy of the same documents (the live VISTAS sprint)."""
import json, sys
from collections import Counter

def credited_pairs(export_path):
    d = json.load(open(export_path, encoding='utf-8'))
    pages = {}
    for doc in d['source_manifest']:
        for p in doc.get('pages') or []:
            pages[p['page_id']] = (doc['filename'], p['number'])
    full, anyc = set(), set()
    for r in d['assessment']['records']:
        credit = float(r.get('credit') or 0)
        if credit <= 0:
            continue
        cites = list(r.get('citations') or [])
        for part in r.get('parts') or []:
            if part.get('credited_as') in ('full', 'related'):
                cites += part.get('citations') or []
        for c in cites:
            key = pages.get(c.get('source_id'))
            if key is None:
                continue
            pair = (r['condition_id'], key[0], key[1])
            anyc.add(pair)
            if credit >= 1:
                full.add(pair)
    return full, anyc

if __name__ == '__main__':
    full, anyc = credited_pairs(sys.argv[1])
    print('full-credit pairs', len(full), 'any-credit pairs', len(anyc))
    print('documents', Counter(f for _, f, _ in anyc).most_common(5))
