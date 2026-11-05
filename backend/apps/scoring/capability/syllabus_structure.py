"""Recognize explicit programme regulations in canonical syllabus pages."""
import re
from collections import defaultdict

REGULATION = re.compile(r'(?im)\bregulations?\s+(20\d{2})[ \t]*$')
COHORT = re.compile(
    r'(?im)^[ \t]*\(?[ \t]*(?:applicable|effective)\b[^\r\n]{0,100}'
    r'\b(?:admitted|admissions|cohort)\b[^\r\n]{0,100}?\b(20\d{2})'
    r'\s*[-–]\s*(20\d{2}|\d{2})\b[^\r\n]{0,60}$'
)
SECTION_END = re.compile(r'(?im)^[ \t]*(?:appendix|annexure|annex)\b')
NEW_COVER = re.compile(r'(?im)^[ \t]*Effective from the Academic year\b')
ROSTER = re.compile(r'(?im)^[ \t]*LIST OF [^\r\n]*\bCOURSES[ \t]*$')
CREDITS = re.compile(r'[ \t]+(?:\d[ \t]+){2,3}\d[ \t]*$')
OBJECTIVE = re.compile(r'(?im)^[ \t]*Course Objectives?[ \t]*(?::|\n)')
AI = re.compile(r'\b(?:artificial intelligence|machine learning|deep learning|neural networks)\b', re.I)
UNIT = re.compile(r'(?im)^[ \t]*Unit\s*[-–]?\s*(?:[ivx]+|\d+)\b')


def course_companions(sources):
    """Reset at missing pages, appendix headings and any new declaration or regulation."""
    documents = defaultdict(list)
    for source in sources:
        if source.get('document_id') and source.get('page_number'):
            documents[source['document_id']].append(source)
    links = {}
    for pages in documents.values():
        if len({p['page_number'] for p in pages}) != len(pages):
            continue
        previous, companion = 0, None
        for page in sorted(pages, key=lambda p: p['page_number']):
            number, text = page['page_number'], page['text']
            regulations, cohorts = list(REGULATION.finditer(text)), list(COHORT.finditer(text))
            appendix = SECTION_END.search(text)
            if number != previous + 1 or appendix or NEW_COVER.search(text):
                companion = None
            previous = number
            if regulations or cohorts:
                companion = None
                if not appendix and len(regulations) == len(cohorts) == 1:
                    regulation, cohort = regulations[0], cohorts[0]
                    year, end = int(cohort[1]), cohort[2]
                    if (regulation.end() <= cohort.start() and int(regulation[1]) == year
                            and int(end) == (year + 1) % (100 if len(end) == 2 else 10000)):
                        companion = (page, cohort.start(), cohort[0], None)
                continue
            if companion:
                links[page['id']] = companion
    return links


def select_pair(rows, sources, budget):
    links = course_companions(sources)
    rosters = defaultdict(dict)
    for page in sorted(sources, key=lambda p: (p.get('page_number', 0), p['id'])):
        cohort = links.get(page['id'])
        if not cohort:
            continue
        heading = ROSTER.search(page['text'])
        if heading:
            for line in re.finditer(r'(?m)^[ \t]*(?:\|[^:\r\n]+:[ \t]*)?(\S[^\r\n]*?)[ \t]*$', page['text'][heading.end():]):
                title = ' '.join(line[1].casefold().split())
                start = heading.end() + line.start(1)
                rosters[cohort[0]['id']].setdefault(title, (page, start, line[1], None))
    for row in rows:
        source, offset, text, _ = row
        cohort = links.get(source['id'])
        objective = OBJECTIVE.search(text)
        if not cohort or not objective:
            continue
        heading = text[:objective.start()].strip().splitlines()
        title = ' '.join(CREDITS.sub('', heading[-1]).casefold().split()) if heading else ''
        roster = rosters[cohort[0]['id']].get(title)
        if (not roster or roster[0]['page_number'] >= source['page_number']
                or len(text) + len(cohort[2]) + len(roster[2]) > budget):
            continue
        body = text[objective.end():]
        unit = UNIT.search(body)
        if not unit or not AI.search(body[:unit.start()]):
            continue
        linked = {**source, 'syllabus_edition': {
            'declaration_source_id': cohort[0]['id'], 'start': cohort[1],
            'end': cohort[1] + len(cohort[2]),
            'roster_source_id': roster[0]['id'], 'roster_start': roster[1],
            'roster_end': roster[1] + len(roster[2]),
        }}
        return [(linked, offset, text, row[3]), cohort, roster]
    return []
