"""Conflict detection that compares like with like, and conflict summaries that never go stale.

- `disagreements(facts)`: groups of a field's facts that measure the same thing (scope.comparable) and state
  different values once printing differences are removed (normalize.same_value). "1,234" vs 1234 is not a
  conflict; 2022-23 vs 2023-24 is not the same metric; the same file's earlier version is history, not a second
  source. A number and a stated bound it satisfies (17224 and "more than 15000") agree (`bounds_agree`). Anything
  left that disagrees IS a conflict -- the AI may add a note, never remove one.
  Rules added 24 Nov 2026 after reading test 13's 40 open conflicts (36 were not real): an answer given as a
  questionnaire option ("A. All of the above") is not a value and is never compared (`option_code`); names agree
  across "&"/"and", dropped "the"/"of" and their initials ("AICTE" = "All India Council for Technical Education",
  `same_statement`); a "?" in front of a number is a misread "≥" (`_interval`). Undated numbers are still
  compared: a person should look at them (test 13's two possible real conflicts include an undated one). Category
  labels still never separate facts on their own: the extractor names them freely ("teaching staff", "faculty"),
  so treating unrelated-looking labels as different measures could hide a real conflict.
- `candidate_rows(facts)`: each candidate as a person needs to see it: value, document and version, page, period,
  population, validation and grounding result.
- `summary(gap)` / `refresh(gap)`: the conflict's description rebuilt from the facts as they are now; called
  whenever a candidate fact changes (review, correction, re-extraction).
"""
import re

from apps.facts.models import ExtractedFact

from . import normalize, scope as scope_mod


def live_facts(facts):
    """Not rejected, and not from a document superseded by a newer version (that version speaks for it)."""
    out = []
    for fact in facts:
        if fact.retired_at is not None or fact.status == ExtractedFact.Status.REJECTED:
            continue
        doc = fact.source_document or fact.document
        if doc is not None and doc.superseded_at is not None:
            continue
        out.append(fact)
    return out


_OPTION = re.compile(r'^\s*\(?[a-e]\s*[.)]\s*(?:all of the above|none of the above|any\s+\w+\s+(?:or\s+(?:more|all)\s+)?of the above|'
                     r'\w+\s+of the above)\s*\.?\s*$', re.I)
_FILLER = {'and', 'the', 'of'}


def option_code(value):
    """True for a questionnaire option given as the answer ("A. All of the above", "(b) any 3 of the above"): it
    names a choice on a form the reader cannot see, so it is not a value to compare."""
    return bool(_OPTION.match(str(value if value is not None else '')))


def _words(value):
    return [w for w in normalize.tokens(str(value if value is not None else '')) if w not in _FILLER]


def _initials(value):
    return ''.join(w[0] for w in _words(value) if w != 'for' and not w.isdigit())


def same_statement(a, b, data_type):
    """True when two values say the same thing: equal once printing differences are removed
    (normalize.same_value), or -- for text -- the same words apart from "&"/"and", "the" and "of", or one is the
    initials of the other ("AICTE" and "All India Council for Technical Education")."""
    if normalize.same_value(a, b, data_type):
        return True
    if normalize.comparable_value(a, data_type)[0] != 'text' or normalize.comparable_value(b, data_type)[0] != 'text':
        return False
    wa, wb = _words(a), _words(b)
    if wa and wa == wb:
        return True
    for short, long in ((wa, b), (wb, a)):
        if len(short) == 1 and len(short[0]) >= 3 and not short[0].isdigit() and short[0] == _initials(long):
            return True
    return False


def distinct_values(facts):
    """The facts' values, one per different statement (same_statement)."""
    distinct = []
    for fact in facts:
        if not any(same_statement(fact.value, other.value, fact.data_type) for other in distinct):
            distinct.append(fact)
    return [f.value for f in distinct]


