"""Source grounding: is the fact's citation real, and does its value come from it? Deterministic code only.

Three questions, answered separately (each result says which):

1. Citation -- does the cited document (the exact version) exist in the fact's sprint, and is the cited page
   inside it? (`document_missing`, `page_missing`, `no_page`)
2. Quote -- is the quoted text on that page? Matched on words and numbers (`normalize.tokens`), so case,
   punctuation, line breaks, ligatures and digit grouping do not matter:
   - `exact`: every word of the quote appears, in order, on the page;
   - `ocr_variant`: no exact run, but a stretch of the page matches the quote's text at least
     QUOTE_MATCH_MIN_RATIO (character similarity), every word of four or more letters has a close counterpart
     there (OCR_WORD_MIN_RATIO), **and every number in the quote appears in that stretch exactly** -- OCR may
     garble letters ("facu1ty", "certificati on"), never the figures a fact rests on;
   - `not_found`: neither -- the quote is not on the cited page (fabricated, or from another page);
   - `unavailable`: the page's text was never stored (e.g. an older upload), so this cannot be checked;
   - `no_quote`: the fact carries no quote.
3. Value -- does the quote state the fact's value? (`value_support`)
   - `in_quote`: the number / words / date of the value are in the quote;
   - `conflicts_quote`: the quote states a *different but nearby* number (extracted 6,909, quote says 6,910) --
     the value contradicts its own evidence;
   - `not_in_quote`: the quote does not state the value at all;
   - `not_checkable`: the value cannot be compared word-for-word (yes/no judgements, long paraphrases).

Nothing here is a probability: `score` on an OCR variant is the share of matching words, reported as such.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from . import normalize

#: Character similarity a stretch of the page must reach for an OCR variant (numbers must match exactly).
QUOTE_MATCH_MIN_RATIO = 0.9
#: Each word of 4+ letters in the quote needs a page word at least this similar (OCR garbles, not other words).
OCR_WORD_MIN_RATIO = 0.75
#: A quote number this close to the value (relative) is read as the same figure misread, not a different one.
NEAR_NUMBER_RELATIVE = 0.02


@dataclass
class Grounding:
    citation: str = ''           # ok | document_missing | page_missing | no_page | wrong_sprint
    quote: str = ''              # exact | ocr_variant | not_found | unavailable | no_quote
    value_support: str = ''      # in_quote | conflicts_quote | not_in_quote | not_checkable
    score: float | None = None   # share of the quote's words matched (OCR variant / not found)
    pages: list = field(default_factory=list)
    document_id: str | None = None
    document_version: int | None = None
    detail: list = field(default_factory=list)
    matched_numbers: list = field(default_factory=list)
    quote_numbers: list = field(default_factory=list)

    @property
    def passed(self):
        """Citation, quote and value all hold up (the parts automation requires)."""
        return self.citation == 'ok' and self.quote in ('exact', 'ocr_variant') and self.value_support == 'in_quote'

    @property
    def status(self):
        """One word for the fact row: the first part that fails, else how the quote matched."""
        if self.citation != 'ok':
            return self.citation
        if self.quote not in ('exact', 'ocr_variant'):
            return self.quote
        if self.value_support in ('conflicts_quote', 'not_in_quote'):
            return f'value_{self.value_support}'
        return self.quote

    def as_dict(self):
        return {'status': self.status, 'citation': self.citation, 'quote': self.quote,
                'value_support': self.value_support, 'score': self.score, 'pages': self.pages,
                'document_id': self.document_id, 'document_version': self.document_version,
                'detail': self.detail, 'quote_numbers': [str(n) for n in self.quote_numbers],
                'kind': 'deterministic'}


def parse_pages(source_page):
    """'12' -> [12]; 'p. 12' -> [12]; '12-13' -> [12, 13]; '12, 14' -> [12, 14]; '' -> []."""
    text = str(source_page or '').lower().replace('pages', '').replace('page', '').replace('pp.', '').replace('p.', '')
    pages = []
    for part in re.split(r'[,;&]|\band\b', text):
        m = re.fullmatch(r'\s*(\d+)\s*(?:[-–to]+\s*(\d+))?\s*', part)
        if not m:
            continue
        start, end = int(m.group(1)), int(m.group(2) or m.group(1))
        if end < start or end - start > 20:
            end = start
        pages.extend(range(start, end + 1))
    return sorted(set(pages))


def page_text(document, page_number, provided=None):
    """The stored text of one page of this document version; `provided` = {page_number: text} read in this run."""
    if provided and page_number in provided:
        return provided[page_number]
    from apps.extraction.models import DocumentPage
    row = DocumentPage.objects.filter(document=document, page_number=page_number).only('text').first()
    return row.text if row and row.text else None


def match_quote(quote, text):
    """('exact' | 'ocr_variant' | 'not_found', score) of `quote` on `text`."""
    q = normalize.tokens(quote)
    p = normalize.tokens(text)
    if not q:
        return 'no_quote', None
    if not p:
        return 'not_found', 0.0
    n = len(q)
    joined_q = ' '.join(q)
    if f' {joined_q} ' in f' {" ".join(p)} ':
        return 'exact', 1.0
    q_numbers = [t for t in q if t[0].isdigit()]
    best = 0.0
    best_window = None
    widths = sorted({max(1, n - 2), max(1, n - 1), n, n + 1, n + 2, n + 3})
    for width in widths:
        for start in range(0, max(1, len(p) - width + 1)):
            window = p[start:start + width]
            matcher = SequenceMatcher(None, joined_q, ' '.join(window), autojunk=False)
            if matcher.real_quick_ratio() <= best or matcher.quick_ratio() <= best:
                continue
            ratio = matcher.ratio()
            if ratio > best:
                best, best_window = ratio, window
    if best >= QUOTE_MATCH_MIN_RATIO and best_window is not None:
        window_numbers = [t for t in best_window if t[0].isdigit()]
        numbers_ok = all(window_numbers.count(num) >= q_numbers.count(num) for num in set(q_numbers))
        if numbers_ok and _words_present(q, best_window):
            return 'ocr_variant', round(best, 3)
    return 'not_found', round(best, 3)


def _words_present(quote_tokens, window):
    """Every quote word of 4+ letters has a close page word (or two adjacent page words joined: "certificati on")."""
    words = [t for t in window if not t[0].isdigit()]
    candidates = words + [a + b for a, b in zip(words, words[1:])]
    for token in quote_tokens:
        if token[0].isdigit() or len(token) < 4:
            continue
        if token in candidates:
            continue
        if not any(SequenceMatcher(None, token, c, autojunk=False).ratio() >= OCR_WORD_MIN_RATIO
                   for c in candidates if abs(len(c) - len(token)) <= 3):
            return False
    return True


def value_support(value, data_type, quote, derivation_ok=False, input_numbers=()):
    """How the quote backs the value (see module docstring). `derivation_ok`: a checked calculation produced
    the value from cited inputs, so the result need not be printed in the quote itself. `input_numbers`: that
    calculation's inputs -- a subtotal printed in the quote is an input, not a misread of the total."""
    if not (quote or '').strip():
        return 'not_in_quote', [], []
    quote_numbers = normalize.numbers_in(quote)
    if data_type in ('number', 'percentage', 'currency'):
        number = normalize.parse_number(value)
        if number is None:
            return 'not_checkable', [], quote_numbers
        # A scaled amount ("1.2 lakh") is printed as its digits.
        printed = {number}
        raw = normalize.numbers_in(value)
        if len(raw) == 1:
            printed.add(raw[0])
        if printed & set(quote_numbers):
            return 'in_quote', sorted(printed & set(quote_numbers)), quote_numbers
        inputs = {normalize.parse_number(n) for n in input_numbers}
        near = [q for q in quote_numbers if q and q not in inputs and _near(number, q)]
        if near:
            return 'conflicts_quote', near, quote_numbers
        if derivation_ok:
            return 'in_quote', [], quote_numbers
        return 'not_in_quote', [], quote_numbers
    if data_type == 'date':
        wanted = normalize.parse_date(value)
        if not wanted or wanted['kind'] == 'invalid':
            return 'not_checkable', [], quote_numbers
        candidates = re.findall(r'\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{1,2}-\d{1,2}|(?:19|20)\d{2}\s*[-/]\s*\d{2,4}'
                                r'|\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|[A-Za-z]{3,9}\.?,?\s+\d{4}|(?:19|20)\d{2}',
                                normalize.clean_text(quote))
        return ('in_quote' if any(normalize.parse_date(c) == wanted for c in candidates) else 'not_in_quote'), [], []
    if data_type == 'boolean':
        return 'not_checkable', [], quote_numbers
    words = normalize.tokens(' '.join(value) if isinstance(value, list) else value)
    if not words or len(words) > 25:
        return 'not_checkable', [], quote_numbers
    qt = normalize.tokens(quote)
    if f' {" ".join(words)} ' in f' {" ".join(qt)} ':
        return 'in_quote', [], quote_numbers
    if isinstance(value, list) and all(f' {" ".join(normalize.tokens(v))} ' in f' {" ".join(qt)} ' for v in value):
        return 'in_quote', [], quote_numbers
    return 'not_in_quote', [], quote_numbers


