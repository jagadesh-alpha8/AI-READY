"""What a fact measures -- reporting period, population, unit, included / excluded categories -- and whether two
facts measure the same thing, so only comparable facts are compared (conflict detection, cross-source checks).

Scope comes from two places, kept apart in the result (`source` per part):
- `deterministic`: read with fixed patterns from the fact's field key / name and its quote ("2022-23", "UG",
  "Department of CSE", "%");
- `extraction`: what the extractor stated in its `scope` (an AI reading -- used only to tell facts *apart*, never
  to treat two facts as the same metric).

`comparable(a, b)` is conservative in the safe direction: two facts are NOT comparable only when a known part
differs (2022-23 vs 2023-24, UG vs PG, a share vs a count). An unknown part never makes facts comparable or
incomparable on its own -- it is reported as unknown, so a genuine disagreement is never hidden by a guess.
"""
import re

from . import normalize

_PERIOD = re.compile(r'\b(?:ay|fy|a\.y\.|f\.y\.)?\s*((?:19|20)\d{2})\s*[-/–]\s*((?:19|20)?\d{2})\b', re.I)
_AS_ON = re.compile(r'\bas\s+(?:on|of)\s+(\d{1,2}[./-]\d{1,2}[./-](?:19|20)\d{2}|[A-Za-z]+\s+(?:19|20)\d{2})', re.I)
_YEAR = re.compile(r'\b(?:in|for|during|year)\s+((?:19|20)\d{2})\b', re.I)

#: Population words -> a canonical population. Order matters: the first match wins.
POPULATIONS = [
    (re.compile(r'\b(ph\.?\s?d|doctoral|research scholars?)\b', re.I), 'doctoral'),
    (re.compile(r'\b(pg|post[- ]?graduate|m\.?\s?tech|mba|mca|m\.?\s?sc|m\.?e\.?)\b', re.I), 'postgraduate'),
    (re.compile(r'\b(ug|under[- ]?graduate|b\.?\s?tech|b\.?\s?e\.?|b\.?\s?sc|bba|bca)\b', re.I), 'undergraduate'),
    (re.compile(r'\b(integrated)\b', re.I), 'integrated'),
    (re.compile(r'\b(diploma)\b', re.I), 'diploma'),
]
_DEPARTMENT = re.compile(r'\b(?:department|dept\.?)\s+of\s+([a-z &]+?)(?:[,.;:)]|\s+(?:has|have|is|are|with|\d)|$)', re.I)


def _period(text):
    m = _PERIOD.search(text)
    if m:
        start, end = int(m.group(1)), m.group(2)
        end = int(end) if len(end) == 4 else (start // 100) * 100 + int(end)
        if end == start + 1:
            return f'{start}-{str(end)[-2:]}'
    m = _AS_ON.search(text)
    if m:
        parsed = normalize.parse_date(m.group(1))
        if parsed and parsed['kind'] == 'date':
            return parsed['date'].isoformat()
        if parsed and parsed['kind'] == 'month':
            return f'{parsed["year"]}-{parsed["month"]:02d}'
    m = _YEAR.search(text)
    return m.group(1) if m else ''


def _population(text):
    found = [name for pattern, name in POPULATIONS if pattern.search(text)]
    dept = _DEPARTMENT.search(text)
    if dept:
        found.append('dept:' + ' '.join(normalize.tokens(dept.group(1))))
    return found


def _unit(data_type, text):
    # From the data type only: a stray % elsewhere in a quote must not split two counts apart.
    if data_type == 'percentage':
        return 'percent'
    if data_type == 'currency':
        return 'currency'
    if data_type == 'number':
        return 'count'
    return data_type or ''


def read_scope(fact, *, stated=None):
    """The scope of one fact: {'period', 'population', 'unit', 'includes', 'excludes', 'sources': {part: source}}.
    `stated` is the extractor's own scope dict (AI), if any -- falls back to fact.scope."""
    stated = stated if stated is not None else (getattr(fact, 'scope', None) or {})
    text = ' '.join(str(x or '') for x in (fact.field_key.replace('_', ' '), fact.field_name, fact.source_snippet))
    period, population = _period(text), _population(text)
    sources = {}
    scope = {'period': period, 'population': population, 'unit': _unit(fact.data_type, f'{fact.source_snippet or ""}'),
             'includes': list(stated.get('includes') or []), 'excludes': list(stated.get('excludes') or [])}
    if period:
        sources['period'] = 'deterministic'
    elif stated.get('period'):
        scope['period'], sources['period'] = str(stated['period']), 'extraction'
    if population:
        sources['population'] = 'deterministic'
    elif stated.get('population'):
        scope['population'] = [str(stated['population']).lower()]
        sources['population'] = 'extraction'
    sources['unit'] = 'deterministic'
    if isinstance(stated.get('unit'), str) and stated['unit'].strip():
        scope['unit'] = ' '.join(stated['unit'].lower().split())
        sources['unit'] = 'extraction'
    if scope['includes'] or scope['excludes']:
        sources['categories'] = stated.get('source', 'extraction')
    scope['sources'] = sources
    return scope


def comparable(a, b):
    """(True, '') when two scopes can describe the same metric; (False, why) when a known part differs.
    Unknown parts (blank on either side) are listed in why only if nothing else differs."""
    diffs = []
    if a.get('period') and b.get('period') and _norm_period(a['period']) != _norm_period(b['period']):
        diffs.append(f'different periods ({a["period"]} vs {b["period"]})')
    pa, pb = set(a.get('population') or []), set(b.get('population') or [])
    if pa and pb and pa != pb:
        diffs.append(f'different populations ({", ".join(sorted(pa))} vs {", ".join(sorted(pb))})')
    if a.get('unit') and b.get('unit') and a['unit'] != b['unit']:
        diffs.append(f'different units ({a["unit"]} vs {b["unit"]})')
    cats = lambda s: ({' '.join(normalize.tokens(i)) for i in s.get('includes') or []},  # noqa: E731
                      {' '.join(normalize.tokens(i)) for i in s.get('excludes') or []})
    (ia, ea), (ib, eb) = cats(a), cats(b)
    if (ia & eb) or (ib & ea):
        diffs.append('one includes a category the other excludes')
    return (False, '; '.join(diffs)) if diffs else (True, '')


def unknown_parts(a, b):
    return [part for part in ('period', 'population') if not a.get(part) or not b.get(part)]


def _norm_period(period):
    return str(period).lower().replace('ay', '').replace('fy', '').replace(' ', '').replace('/', '-')
