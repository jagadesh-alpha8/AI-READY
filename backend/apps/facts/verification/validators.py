"""Type-specific deterministic checks on one fact's value. Pass / fail / warn with the rule in words -- no AI,
no probability. Each validator returns a list of check dicts:

    {'code', 'label', 'status': 'pass'|'fail'|'warn', 'detail', 'kind': 'deterministic'}

`fail` means the value cannot be right as recorded (a negative headcount, a 140% share, 31 February);
`warn` means it may be right but a person must look (a percentage printed without a % sign).

Range rules for particular fields come from settings.FACT_VALIDATION_RANGES ({field_key regex: [min, max]}),
on top of the built-in ones below. Adding a validator: write `def _check_<data_type>(value, fact, ctx)` and add
it to VALIDATORS.
"""
import re
from datetime import date
from decimal import Decimal

from django.conf import settings

from . import normalize

#: Fields that count people or things: whole numbers, never negative.
COUNT_FIELD = re.compile(r'(count|number|no_of|num_|total|students|faculty|staff|teachers|labs|programmes|'
                         r'programs|courses|seats|intake|enrol|admitted|graduates|placed|papers|patents|mous)',
                         re.I)
YEAR_FIELD = re.compile(r'(year|established|founded|since)', re.I)


#: Says what the check is -- the text parses as a number -- so a PASS is never read as "matches the document".
FORMAT_LABEL = 'Readable as a number'


def _unreadable(value, fact):
    """A value that is not one number: ambiguous separators need a person ('warn'); anything else is invalid."""
    issue = normalize.number_issue(getattr(fact, 'value_text', '') or '') or normalize.number_issue(value)
    if issue:
        return [check('number_format', FORMAT_LABEL, 'warn', f'{issue} -- a person must read the document.')]
    return [check('number_format', FORMAT_LABEL, 'fail', f'{value!r} is not one number.')]


def check(code, label, status, detail):
    return {'code': code, 'label': label, 'status': status, 'detail': detail, 'kind': 'deterministic'}


def _ranges(field_key):
    rules = getattr(settings, 'FACT_VALIDATION_RANGES', {}) or {}
    return [(pattern, bounds) for pattern, bounds in rules.items() if re.search(pattern, field_key or '', re.I)]


def _check_number(value, fact, ctx):
    number = normalize.parse_number(value)
    if number is None:
        return _unreadable(value, fact)
    out = [check('number_format', FORMAT_LABEL, 'pass',
                 f'Reads as {normalize.format_number(number)} (format only -- see "Value in the document").')]
    key = f'{fact.field_key} {fact.field_name}'
    if YEAR_FIELD.search(key) and not COUNT_FIELD.search(fact.field_key or ''):
        this_year = date.today().year
        ok = number == number.to_integral() and 1800 <= number <= this_year + 1
        out.append(check('year_range', 'Year range', 'pass' if ok else 'fail',
                         f'A year must be a whole number between 1800 and {this_year + 1}.'))
    elif COUNT_FIELD.search(fact.field_key or ''):
        ok = number >= 0 and number == number.to_integral()
        out.append(check('count_whole', 'Count is a whole number ≥ 0', 'pass' if ok else 'fail',
                         'A count of people or things cannot be negative or fractional.'
                         if not ok else f'{normalize.format_number(number)} is a whole number.'))
    out += _configured_range(number, fact)
    return out


def _check_percentage(value, fact, ctx):
    number = normalize.parse_number(value)
    if number is None:
        return _unreadable(value, fact)
    ok = Decimal(0) <= number <= Decimal(100)
    out = [check('percent_range', 'Percentage between 0 and 100', 'pass' if ok else 'fail',
                 f'{normalize.format_number(number)}% ' + ('is within 0–100.' if ok else 'is outside 0–100.'))]
    quote = fact.source_snippet or ''
    if ok and quote and not normalize.has_percent_marker(quote) and not ctx.get('derivation_ok'):
        out.append(check('percent_unit', 'Unit is a percentage', 'warn',
                         'The quote shows no % sign or "percent": the number may be a count, not a share.'))
    out += _configured_range(number, fact)
    return out


