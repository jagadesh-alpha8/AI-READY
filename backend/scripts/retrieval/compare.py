"""Offline retrieval comparison: wide keyword search, the evidence map alone, and the map with semantic search, scored
against test 13's credited evidence (gold v1) and, when given, the reviewed new evidence (gold v2, review_sheet.py).
Uses the product's own packet builder (evaluation._prepare), so the packets are the ones a run would build. No model
calls. The files it reads carry the college's text: keep them outside the repository.

Run from backend/. Recommended (25 Nov): on test 13's exact inputs, which carry the reviewed evidence, so every method
gets the extracted-evidence lane as a run does; the live map's tags join to those pages by page text:
  python scripts/retrieval/compare.py - MAP.json TEST13_EXPORT.json --inputs 48177e22-inputs.json.gz --out results.json
      [--new-gold reviewed.json] [--embedding /path/to/bge-small]
Pages-only (no lane), on a sprint export:
  python scripts/retrieval/compare.py SOURCES.json MAP.json TEST13_EXPORT.json --out results.json
Measured 25 Nov, keyword search at 200,000 on test 13's inputs: 107 of 111 full / 219 of 225 any with the lane,
91 / 196 without it. Sizes: --caps 60000,100000 --keyword-sizes 60000,100000,200000 compares at equal size; every
map cap also gets the same-area band (map_same_area, CAPABILITY_MAP_SAME_AREA).
"""
import argparse, json, os, re, sys, time
from collections import Counter, defaultdict

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ.setdefault('SECRET_KEY', 'x')
os.environ.setdefault('DATABASE_URL', 'sqlite:////tmp/compare.sqlite3')
import django  # noqa: E402
django.setup()

from apps.scoring.capability.engine import release  # noqa: E402
from apps.scoring.capability.evaluation import _prepare  # noqa: E402
from apps.scoring.capability.page_use import _structure  # noqa: E402
from apps.scoring.capability import structure as document_structure  # noqa: E402
from apps.evidence_map import packet, semantic  # noqa: E402


def norm(text):
    return ' '.join((text or '').split()).lower()


