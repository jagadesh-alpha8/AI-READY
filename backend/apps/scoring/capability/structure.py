"""Document structure for retrieval: NAAC metric sections, duplicate pages and indicator routing.

Deterministic and local: no model calls. Nothing here changes source text or decides credit.
Structure only changes which exact source windows retrieval considers first:

* `sections` reads NAAC metric headings ("6.2.3" on its own line, or followed by its title, or
  opening a rendered table) and carries each metric across page breaks until the next heading.
* `deduplicate` drops pages whose text is identical to a page already kept, so copies of one file
  do not take packet space twice. Pages with any different text are kept.
* `routed_spans` returns the spans of sections whose metric title matches an indicator's route.
  Retrieval boosts query matches inside them; a route never adds text that does not match a query.
* `repeats` (repeat skipping) tells keyword selection to pass over a window that mostly repeats a window
  already chosen from a different document (an AQAR or annexure restating the SSR), so the space goes to
  the next-ranked window instead. Copies inside one document are not skipped.
"""
import hashlib
import re
from collections import Counter
from dataclasses import dataclass

VERSION = 'naac-metric-routing-v1'
DEDUPLICATE_VERSION = 'exact-page-text-v1'
REPEAT_SKIP_VERSION = 'cross-document-repeat-v1'
REPEAT_SKIP_THRESHOLD = 0.5   # share of distinct words two windows have in common (Jaccard)

_METRIC = r'[1-7]\.\d{1,2}\.\d{1,2}(?:\.\d{1,2})?'
HEADING = re.compile(r'^[ \t]*(' + _METRIC + r')(?:[ \t]*$|[ \t]+(?=[A-Z(]))', re.M)
TABLE_HEADING = re.compile(r'^\[Table \d+(?: on page \d+)? -- columns: (' + _METRIC + r')\b', re.M)
ANNEXURE = re.compile(r'^[ \t]*(?:\d+\.\s*)?ANNEXURE\b', re.M)
RESPONSE = re.compile(r'^\s*Response\s*:', re.M)
FOOTER = re.compile(r'^\s*Page \d+/\d+.*$', re.M)


@dataclass(frozen=True)
class Section:
    document_id: str
    metric: str          # three-level NAAC metric, e.g. "6.2.3", or "annexure"
    title: str
    start_page: int


def _key(metric):
    return tuple(int(part) for part in metric.split('.'))


def _title(text, end, following=''):
    """The metric question: text after the number up to "Response:" (or 240 characters).

    A heading near the foot of a page continues on the next page; page footers are skipped."""
    tail = FOOTER.sub('', text[end:] + '\n' + following)[:600]
    stop = RESPONSE.search(tail)
    return re.sub(r'\s+', ' ', tail[:stop.start()] if stop else tail[:240]).strip()[:240]


def sections(sources):
    """Map each source id to [(start, end, Section)] covering its text, in order.

    Headings must be non-decreasing within a document: a metric number that goes backwards (a
    reference in a later table, such as the DVV deviation annexure) does not open a section.
    Text before the first heading belongs to no section.
    """
    by_document = {}
    for source in sources:
        by_document.setdefault(_document(source), []).append(source)
    result = {}
    for document_id, pages in by_document.items():
        pages = sorted(pages, key=lambda s: s.get('page_number') or 0)
        current, last = None, ()
        for position, source in enumerate(pages):
            text = source['text']
            following = pages[position + 1]['text'][:600] if position + 1 < len(pages) else ''
            marks = [(m.start(), m.group(1), m.end()) for m in HEADING.finditer(text)]
            marks += [(m.start(), m.group(1), m.end()) for m in TABLE_HEADING.finditer(text)]
            marks += [(m.start(), 'annexure', m.end()) for m in ANNEXURE.finditer(text)]
            spans, cursor = [], 0
            for start, number, end in sorted(marks):
                if number == 'annexure':
                    opened = Section(document_id, 'annexure', _title(text, end, following), source.get('page_number') or 0)
                else:
                    metric = '.'.join(number.split('.')[:3])
                    if current is not None and current.metric == 'annexure':
                        continue
                    if _key(metric) < last:
                        continue
                    if current is not None and current.metric == metric:
                        continue
                    last = _key(metric)
                    opened = Section(document_id, metric, _title(text, end, following), source.get('page_number') or 0)
                if current is not None and start > cursor:
                    spans.append((cursor, start, current))
                current, cursor = opened, start
            if current is not None and cursor < len(text):
                spans.append((cursor, len(text), current))
            result[source['id']] = spans
    return result