def _check_currency(value, fact, ctx):
    number = normalize.parse_number(value)
    if number is None:
        return _unreadable(value, fact)
    out = [check('amount_positive', 'Amount ≥ 0', 'pass' if number >= 0 else 'fail',
                 f'Reads as ₹{normalize.format_number(number)}.')]
    stored = normalize.parse_number(fact.normalized_value) if fact.normalized_value is not None else None
    if stored is not None and stored != number:
        out.append(check('amount_normalized', 'Stored amount matches the text', 'fail',
                         f'The stored amount {normalize.format_number(stored)} differs from the value as printed '
                         f'({value!r} = {normalize.format_number(number)}).'))
    quote = fact.source_snippet or ''
    if quote and not normalize.has_currency_marker(quote) and not normalize.has_currency_marker(str(value)):
        out.append(check('currency_unit', 'Unit is an amount of money', 'warn',
                         'Neither the value nor the quote names a currency (Rs, ₹, INR, lakh, crore).'))
    out += _configured_range(number, fact)
    return out


def _check_date(value, fact, ctx):
    parsed = normalize.parse_date(value)
    if parsed is None:
        return [check('date_format', 'Date format', 'fail',
                      f'{value!r} is not a date, month, year or academic year (e.g. 2023-08-15, 15/08/2023, 2022-23).')]
    if parsed['kind'] == 'invalid':
        return [check('date_format', 'Date format', 'fail', parsed['detail'])]
    year = parsed.get('year') or parsed.get('start') or parsed['date'].year
    this_year = date.today().year
    out = [check('date_format', 'Date format', 'pass', f'Reads as {parsed["kind"].replace("_", " ")}.')]
    if not 1800 <= year <= this_year + 5:
        out.append(check('date_range', 'Plausible year', 'fail', f'{year} is outside 1800–{this_year + 5}.'))
    elif year > this_year + 1 or (parsed['kind'] == 'date' and parsed['date'] > date(this_year + 1, 12, 31)):
        out.append(check('date_range', 'Plausible year', 'warn', f'{year} is in the future; is it a planned date?'))
    return out


def _check_boolean(value, fact, ctx):
    flag = normalize.parse_bool(value)
    return [check('boolean_format', 'Yes / no value', 'pass' if flag is not None else 'fail',
                  f'Reads as {"yes" if flag else "no"}.' if flag is not None else f'{value!r} is not yes or no.')]


def _check_text(value, fact, ctx):
    text = ' '.join(value) if isinstance(value, list) else str(value or '')
    if not text.strip():
        return [check('not_blank', 'Has a value', 'fail', 'The value is blank.')]
    return [check('not_blank', 'Has a value', 'pass', 'The value is not blank.')]


def _configured_range(number, fact):
    out = []
    for pattern, (low, high) in _ranges(fact.field_key):
        ok = (low is None or number >= Decimal(str(low))) and (high is None or number <= Decimal(str(high)))
        out.append(check('field_range', f'Allowed range for {pattern}', 'pass' if ok else 'fail',
                         f'{normalize.format_number(number)} must be between {low} and {high}.'))
    return out


VALIDATORS = {
    'number': _check_number,
    'percentage': _check_percentage,
    'currency': _check_currency,
    'date': _check_date,
    'boolean': _check_boolean,
    'string': _check_text,
    'list': _check_text,
}


def validate(value, fact, ctx=None):
    """All deterministic checks for the fact's data type; `fact` gives field_key / snippet / normalized_value."""
    if value is None:
        return [check('not_blank', 'Has a value', 'warn', 'The value is recorded as unknown.')]
    return VALIDATORS.get(fact.data_type, _check_text)(value, fact, ctx or {})


def summarize(checks):
    """'fail' if any check fails, else 'warn' if any warns, else 'pass' ('not_applicable' when there are none)."""
    statuses = {c['status'] for c in checks}
    if 'fail' in statuses:
        return 'fail'
    if 'warn' in statuses:
        return 'warn'
    return 'pass' if checks else 'not_applicable'
