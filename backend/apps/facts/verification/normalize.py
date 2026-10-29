"""Deterministic normalization for comparing fact values and quotes -- never written back over a fact's value.

Everything here is plain code (no AI): the same input always gives the same output.

- `parse_number(text)`: a number as it may be printed in an Indian higher-education document -- "6,910",
  "50,00,000" (Indian digit grouping), "Rs. 20,000", "₹ 1.2 lakh", "3.5 crore", "77.94%", "(1,234)" ->
  Decimal. None when there is no unambiguous number.
- `numbers_in(text)`: every number printed in a text, as Decimals (OCR digit look-alikes repaired inside
  numeric tokens only).
- `parse_date(text)`: a calendar date or an academic / financial year, as a small dict.
- `tokens(text)`: the words and numbers of a text for quote matching -- case, punctuation, curly quotes,
  ligatures, soft hyphens, words split across lines and digit grouping all ignored.
- `same_value(a, b, data_type)`: whether two stored values say the same thing ("1,234" == 1234,
  "Rs 20,000" == 20000, " Yes " == true).
"""
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

#: Multipliers for Indian amount words ("1.2 lakh" = 120,000).
SCALE_WORDS = {'lakh': Decimal(100_000), 'lakhs': Decimal(100_000), 'lac': Decimal(100_000),
               'lacs': Decimal(100_000), 'crore': Decimal(10_000_000), 'crores': Decimal(10_000_000),
               'cr': Decimal(10_000_000), 'thousand': Decimal(1000), 'million': Decimal(1_000_000)}
CURRENCY_MARKERS = ('rs', 'rs.', 'inr', '₹', 'rupees', 'rupee')

# A number as printed: optional sign, digits with , grouping (Indian or Western), optional decimals.
# Parentheses are not read as negative: "Total students (6,910)" is a note, not a loss.
_NUMBER = re.compile(r'(?<![\d,])[-−]?\d[\d,]*(?:\.\d+)?')
# Inside a token that is mostly digits, OCR reads 0 as O/o, 1 as l/I, 5 as S.
_OCR_DIGIT = str.maketrans({'O': '0', 'o': '0', 'l': '1', 'I': '1', 'S': '5'})
_DIGITISH = re.compile(r'\b[\dOolIS][\dOolIS,.]*\d[\dOolIS,.]*\b|\b\d[\dOolIS,.]*\b')

_QUOTES = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', '−': '-',
                         ' ': ' ', '­': ''})


def clean_text(text):
    """NFKC (ligatures, full-width digits), straight quotes and dashes, no soft hyphens, words that were split
    across a line break joined ("manage-\\nment" -> "management"), single spaces."""
    text = unicodedata.normalize('NFKC', str(text or '')).translate(_QUOTES)
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
    return re.sub(r'\s+', ' ', text).strip()


def _repair_ocr_digits(text):
    """Fix O/l/I/S read inside a token that is otherwise a number ("6,91O" -> "6,910"); words are untouched."""
    def fix(match):
        token = match.group(0)
        digits = sum(ch.isdigit() for ch in token)
        letters = sum(ch in 'OolIS' for ch in token)
        return token.translate(_OCR_DIGIT) if digits and digits >= letters else token
    return _DIGITISH.sub(fix, text)


def _to_decimal(raw):
    raw = raw.strip().rstrip(',').replace('−', '-').replace(',', '')
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def numbers_in(text):
    """Every number printed in `text`, in order, as Decimals ("6,910 students and 234" -> [6910, 234])."""
    text = _repair_ocr_digits(clean_text(text))
    out = []
    for match in _NUMBER.finditer(text):
        number = _to_decimal(match.group(0))
        if number is not None:
            out.append(number)
    return out


