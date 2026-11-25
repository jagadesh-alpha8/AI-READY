"""Answer key v2: the map's direct and supporting tags on (requirement, page) pairs test 13 never credited, laid out for a
person to read, so new real evidence is counted instead of discounted.

  python scripts/retrieval/review_sheet.py SOURCES.json MAP.json TEST13_EXPORT.json --out review.json [--seed seed.json]

Each row: requirement (id and sentence), document and page, the tag's strength, quote and reason, and the page text
around the quote. A reviewer fills "verdict": direct | supporting | not_evidence | topical, and "note". Rows also carry
whether any test 13 packet held the page (never_seen: no judge has read it). Direct tags come first.
The seed (the 25 Nov hand reading of Self-Study Report pages) is merged in as already reviewed.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from compare import gold_pairs, norm  # noqa: E402  (sets up Django)

from apps.scoring.capability.engine import release  # noqa: E402
from apps.evidence_map import spec  # noqa: E402

SEED = [  # 25 Nov hand reading (claude/ai-ready-overnight-24-nov.md): Self-Study Report pages missing from test 13
    *({'requirement': 'AIQIF-C9.2.A2', 'page_number': n, 'verdict': 'direct',
       'note': 'before/after values with a remark (DVV annexure)'} for n in (183, 184, 185, 186)),
    {'requirement': 'AIQIF-C6.2', 'page_number': 142, 'verdict': 'supporting', 'note': 'continues the e-governance list on 141'},
    *({'requirement': 'AIQIF-C1.4', 'page_number': n, 'verdict': 'supporting', 'note': note}
      for n, note in ((8, 'LMS with Wi-Fi for student use'), (112, 'e-content platforms in use'),
                      (157, 'smart classrooms 46% to 100%'))),
]
SSR = 'NAAC SSR  Latest Self-Study Report.pdf'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sources'); ap.add_argument('map'); ap.add_argument('test13')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    exported = json.load(open(a.sources, encoding='utf-8'))
    filename = {d['document_id']: d['filename'] for d in exported['manifest']}
    text_of = {spec.text_hash(s['text']): s for s in exported['sources'] if (s.get('text') or '').strip()}
    gold = gold_pairs(a.test13)
    t13 = json.load(open(a.test13, encoding='utf-8'))
    seen = set()
    pages = {p['page_id']: (doc['filename'], p['number']) for doc in t13['source_manifest'] for p in doc.get('pages') or []}
    for t in t13['assessment']['traces']:
        for w in t.get('source_excerpts') or []:
            if (w.get('id') or w.get('source_id')) in pages:
                seen.add(pages[w.get('id') or w.get('source_id')])
    sentences = {c['id']: c['text'] for i in release()['indicators'] for c in i['conditions']}
    rows, done = [], set()
    for p in json.load(open(a.map, encoding='utf-8'))['pages']:
        source = text_of.get(p['text_hash'])
        if source is None:
            continue
        fn, num = filename.get(source['document_id']) or p.get('filename'), source['page_number']
        for tag in p.get('tags') or []:
            if tag.get('strength') not in ('direct', 'supporting'):
                continue
            for req in tag.get('requirements') or []:
                key = (req, fn, num)
                if key in gold or key in done:
                    continue
                done.add(key)
                text = source['text']
                span = spec.locate(text, tag.get('quote') or '') if tag.get('quote') else None
                start = max(0, (span[0] if span else 0) - 600)
                rows.append({'requirement': req, 'requirement_text': sentences.get(req, ''), 'filename': fn,
                             'page_number': num, 'strength': tag['strength'], 'quote': tag.get('quote'),
                             'reason': tag.get('reason'), 'quote_found': span is not None,
                             'never_seen': (fn, num) not in seen, 'page_excerpt': text[start:start + 1800],
                             'verdict': None, 'note': ''})
    for s in SEED:
        rows.append({**s, 'filename': SSR, 'requirement_text': sentences.get(s['requirement'], ''), 'strength': 'seed',
                     'quote': None, 'reason': None, 'never_seen': True, 'page_excerpt': '', 'seed': True})
    rows.sort(key=lambda r: (r['strength'] != 'seed', r['strength'] != 'direct', not r['never_seen'], r['requirement'],
                             r['filename'], r['page_number']))
    json.dump(rows, open(a.out, 'w'), indent=1, ensure_ascii=False)
    from collections import Counter
    print(len(rows), 'rows to review:', Counter(r['strength'] for r in rows), 'never seen by a judge:',
          sum(r['never_seen'] for r in rows))


if __name__ == '__main__':
    main()