def _normal(text):
    return re.sub(r'\s+', ' ', text).strip().lower()


def _document(source):
    return source.get('document_id') or source['id']


def deduplicate(sources):
    """Keep one page per exact text (whitespace and case ignored); report what was dropped.

    The copy kept is the one in the document with the most pages (an extract repeats pages of the full
    report, not the reverse), then by document id and page number, so the choice does not depend on input
    order. A dropped page's text is identical to the kept page, so any quotation stays citable.
    """
    sizes = Counter(_document(s) for s in sources)
    kept, dropped, seen = [], [], {}
    for source in sorted(sources, key=lambda s: (-sizes[_document(s)], _document(s), s.get('page_number') or 0)):
        body = _normal(source['text'])
        fingerprint = hashlib.sha256(body.encode()).hexdigest()
        if body and fingerprint in seen:
            kept_source = seen[fingerprint]
            dropped.append({'id': source['id'], 'duplicate_of': kept_source['id'],
                            'page': (_document(source), source.get('page_number')),
                            'kept_page': (_document(kept_source), kept_source.get('page_number'))})
            continue
        seen.setdefault(fingerprint, source)
        kept.append(source)
    order = {s['id']: n for n, s in enumerate(sources)}
    return sorted(kept, key=lambda s: order[s['id']]), dropped


# Indicator routes over NAAC metric titles (case-insensitive). Titles, not numbers, because metric
# numbering differs between the university, autonomous and affiliated-college manuals and AQARs.
# A route only boosts windows that already match an indicator query; keep routes specific.
ROUTES = {
    'AIQIF-C1.1': r'strategic plan|perspective plan|institutional development plan|strategy development|vision and mission|e-governance',
    'AIQIF-C1.2': r'governance|leadership|decentrali[sz]ation|participative management|organ[io]gram|statutory bod',
    'AIQIF-C1.3': r'expenditure|budget|financial|funds?\b|grants?\b|seed money|resource mobili[sz]ation|innovation|ecosystem',
    'AIQIF-C1.4': r'e-governance|ict|learning management|e-content|maintaining physical|maintenance|computer',
    'AIQIF-C2.1': r'code of conduct|ethic|policy|policies',
    'AIQIF-C2.2': r'e-governance|it policy|it facilit|policy|policies|grievance',
    'AIQIF-C2.3': r'e-governance|it facilit|erp|software',
    'AIQIF-C2.4': r'grievance|redressal|appeal|code of conduct',
    'AIQIF-C3.1': r'curricul|syllabus|syllabi|programmes? offered|courses?\b|board of studies|value[- ]added',
    'AIQIF-C3.2': r'value[- ]added|courses?\b|cross[- ]cutting|interdisciplinary|mooc|swayam|nptel|e-content',
    'AIQIF-C3.3': r'student[- ]centric|experiential|participative learning|ict|teaching[- ]learning|e-content|examination|evaluation',
    'AIQIF-C3.4': r'projects?\b|internships?|field work|experiential|innovation',
    'AIQIF-C4.1': r'professional development|faculty development|training programmes?|refresher|orientation|teachers?\b',
    'AIQIF-C4.2': r'professional development|faculty development|training programmes?|refresher|orientation|teachers?\b|e-content',
    'AIQIF-C4.3': r'teachers?\b|research|e-content|ict|publications?',
    'AIQIF-C4.4': r'non[- ]teaching|administrative staff|professional development|training programmes?|welfare',
    'AIQIF-C5.1': r'value[- ]added|courses?\b|capacity (?:building|development)|skill|ict',
    'AIQIF-C5.2': r'value[- ]added|certificate|courses?\b|skill|programmes?',
    'AIQIF-C5.3': r'projects?\b|internships?|field work|competitions?|awards?|hackathon|innovation',
    'AIQIF-C5.4': r'placement|internships?|career|progression|employab|competitive examinations',
    'AIQIF-C6.1': r'it facilit|it infrastructure|computers?\b|bandwidth|internet|library|e-resources|ict|laborator|infrastructure|maintain',
    'AIQIF-C6.2': r'e-governance|database|erp|library automation|it facilit|data',
    'AIQIF-C6.3': r'it policy|it facilit|security|backup|maintain|maintenance',
    'AIQIF-C6.4': r'ict|laborator|e-content|learning management|infrastructure|divyangjan|disabled|accessib|it facilit|library|e-resources',
    'AIQIF-C7.1': r'research|projects?\b|grants?\b|publications?|seed money|patents?|consultancy|innovation',
    'AIQIF-C7.2': r'innovation|incubation|start[- ]?ups?|ecosystem|entrepreneur|ipr\b',
    'AIQIF-C7.3': r'innovation|incubation|start[- ]?ups?|ipr\b|patents?|seed money|grants?\b|funding|entrepreneur',
    'AIQIF-C7.4': r'collaborat|mou|linkages?|extension|outreach|consultancy|community',
    'AIQIF-C8.1': r'e-governance|erp|administrat|automation|admission|examination|it facilit|maintain|maintenance|grievance|efficien',
    'AIQIF-C8.2': r'collaborat|mou|industry|linkages?|internships?|curricul|consultancy',
    'AIQIF-C8.3': r'placement|progression|start[- ]?ups?|entrepreneur|career|employab|incubation',
    'AIQIF-C8.4': r'outcomes?\b|attainment|best practices?|impact|pass percentage|feedback',
    'AIQIF-C9.1': r'iqac|academic audit|quality|audit|feedback|best practices?',
    'AIQIF-C9.2': r'iqac|audit|quality|deviation|dvv|annexure',
    'AIQIF-C9.3': r'curricul|syllabus|syllabi|board of studies|revision|iqac|feedback|quality|accreditation',
    'AIQIF-C9.4': r'feedback|survey|satisfaction|iqac|grievance|ict',
}
_COMPILED = {code: re.compile(pattern, re.I) for code, pattern in ROUTES.items()}