def disagreements(facts):
    """[[fact, ...], ...]: each a set of comparable facts with more than one distinct value."""
    facts = [f for f in live_facts(facts) if not option_code(f.value)]
    scopes = {f.pk: scope_mod.read_scope(f) for f in facts}
    groups = []
    for fact in facts:
        for group in groups:
            if all(scope_mod.comparable(scopes[fact.pk], scopes[g.pk])[0] for g in group):
                group.append(fact)
                break
        else:
            groups.append([fact])
    out = []
    for group in groups:
        if len(distinct_values(group)) > 1 and not bounds_agree([f.value for f in group],
                                                                misread=misread_allowed(group)):
            out.append(group)
    return out


_BOUND = re.compile(r'(more than|greater than|over|above|exceeding|in excess of|at least|minimum of|not less than|'
                    r'less than|fewer than|below|under|up to|at most|maximum of|not more than|>=|<=|>|<|\u2265|\u2264)'
                    r'\s*([\d][\d,]*(?:\.\d+)?)', re.I)
_MISREAD_AT_LEAST = re.compile(r'^\s*\?\s*(?=\d)')   # "? 50": a "≥" the text layer could not encode
# In Indian PDFs a lost glyph before an amount is far more often the rupee sign than "≥" ("? 2,00,000" is ₹2,00,000).
# So "?" is read as "≥" only for facts that show no sign of being money (misread_allowed); otherwise the "?" is
# dropped and the number compared as stated, which keeps a real money disagreement visible.
_MONEY = re.compile(r'\u20b9|\brs\.?\s*\d|\binr\b|\brupees?\b|\blakhs?\b|\blacs?\b|\bcrores?\b|\bfees?\b|'
                    r'\bamount\b|\bbudget|\bexpenditure|\bspent\b|\bsalar|\bincome\b|\brevenue\b|\bgrants?\b|'
                    r'\bfund|\bcost|\bprice|\bpaid\b|\bpayment|\bscholarship|\bdonation|\bcash\b|\bstipend|'
                    r'\bhonorari|\bremuneration|\bsponsor|\bprize money|\bturnover|\bprofit|\bloan|\bdeposit|'
                    r'\b\d{1,2},\d{2},\d{3}\b', re.I)


def misread_allowed(facts):
    """True when none of the facts looks like money (data type, field name, value or source snippet), so a "?" before
    a number may be read as a lost "≥". One currency-like fact in the group is enough to say no."""
    for fact in facts:
        if getattr(fact, 'data_type', '') == 'currency':
            return False
        text = ' '.join(str(getattr(fact, name, '') or '') for name in ('field_name', 'field_key', 'source_snippet'))
        if _MONEY.search(text.replace('_', ' ')) or _MONEY.search(str(getattr(fact, 'value', '') or '')):
            return False
    return True


_PLAIN = re.compile(r'^\s*([\d][\d,]*(?:\.\d+)?)\s*(?:%|percent)?\s*$', re.I)
_LOWER = ('more than', 'greater than', 'over', 'above', 'exceeding', 'in excess of', '>')
_LOWER_EQ = ('at least', 'minimum of', 'not less than', '>=', '\u2265')
_UPPER = ('less than', 'fewer than', 'below', 'under', '<')


def _interval(value, misread=False):
    """(low, low_inclusive, high, high_inclusive) for a plain number or a stated bound ("more than 15000"),
    None when the value is neither. misread: read a "?" before the number as "≥" (else it is dropped)."""
    from decimal import Decimal
    text = _MISREAD_AT_LEAST.sub('>= ' if misread else '', str(value if value is not None else ''))
    plain = _PLAIN.match(text)
    if plain:
        n = Decimal(plain.group(1).replace(',', ''))
        return n, True, n, True
    match = _BOUND.search(text)
    if not match:
        return None
    op, n = match.group(1).lower(), Decimal(match.group(2).replace(',', ''))
    if op in _LOWER:
        return n, False, None, False
    if op in _LOWER_EQ:
        return n, True, None, False
    if op in _UPPER:
        return None, False, n, False
    return None, False, n, True