def gold_pairs(export_path):
    """{(requirement, filename, page): {'full': bool, 'quotes': [...]}} from test 13's export: pages cited by a part
    credited in full (full) or as related / digital groundwork, or by a requirement with any credit (part)."""
    d = json.load(open(export_path, encoding='utf-8'))
    pages = {p['page_id']: (doc['filename'], p['number']) for doc in d['source_manifest'] for p in doc.get('pages') or []}
    gold = {}
    for r in d['assessment']['records']:
        cid, credit = r['condition_id'], float(r.get('credit') or 0)
        cites = []
        for part in r.get('parts') or []:
            for key, label in (('citations', 'credited_as'), ('second_citations', 'second_credited_as')):
                kind = part.get(label) or part.get('finding')
                if kind in ('full', 'related', 'digital_only'):
                    cites += [(c, kind == 'full') for c in part.get(key) or []]
        if credit > 0:
            cites += [(c, credit >= 1) for c in r.get('citations') or []]
        for c, full in cites:
            key = pages.get(c.get('source_id'))
            if key is None:
                continue
            entry = gold.setdefault((cid,) + key, {'full': False, 'quotes': set(), 'source': 'test13'})
            entry['full'] = entry['full'] or full
            if c.get('quote'):
                entry['quotes'].add(c['quote'])
    return gold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sources'); ap.add_argument('map'); ap.add_argument('test13')
    ap.add_argument('--out', required=True); ap.add_argument('--new-gold')
    ap.add_argument('--embedding', default='/tmp/bge-small')
    ap.add_argument('--inputs', help="A run's frozen inputs (.json.gz): its pages, reviewed evidence, population, "
                                     "period and scope replace SOURCES, and every method gets the evidence lane, as a run does")
    ap.add_argument('--no-lane', action='store_true', help='Leave the evidence lane out (pages-only comparison).')
    ap.add_argument('--caps', default=str(packet.CAP_CHARS),
                    help='Map packet caps to compare, comma-separated (default 60000). Each cap gets the map alone, the '
                         'map with the same-area band (same-area-1) and, with --embedding, both with semantic search.')
    ap.add_argument('--keyword-sizes', default='200000', help='Keyword packet sizes, comma-separated (default 200000).')
    a = ap.parse_args()
    run_inputs = {}
    if a.inputs:
        import gzip
        run_inputs = json.load(gzip.open(a.inputs, 'rt', encoding='utf-8'))['inputs']
        exported = {'sources': run_inputs['sources'], 'manifest': run_inputs['manifest']}
    else:
        exported = json.load(open(a.sources, encoding='utf-8'))
    sources, manifest = exported['sources'], exported['manifest']
    from apps.scoring.capability.reviewed_evidence import LANE_VERSION_2
    reviewed = None if a.no_lane else run_inputs.get('reviewed_evidence')
    lane = None if (a.no_lane or reviewed is None) else LANE_VERSION_2
    filename = {d['document_id']: d['filename'] for d in manifest}
    mp = json.load(open(a.map, encoding='utf-8'))
    pages_map = {p['text_hash']: {'page_type': p['page_type'], 'tags': p['tags']}
                 for p in mp['pages'] if p['status'] == 'tagged'}
    gold = gold_pairs(a.test13)
    if a.new_gold:
        for row in json.load(open(a.new_gold, encoding='utf-8')):
            if row.get('verdict') in ('direct', 'supporting'):
                key = (row['requirement'], row['filename'], row['page_number'])
                entry = gold.setdefault(key, {'full': row['verdict'] == 'direct', 'quotes': set(), 'source': 'reviewed'})
                if row.get('quote'):
                    entry['quotes'].add(row['quote'])
    rubric = release()
    dedup = {'deduplicate': document_structure.DEDUPLICATE_VERSION, 'repeat_skip': document_structure.REPEAT_SKIP_VERSION}
    search = None
    if a.embedding and os.path.isfile(os.path.join(a.embedding, 'tokenizer.json')):
        from django.test.utils import override_settings
        override_settings(CAPABILITY_EMBEDDING_PATH=a.embedding,
                          CAPABILITY_EMBEDDING_MODEL='BAAI/bge-small-en-v1.5').enable()
        search = semantic.configured({})
    policies = {}
    for size in (int(x) for x in a.keyword_sizes.split(',') if x.strip()):
        policies[f'keyword_{size // 1000}k'] = ({'mode': 'bm25', **dedup, 'keyword_chars': size}, None)
    caps = [int(x) for x in a.caps.split(',') if x.strip()]
    for cap in caps:
        suffix = '' if caps == [packet.CAP_CHARS] else f'_{cap // 1000}k'
        for label, same_area in (('map', False), ('map_same_area', True)):
            for sem_label, sem in (('', None), ('_semantic', search)):
                if sem_label and sem is None:
                    continue
                name = label.replace('map', 'map' + sem_label, 1) + suffix
                policies[name] = ({'mode': 'map', **dedup}, {'pages': pages_map, 'cap_chars': cap, 'semantic': sem,
                                                             'same_area': same_area})
    from apps.evidence_map import spec as _spec
    joined = sum(1 for x in sources if _spec.text_hash(x['text'] or '') in pages_map)
    print(f'map tags joined to {joined} of {len(sources)} pages (by page text); tagged pages in the map: {len(pages_map)}',
          flush=True)
    print('evidence lane:', lane, '| reviewed claims:', len((reviewed or {}).get('claims') or []), flush=True)
    results = {'gold': {'full': sum(1 for g in gold.values() if g['full']), 'any': len(gold),
                        'reviewed_new': sum(1 for g in gold.values() if g['source'] == 'reviewed')},
               'map_coverage': mp.get('coverage'), 'methods': {}}
    for name, (policy, evidence_map) in policies.items():
        started = time.time()
        structure = _structure(sources, policy)
        reached_page, reached_quote, chars, per_indicator = set(), set(), 0, {}
        steps = Counter()
        for indicator in rubric['indicators']:
            prepared = _prepare(indicator, sources=sources, semantic_ranker=None, gemini=True, reviewed_evidence=reviewed,
                                population=run_inputs.get('population') or '',
                                reference_period=run_inputs.get('reference_period') or '',
                                scope=run_inputs.get('scope'), structure=structure,
                                judgment='parts', keyword_chars=policy.get('keyword_chars'),
                                evidence_map=evidence_map, lane_version=lane)
            context = prepared['context']
            chars += sum(len(w.get('text') or '') for w in context)
            texts = defaultdict(str)
            for w in context:
                key = (filename.get(w.get('document_id')), w.get('page_number'))
                texts[key] += ' ' + norm(w.get('text'))
            ids = {c['id'] for c in indicator['conditions']}
            got = 0
            for (cid, fn, pg), g in gold.items():
                if cid not in ids or (fn, pg) not in texts:
                    continue
                reached_page.add((cid, fn, pg))
                if not g['quotes'] or any(norm(q)[:120] in texts[(fn, pg)] for q in g['quotes']):
                    reached_quote.add((cid, fn, pg))
                    got += 1
            per_indicator[indicator['code']] = {'chars': sum(len(w.get('text') or '') for w in context),
                                                'gold_reached': got,
                                                'gold': sum(1 for (cid, _, _) in gold if cid in ids)}
        full = {k for k, g in gold.items() if g['full']}
        results['methods'][name] = {
            'full_reached_quote': len(reached_quote & full), 'full_reached_page': len(reached_page & full),
            'any_reached_quote': len(reached_quote), 'any_reached_page': len(reached_page),
            'chars_total': chars, 'seconds': round(time.time() - started, 1),
            'missed_full': sorted(map(list, full - reached_quote))[:60], 'per_indicator': per_indicator}
        print(name, {k: v for k, v in results['methods'][name].items() if k not in ('missed_full', 'per_indicator')},
              flush=True)
    json.dump(results, open(a.out, 'w'), indent=1, default=list)


if __name__ == '__main__':
    main()