def parse_number(value):
    """The single number a value states, with lakh / crore applied; None when it states none or several.

    Numbers and numeric strings both work. A year range ("2022-23") or two numbers is not one number."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = clean_text(value).lower()
    for marker in CURRENCY_MARKERS:
        text = text.replace(marker, ' ')
    text = text.replace('%', ' ').replace('per cent', ' ').replace('percent', ' ')
    found = numbers_in(text)
    if len(found) != 1:
        return None
    number = found[0]
    for word, scale in SCALE_WORDS.items():
        if re.search(rf'\b{word}\b', text):
            number *= scale
            break
    return number


def has_currency_marker(text):
    low = clean_text(text).lower()
    return any(re.search(rf'(^|[^a-z]){re.escape(m)}([^a-z]|$)', low) for m in CURRENCY_MARKERS) or any(
        re.search(rf'\b{w}\b', low) for w in SCALE_WORDS if w not in ('thousand', 'million'))


def has_percent_marker(text):
    low = clean_text(text).lower()
    return '%' in low or 'per cent' in low or 'percent' in low or 'percentage' in low


_MONTHS = {m: i for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct',
                                         'nov', 'dec'], start=1)}
_ACADEMIC_YEAR = re.compile(r'\b((?:19|20)\d{2})\s*[-/–]\s*((?:19|20)?\d{2})\b')


def parse_date(value):
    """{'kind': 'date', 'date': date} | {'kind': 'month', 'year', 'month'} | {'kind': 'year', 'year'} |
    {'kind': 'academic_year', 'start', 'end'}; None when the text is not a date. "2022-23" is an academic year,
    not a subtraction."""
    if value is None or isinstance(value, bool):
        return None
    text = clean_text(value).lower()
    m = re.fullmatch(r'((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})', text)
    if m:
        return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r'(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d{2})', text)
    if m:  # Indian order: day / month / year
        return _date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.fullmatch(r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*\.?,?\s+((?:19|20)\d{2})', text)
    if m and m.group(2) in _MONTHS:
        return _date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))
    m = re.fullmatch(r'([a-z]{3})[a-z]*\.?,?\s+((?:19|20)\d{2})', text)
    if m and m.group(1) in _MONTHS:
        return {'kind': 'month', 'year': int(m.group(2)), 'month': _MONTHS[m.group(1)]}
    m = _ACADEMIC_YEAR.fullmatch(text.replace('ay ', '').replace('fy ', '').strip())
    if m:
        start, end = int(m.group(1)), m.group(2)
        end = int(end) if len(end) == 4 else (start // 100) * 100 + int(end)
        if end == start + 1:
            return {'kind': 'academic_year', 'start': start, 'end': end}
        return {'kind': 'invalid', 'detail': f'{value!r}: an academic year must span two consecutive years.'}
    m = re.fullmatch(r'((?:19|20)\d{2})', text)
    if m:
        return {'kind': 'year', 'year': int(m.group(1))}
    return None


def _date(year, month, day):
    try:
        return {'kind': 'date', 'date': date(year, month, day)}
    except ValueError:
        return {'kind': 'invalid', 'detail': f'{year:04d}-{month:02d}-{day:02d} is not a real date.'}


_LETTERISH = re.compile(r'\b(?=\w*[A-Za-z]\w*[015]|\w*[015]\w*[A-Za-z])[A-Za-z015]{3,}\b')
_OCR_LETTER = str.maketrans({'0': 'o', '1': 'l', '5': 's'})


def _repair_ocr_letters(text):
    """Fix digits read inside a word ("facu1ty" -> "faculty", "instituti0n" -> "institution"); only in tokens
    that are mostly letters, so figures are never touched."""
    def fix(match):
        token = match.group(0)
        letters = sum(ch.isalpha() for ch in token)
        return token.translate(_OCR_LETTER) if letters >= 2 * (len(token) - letters) else token
    return _LETTERISH.sub(fix, text)


def tokens(text):
    """Lower-case words and numbers for quote matching; a grouped number is one token ("6,910" -> "6910")."""
    text = _repair_ocr_letters(_repair_ocr_digits(clean_text(text))).lower()
    text = re.sub(r'(?<=\d),(?=\d)', '', text)  # digit grouping, Indian or Western
    return re.findall(r'\d+(?:\.\d+)?|[a-z]+', text)


_TRUE = {'yes', 'y', 'true', 'available', 'present', 'exists', '1'}
_FALSE = {'no', 'n', 'false', 'not available', 'absent', 'none', '0', 'nil'}


def parse_bool(value):
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower().rstrip('.')
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def comparable_value(value, data_type):
    """A canonical form of a stored value for comparison -- never stored over the value itself."""
    if data_type in ('number', 'percentage', 'currency'):
        number = parse_number(value)
        if number is not None:
            return ('number', number.normalize() if number == number.to_integral() else number)
    if data_type == 'boolean':
        flag = parse_bool(value)
        if flag is not None:
            return ('bool', flag)
    if data_type == 'date':
        parsed = parse_date(value)
        if parsed and parsed['kind'] != 'invalid':
            return ('date', tuple(sorted((k, str(v)) for k, v in parsed.items())))
    if isinstance(value, list):
        return ('list', tuple(sorted(' '.join(tokens(v)) for v in value)))
    return ('text', ' '.join(tokens(value)))


def same_value(a, b, data_type='string'):
    """True when two stored values say the same thing once printing differences are removed."""
    return comparable_value(a, data_type) == comparable_value(b, data_type)


def format_number(number):
    """6910 -> '6,910'; 77.9400 -> '77.94' (for messages)."""
    if number is None:
        return '—'
    number = Decimal(number)
    if number == number.to_integral():
        return f'{int(number):,}'
    return f'{number.normalize():,f}'
