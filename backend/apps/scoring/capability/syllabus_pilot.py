"""Offline comparison of bounded syllabus companions against A1 lexical packing."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from .engine import release
from .evaluation import select_balanced_context

INDICATOR = 'AIQIF-C3.1'
VERSION = 'syllabus-structure-pilot-1'
COHORT = re.compile(
    r'^\s*\(?\s*Applicable to all the candidates admitted from the academic year\s+'
    r'(20\d{2})\s*[-–]\s*(\d{2}|20\d{2})\s+onwards\s*\)?\s*$',
    re.IGNORECASE,
)
OBJECTIVE = re.compile(r'(?im)^\s*Course Objectives?[^\S\n]*(?::|\n)')
AI = re.compile(r'\b(?:artificial intelligence|machine learning|deep learning|neural networks)\b', re.I)
UNIT = re.compile(r'(?im)^\s*Unit\s*[-–]?\s*(?:[ivx]+|\d+)\b')


def revision(pages):
    """Hash the canonical text coordinate space used by both packet arms."""
    value = sorted((page['page_number'], page['text']) for page in pages)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode('utf-8')).hexdigest()


def edition_index(sources, editions):
    """Validate reviewed, inclusive body-page intervals against frozen source text."""
    by_document = {}
    for source in sources:
        by_document.setdefault(source.get('document_id'), []).append(source)
    index = {}
    for edition in editions:
        document = edition['document_id']
        pages = by_document.get(document, [])
        if revision(pages) != edition['revision']:
            raise ValueError('Edition was reviewed against different canonical document text.')
        by_page = {p['page_number']: p for p in pages}
        first, last = edition['first_body_page'], edition['last_body_page']
        page = edition['declaration_page']
        if len(by_page) != len(pages) or not (page in by_page and page < first <= last <= max(by_page)):
            raise ValueError('Invalid syllabus edition interval or duplicate page.')
        source = by_page[page]
        start, end = edition['start'], edition['end']
        text = edition['quote']
        match = COHORT.fullmatch(text)
        if not (match and 0 <= start < end <= len(source['text']) and source['text'][start:end] == text):
            raise ValueError('Invalid exact cohort declaration.')
        start_year = int(match[1])
        if int(match[2]) != (start_year + 1) % (100 if len(match[2]) == 2 else 10000):
            raise ValueError('Invalid academic year.')
        for body_page in range(page, last + 1):
            key = (document, body_page)
            if key in index:
                raise ValueError('Overlapping syllabus editions.')
            index[key] = (source, start, text, None) if body_page >= first else None
    return index


def compare(sources, editions, budget=18000):
    """The manifest contains structural metadata only. Labels are applied after packing."""
    if not 100 <= budget <= 100000:
        raise ValueError('Choose a budget from 100 to 100000 characters.')
    indicator = next(i for i in release()['indicators'] if i['code'] == INDICATOR)
    index = edition_index(sources, editions)
    link = None

    def seed(rows):
        nonlocal link
        for row in rows:
            source, start, text, _ = row
            companion = index.get((source.get('document_id'), source.get('page_number')))
            objective = OBJECTIVE.search(text)
            if not companion or not objective or len(text) + len(companion[2]) > budget:
                continue
            body = text[objective.end():]
            unit = UNIT.search(body)
            if not unit or not AI.search(body[:unit.start()]):
                continue
            cohort_source, cohort_start, cohort_text, _ = companion
            link = {
                'course': {'source_id': source['id'], 'start': start, 'end': start + len(text)},
                'cohort': {'source_id': cohort_source['id'], 'start': cohort_start,
                           'end': cohort_start + len(cohort_text)},
                'basis': 'reviewed_syllabus_edition',
            }
            return [row, companion]
        return []

    baseline = select_balanced_context(indicator, sources, max_chars=budget)
    structural = select_balanced_context(indicator, sources, max_chars=budget, structural_seed=seed)
    return {'version': VERSION, 'indicator': INDICATOR, 'budget': budget, 'baseline': baseline,
            'structural': structural, 'link': link}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay-inputs', type=Path, required=True)
    parser.add_argument('--editions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget', type=int, default=18000)
    args = parser.parse_args()
    if Path(__file__).resolve().parents[4] in args.output.resolve().parents:
        parser.error('Write private packet text outside the repository.')
    with args.output.open('x', encoding='utf-8') as handle:
        replay = json.loads(args.replay_inputs.read_text(encoding='utf-8'))['replay_inputs']
        editions = json.loads(args.editions.read_text(encoding='utf-8'))
        json.dump(compare(replay['sources'], editions, args.budget), handle, indent=2)


if __name__ == '__main__':
    main()