def bounds_agree(values, misread=False):
    """True when every value is a number or a stated bound and one number satisfies all of them, as with
    17224 and "more than 15000". Such facts state the same thing at different precision, not a conflict."""
    intervals = [_interval(v, misread) for v in values]
    if any(i is None for i in intervals) or all(i[0] == i[2] and i[0] is not None for i in intervals):
        return False  # not all numeric-or-bound, or only exact numbers (those differ: a real conflict)
    low, low_inc, high, high_inc = None, True, None, True
    for lo, lo_inc, hi, hi_inc in intervals:
        if lo is not None and (low is None or lo > low or (lo == low and not lo_inc)):
            low, low_inc = lo, lo_inc
        if hi is not None and (high is None or hi < high or (hi == high and not hi_inc)):
            high, high_inc = hi, hi_inc
    if low is None or high is None:
        return True
    return low < high or (low == high and low_inc and high_inc)


def comparable_pair(a, b):
    """(compatible, why_not) for two facts of the same field."""
    return scope_mod.comparable(scope_mod.read_scope(a), scope_mod.read_scope(b))


def candidate_row(fact):
    doc = fact.source_document or fact.document
    s = scope_mod.read_scope(fact)
    return {'fact_id': str(fact.id), 'value': fact.value, 'status': fact.status,
            'document_id': str(doc.id) if doc else None,
            'document_name': (doc.original_filename or doc.title) if doc else None,
            'document_version': doc.version_number if doc else None,
            'superseded': bool(doc and doc.superseded_at), 'page': fact.source_page or None,
            'period': s.get('period') or None, 'population': s.get('population') or [], 'unit': s.get('unit'),
            'includes': s.get('includes') or [], 'excludes': s.get('excludes') or [],
            'validation_status': fact.validation_status or None, 'grounding_status': fact.grounding_status or None,
            'verification_status': fact.verification_status or None}


def _where(row):
    parts = [row['document_name'] or 'an unknown document']
    if row.get('document_version'):
        parts[0] += f' v{row["document_version"]}'
    if row.get('page'):
        parts.append(f'page {row["page"]}')
    if row.get('period'):
        parts.append(row['period'])
    return ', '.join(parts)


def summary(gap):
    """The conflict's description from its facts as they are now."""
    from apps.gaps.services import conflict_facts
    facts = [f for f in conflict_facts(gap) if f.sprint_id == gap.sprint_id]
    rows = [candidate_row(f) for f in live_facts(facts)]
    if not rows:
        return 'None of the facts this conflict compared is still in play.'
    field = (gap.source_fact.field_name or gap.source_fact.field_key) if gap.source_fact_id else 'this field'
    values = '; '.join(f'{r["value"]!r} ({_where(r)})' for r in rows)
    distinct = distinct_values(live_facts(facts))
    head = (f'Sources report {len(distinct)} different values for "{field}": ' if len(distinct) > 1
            else f'The sources now agree on "{field}": ')
    return head + values + '.'


def refresh(gap, *, user=None):
    """Rewrite a conflict's description from its live facts (with an event when it changed). Returns True if it
    changed. The detection-time snapshots (conflict_value_a/b) are kept: they are labelled 'at detection'."""
    from apps.gaps.models import GapEvent, GapItem
    if gap.gap_type != GapItem.GapType.CONFLICT:
        return False
    text = summary(gap)
    note = ''
    marker = '\n\nAI-assisted note'
    if marker in (gap.description or ''):
        note = gap.description[gap.description.index(marker):]
    new = text + note
    if new == gap.description:
        return False
    old = gap.description
    gap.description = new
    gap.save(update_fields=['description', 'updated_at'])
    GapEvent.objects.create(gap=gap, action=GapEvent.Action.SUMMARY_REFRESHED, user=user,
                            note='A fact this conflict compares changed.', data={'previous': old[:2000]})
    return True


def refresh_for_field(sprint_id, field_key, *, user=None):
    from apps.gaps.models import GapItem
    changed = 0
    for gap in GapItem.objects.filter(sprint_id=sprint_id, gap_type=GapItem.GapType.CONFLICT,
                                      status__in=GapItem.ACTIVE_STATUSES,
                                      source_fact__field_key__iexact=field_key).select_related(
            'source_fact', 'conflict_fact_b'):
        changed += refresh(gap, user=user)
    return changed
