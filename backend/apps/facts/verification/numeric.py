"""Is a numeric fact's number actually in the document? Deterministic, and separate from the other results.

The extractor's value and its quote both come from the AI; either can be wrong in the same way (a value
"563856" with a quote "... 2022 23 -: 563856 ." while the page prints 5638.56). So the number is compared with
the cited PAGE TEXT itself, not only with the quote:

    found            the number is printed on the cited page (any grouping: 5,638.56 = 5638.56)
    decimal_missing  the page prints the same digits WITH a decimal point (5638.56 vs 563856) -- invalid
    scale_mismatch   the page prints the number x10 / x100 / x1000 off (a slipped decimal or unit) -- review
    other_page       not on the cited page, but on another page of the same document -- review
    not_found        not on the cited page or anywhere else read in the document -- review
    ambiguous        the value's own separators can't be read without guessing ("5638,56") -- review
    page_unavailable the cited page's text is not stored -- review (nothing can be compared)
    not_applicable   not a number, or a calculated value (checked by its formula instead)

The value is never changed here: the result explains, a person decides. The unit is reported as printed (the
fact's scope / quote, e.g. "INR in lakhs") and never converted.
"""
import re
from decimal import Decimal

from . import normalize

NUMERIC_TYPES = ('number', 'percentage', 'currency')
_UNIT = re.compile(r'\((?:[^()]*?\b(?:in|INR|Rs\.?|₹)\b[^()]*?)\)|\b(?:INR|Rs\.?)\s+in\s+(?:lakhs?|lacs?|crores?|'
                   r'thousands?|millions?)\b', re.I)
SCALES = (Decimal(10), Decimal(100), Decimal(1000))


def unit_as_printed(snapshot, page_text=''):
    """The unit as the source prints it ("(INR in lakhs)"), from the extractor's scope, else the quote, else the
    cited page. Reported only -- never applied to the value."""
    stated = (snapshot.scope or {}).get('unit')
    if stated:
        return str(stated), 'extraction'
    for text, source in ((snapshot.source_snippet or '', 'quote'), (page_text or '', 'page')):
        match = _UNIT.search(text)
        if match:
            return match.group(0).strip('() '), source
    return '', ''


def _forms(number):
    """How a number may be printed: 5638.56; 563856 -> 563856, 563,856, 5,63,856."""
    number = Decimal(number)
    plain = format(number.normalize(), 'f') if number != number.to_integral() else str(int(number))
    forms = {plain}
    if number == number.to_integral() and abs(number) >= 1000:
        digits = str(abs(int(number)))
        forms.add(f'{int(number):,}')
        head, tail = digits[:-3], digits[-3:]
        indian = ','.join(re.findall(r'\d{1,2}', head[::-1]))[::-1] + ',' + tail if head else tail
        forms.add(indian)
    return forms


def check(snapshot, page_texts, other_pages_with=None):
    """The numeric result for one value + citation.

    page_texts: [text of each cited page] (None entries = not stored). other_pages_with(forms) -> [page numbers
    of the same document that print one of those forms] (optional; used only when the cited page does not)."""
    result = {'kind': 'deterministic', 'status': 'not_applicable', 'source_text': snapshot.value_text or (
        '' if snapshot.value is None else str(snapshot.value)), 'parsed': None, 'unit': '', 'unit_source': '',
        'pages': [], 'detail': ''}
    if snapshot.data_type not in NUMERIC_TYPES:
        return result
    page_text = '\n'.join(t for t in page_texts if t)
    result['unit'], result['unit_source'] = unit_as_printed(snapshot, page_text)
    if snapshot.derivation:
        result['detail'] = 'A calculated value: checked by its formula and cited inputs instead.'
        return result
    issue = normalize.number_issue(snapshot.value_text) or normalize.number_issue(snapshot.value)
    # The number AS PRINTED in the value ("Rs. 42 lakh" -> 42): units are reported, never applied, so it is
    # compared with the page exactly as the page prints it.
    printed = normalize.numbers_in(result['source_text'])
    parsed = printed[0] if len(printed) == 1 else normalize.parse_number(snapshot.value)
    result['parsed'] = None if parsed is None else str(parsed)
    if issue or parsed is None:
        result.update(status='ambiguous', detail=issue or f'{result["source_text"]!r} does not read as one number.')
        return result
    if not page_texts or any(t is None for t in page_texts):
        result.update(status='page_unavailable',
                      detail='The cited page text is not stored, so the number could not be compared with it.')
        return result
    printed = normalize.printed_numbers(page_text)
    shown = normalize.format_number(parsed)
    if any(number == parsed for number, _p in printed):
        result.update(status='found', detail=f'{shown} is printed on the cited page.')
        return result
    digits = normalize.digits_of(format(parsed, 'f').rstrip('0').rstrip('.') if '.' in format(parsed, 'f')
                                 else format(parsed, 'f'))
    dropped = [p for number, p in printed if '.' in p and normalize.digits_of(p) == digits]
    if dropped:
        result.update(status='decimal_missing', page_shows=dropped[0],
                      detail=f'The cited page prints {dropped[0]}, not {shown}: the value has lost its decimal point.')
        return result
    scaled = [p for number, p in printed for k in SCALES
              if number and (parsed == number * k or parsed * k == number)]
    if scaled:
        result.update(status='scale_mismatch', page_shows=scaled[0],
                      detail=f'The cited page prints {scaled[0]}, a power of ten away from {shown} -- a slipped '
                             'decimal point or a different unit?')
        return result
    elsewhere = other_pages_with(_forms(parsed)) if other_pages_with else []
    if elsewhere:
        result.update(status='other_page', pages=elsewhere,
                      detail=f'{shown} is not on the cited page, but is printed on page(s) '
                             f'{", ".join(str(n) for n in elsewhere[:5])} of the same document.')
        return result
    result.update(status='not_found', detail=f'{shown} is not printed on the cited page.')
    return result


#: How each status affects the verification outcome.
INVALID = ('decimal_missing',)
REVIEW = ('scale_mismatch', 'other_page', 'not_found', 'ambiguous', 'page_unavailable')