def page_aliases(structure):
    """{(document_id, page) kept: [(document_id, page) of each identical dropped page]}.

    Reviewed claims are recorded against the page they were extracted from; a claim on a dropped copy
    still attaches to the identical kept page that the packet shows."""
    aliases = {}
    for row in (structure or {}).get('dropped', []):
        aliases.setdefault(tuple(row['kept_page']), []).append(tuple(row['page']))
    return aliases


def routed(section, indicator_code):
    pattern = _COMPILED.get(indicator_code)
    if pattern is None:
        return False
    if section.metric == 'annexure':
        return bool(pattern.search('annexure ' + section.title))
    return bool(pattern.search(section.title))


def routed_spans(structure, indicator_code):
    """{source id: [(start, end)]} of sections routed to this indicator."""
    return {sid: [(a, b) for a, b, section in spans if routed(section, indicator_code)]
            for sid, spans in structure.items()
            if any(routed(section, indicator_code) for _, _, section in spans)}


def words(text):
    """Distinct words of three or more letters or digits, for repeat skipping."""
    return frozenset(re.findall(r'[a-z0-9]{3,}', text.lower()))


def repeats(candidate, document_id, kept):
    """True if `candidate` (a word set) shares more than REPEAT_SKIP_THRESHOLD of its words with a kept
    window from a different document. `kept` is a list of (document id, word set)."""
    if not candidate:
        return False
    return any(other != document_id and len(candidate & chosen) > REPEAT_SKIP_THRESHOLD * len(candidate | chosen)
               for other, chosen in kept)


def build(sources, *, deduplicate_pages=True, routing=True, repeat_skip=False):
    """Retrieval structure for a run: optionally duplicate pages removed, then optionally sections.

    With routing off, `sections` is empty, so selection adds no routed picks and applies no document cap.
    With repeat_skip, keyword selection passes over cross-document repeats (see `repeats`).
    """
    kept, dropped = deduplicate(sources) if deduplicate_pages else (list(sources), [])
    return {'version': VERSION, 'routing': routing, 'repeat_skip': repeat_skip, 'sources': kept, 'dropped': dropped,
            'sections': sections(kept) if routing else {}}
