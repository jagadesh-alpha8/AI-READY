"""Calculated (derived) facts: values the document does not print in one place, worked out from cited inputs.

A derivation is stored on the fact (`ExtractedFact.derivation`) as:

    {'operation': 'sum' | 'difference' | 'ratio' | 'percentage' | 'product',
     'formula': '6,910 + 234',                       # as written for people
     'inputs': [{'label': 'Students (subtotal)', 'value': '6,910', 'document_id': '...',
                 'document_version': 2, 'source_page': '14', 'source_snippet': 'Sub total 6,910'}, ...],
     'includes': ['integrated programmes'], 'excludes': ['PhD scholars'],
     'source': 'extraction' | 'correction' | 'evidence'}

The arithmetic is recomputed here with exact decimals and compared with the fact's value: PASS or FAIL, with
the formula and inputs -- never a confidence. Every input is grounded on its own page (grounding.ground), and
the categories it includes / excludes must agree with the fact's own scope. A discrepancy is reported, never
fixed: the stored value and each input stay as cited.
"""
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation

from . import grounding, normalize

OPERATIONS = ('sum', 'difference', 'ratio', 'percentage', 'product')
SYMBOL = {'sum': ' + ', 'difference': ' − ', 'product': ' × ', 'ratio': ' ÷ ', 'percentage': ' ÷ '}


def formula_text(operation, numbers):
    text = SYMBOL.get(operation, ' ? ').join(normalize.format_number(n) for n in numbers)
    return f'({text}) × 100' if operation == 'percentage' else text


def compute(operation, numbers):
    """The exact result, or raises ValueError with why it cannot be computed."""
    if operation not in OPERATIONS:
        raise ValueError(f'Unknown operation {operation!r} (allowed: {", ".join(OPERATIONS)}).')
    if len(numbers) < 2 and operation != 'sum':
        raise ValueError('A calculation needs at least two inputs.')
    if not numbers:
        raise ValueError('A calculation needs inputs.')
    try:
        if operation == 'sum':
            return sum(numbers, Decimal(0))
        if operation == 'difference':
            result = numbers[0]
            for n in numbers[1:]:
                result -= n
            return result
        if operation == 'product':
            result = Decimal(1)
            for n in numbers:
                result *= n
            return result
        result = numbers[0]
        for n in numbers[1:]:
            result /= n
        return result * 100 if operation == 'percentage' else result
    except (DivisionByZero, InvalidOperation) as exc:
        raise ValueError('Division by zero in the calculation.') from exc


def _matches(stated, computed):
    """Equal to the precision the stated value is written with (77.9 matches 77.94...; 7,144 must be exact)."""
    exponent = stated.as_tuple().exponent
    places = Decimal(1).scaleb(exponent) if exponent < 0 else Decimal(1)
    return computed.quantize(places, rounding=ROUND_HALF_UP) == stated.quantize(places, rounding=ROUND_HALF_UP)


def check_derivation(derivation, *, value, data_type, sprint_id, fact_scope=None, documents=None,
                     provided_pages=None, default_document=None):
    """{'status': 'pass'|'fail'|'not_applicable', 'formula', 'inputs': [...], 'computed', 'stated', 'detail': [...],
    'kind': 'deterministic'}. `documents` = {document_id: Document} for the inputs' citations; an input without
    a document id is cited in `default_document` (the fact's own document -- extraction cites within it)."""
    if not derivation:
        return {'status': 'not_applicable', 'kind': 'deterministic', 'detail': []}
    detail, inputs, numbers = [], [], []
    operation = derivation.get('operation')
    for raw in derivation.get('inputs') or []:
        number = normalize.parse_number(raw.get('value'))
        document = (documents or {}).get(str(raw.get('document_id'))) if raw.get('document_id') else default_document
        g = grounding.ground(sprint_id=sprint_id, document=document, source_page=raw.get('source_page'),
                             snippet=raw.get('source_snippet'), value=raw.get('value'), data_type='number',
                             provided_pages=(provided_pages or {}).get(str(document.pk)) if document else None)
        inputs.append({'label': raw.get('label', ''), 'value': raw.get('value'),
                       'number': None if number is None else str(number),
                       'document_id': str(document.pk) if document else raw.get('document_id'),
                       'document_name': document.original_filename if document else None,
                       'document_version': document.version_number if document else raw.get('document_version'),
                       'source_page': raw.get('source_page'), 'source_snippet': raw.get('source_snippet'),
                       'grounding': g.as_dict()})
        if number is None:
            detail.append(f'Input {raw.get("label") or "?"} {raw.get("value")!r} is not one number.')
        else:
            numbers.append(number)
        if not g.passed:
            detail.append(f'Input {raw.get("label") or raw.get("value")!r}: '
                          + ('; '.join(g.detail) or f'citation {g.status}.'))
    stated = normalize.parse_number(value)
    result = {'status': 'fail', 'operation': operation, 'inputs': inputs, 'stated': None if stated is None else str(stated),
              'computed': None, 'formula': derivation.get('formula') or '', 'includes': derivation.get('includes') or [],
              'excludes': derivation.get('excludes') or [], 'kind': 'deterministic', 'detail': detail}
    if len(numbers) != len(inputs) or not inputs:
        result['detail'].append('The calculation cannot be checked: not every input is a number.')
        return result
    try:
        computed = compute(operation, numbers)
    except ValueError as exc:
        result['detail'].append(str(exc))
        return result
    result['computed'] = str(computed.normalize() if computed == computed.to_integral() else computed)
    result['formula'] = formula_text(operation, numbers)
    arithmetic_ok = stated is not None and _matches(stated, computed)
    if stated is None:
        result['detail'].append('The fact value is not a number, so the result cannot be compared.')
    elif not arithmetic_ok:
        result['detail'].append(f'Arithmetic FAIL: {result["formula"]} = {normalize.format_number(computed)}, '
                                f'but the fact says {normalize.format_number(stated)}.')
    scope_problem = _scope_mismatch(derivation, fact_scope or {})
    if scope_problem:
        result['detail'].append(scope_problem)
    inputs_ok = all(i['grounding']['citation'] == 'ok' and i['grounding']['quote'] in ('exact', 'ocr_variant')
                    and i['grounding']['value_support'] == 'in_quote' for i in inputs)
    result['arithmetic'] = 'pass' if arithmetic_ok else 'fail'
    result['status'] = 'pass' if arithmetic_ok and inputs_ok and not scope_problem else 'fail'
    return result


def _scope_mismatch(derivation, scope):
    """The calculation must include what the fact says it includes, and leave out what it excludes."""
    norm = lambda items: {' '.join(normalize.tokens(i)) for i in items or [] if str(i).strip()}  # noqa: E731
    d_inc, d_exc = norm(derivation.get('includes')), norm(derivation.get('excludes'))
    f_inc, f_exc = norm(scope.get('includes')), norm(scope.get('excludes'))
    wrongly_in = d_inc & f_exc
    wrongly_out = d_exc & f_inc
    if wrongly_in:
        return f'Scope FAIL: the calculation includes {", ".join(sorted(wrongly_in))}, which the fact excludes.'
    if wrongly_out:
        return f'Scope FAIL: the calculation leaves out {", ".join(sorted(wrongly_out))}, which the fact includes.'
    return ''