def _near(a, b):
    if a == b:
        return False
    big = max(abs(a), abs(b))
    return big > 0 and abs(a - b) / big <= NEAR_NUMBER_RELATIVE


def ground(*, sprint_id, document, source_page, snippet, value, data_type, provided_pages=None,
           derivation_ok=False, input_numbers=()):
    """Check one citation (a fact's, a calculation input's, or a submitted correction's)."""
    g = Grounding(pages=parse_pages(source_page))
    if document is None:
        g.citation = 'document_missing'
        g.detail.append('No source document is cited.')
    elif str(document.sprint_id) != str(sprint_id):
        g.citation = 'wrong_sprint'
        g.detail.append('The cited document belongs to another sprint.')
    else:
        g.document_id, g.document_version = str(document.id), document.version_number
        if not g.pages:
            g.citation = 'no_page'
            g.detail.append('No page number is cited.')
        elif document.page_count and any(not 1 <= n <= document.page_count for n in g.pages):
            g.citation = 'page_missing'
            g.detail.append(f'Page {source_page} is outside the document ({document.page_count} pages).')
        else:
            g.citation = 'ok'
    if not (snippet or '').strip():
        g.quote = 'no_quote'
        g.detail.append('No quote from the source is recorded.')
    elif g.citation == 'ok':
        texts = [page_text(document, n, provided_pages) for n in g.pages]
        if any(t is None for t in texts):
            g.quote = 'unavailable'
            g.detail.append('The cited page text is not stored, so the quote could not be checked.')
        else:
            g.quote, g.score = match_quote(snippet, '\n'.join(texts))
            if g.quote == 'not_found':
                g.detail.append(f'The quote is not on page {source_page} of '
                                f'{document.original_filename or "the document"} v{document.version_number}'
                                + (f' (best match {g.score:.0%} of its words).' if g.score else '.'))
            elif g.quote == 'ocr_variant':
                g.detail.append(f'Quote matched with OCR differences ({g.score:.0%} of words; numbers exact).')
    else:
        g.quote = 'unavailable'
    g.value_support, g.matched_numbers, g.quote_numbers = value_support(value, data_type, snippet, derivation_ok,
                                                                        input_numbers)
    if g.value_support == 'conflicts_quote':
        g.detail.append(f'The value {normalize.format_number(normalize.parse_number(value))} contradicts its own quote, '
                        f'which says {", ".join(normalize.format_number(n) for n in g.matched_numbers)}.')
    elif g.value_support == 'not_in_quote':
        g.detail.append('The quote does not state this value.')
    return g
