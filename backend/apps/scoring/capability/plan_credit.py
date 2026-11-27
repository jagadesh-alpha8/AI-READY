"""What a college's plan would do to its score, by the same arithmetic as the reports (no model).

A plan action names the parts of a practice it would show once done (plan_mapping's link stage). The projection puts
those parts at "shown in full" and recomputes the practice's credit with the judge's own credit rule
(part_judgment.credit: gates, related credit, the middle step), so a plan that shows only part of a practice earns
part of its credit, as a document would. Credit never falls below what the assessment gave, and credit held for
follow-up answers (reserve.py) is applied the way the reports apply it.

The judge's credit is a mean over two or three passes; a single "view" of the parts is used only for the difference
the plan makes: credit after = baseline credit + (view with the plan - view without it), capped at 1, and exactly 1
when the plan supplies every part the assessment did not show in full in every pass.
"""
from .engine import documented
from .part_judgment import _load as load_parts, credit as part_credit
from .reserve import apply, record_factor

SHOWN, PARTLY, NOT_FOUND = 'shown', 'partly', 'not_found'
PASS_KEYS = ('credited_as', 'second_credited_as', 'third_credited_as')


def spec_parts(condition_id):
    return ((load_parts()[0]['conditions'].get(condition_id) or {}).get('parts')) or []


def credit_of(record):
    if record.get('credit') is not None:
        return float(record['credit'])
    return 1.0 if record.get('state') == 'met' else 0.0


def part_status(record):
    """{part id: 'shown' | 'partly' | 'not_found'}: shown when every pass credited it in full, partly when a pass
    found it in full or as related, else not found."""
    out = {}
    for part in record.get('parts') or []:
        values = [part.get(k) for k in PASS_KEYS if part.get(k) is not None]
        if values and all(v == 'full' for v in values):
            out[part['id']] = SHOWN
        elif any(v in ('full', 'related') for v in values):
            out[part['id']] = PARTLY
        else:
            out[part['id']] = NOT_FOUND
    return out


def _view(statuses, spec, supplied):
    parts = []
    for p in spec:
        state = statuses.get(p['id'], NOT_FOUND)
        if p['id'] in supplied or state == SHOWN:
            parts.append({'id': p['id'], 'credited_as': 'full'})
        elif state == PARTLY:
            parts.append({'id': p['id'], 'credited_as': 'related'})
        else:
            parts.append({'id': p['id'], 'credited_as': 'not_found'})
    return part_credit(parts, spec)


def credit_after(record, supplied):
    """The practice's credit once the plan's parts are shown (never below the assessment's)."""
    base = credit_of(record)
    spec = spec_parts(record['condition_id'])
    if not spec:   # a practice without a part specification: only a plan that shows all of it counts
        return 1.0 if supplied else base
    statuses = part_status(record)
    supplied = {p for p in supplied if p in {s['id'] for s in spec}}
    if not supplied:
        return base
    unshown = {p['id'] for p in spec if statuses.get(p['id']) != SHOWN}
    if unshown and unshown <= supplied:
        return 1.0
    gain = _view(statuses, spec, supplied) - _view(statuses, spec, set())
    return round(min(1.0, max(base, base + gain)), 4)


def score(records, credits, rubric):
    """The headline score for these credits, holding credit for follow-up answers at each practice's own level."""
    held = {cid: record_factor({**records[cid], 'credit': value}) for cid, value in credits.items() if cid in records}
    return documented(apply(credits, held), rubric)['overall']


def project(records, supplies, rubric):
    """(score, {condition id: (before, after)}) once every supplied part is shown.
    supplies: {condition id: set of part ids}."""
    credits = {cid: credit_of(r) for cid, r in records.items()}
    after = dict(credits)
    changed = {}
    for cid, parts in supplies.items():
        record = records.get(cid)
        if record is None:
            continue
        value = credit_after(record, parts)
        if value > credits[cid]:
            after[cid] = value
            changed[cid] = (credits[cid], value)
    return score(records, after, rubric), changed


def unshown_parts(record):
    """The parts of a practice the assessment did not show in full: what a plan would have to supply."""
    statuses = part_status(record)
    return [p for p in spec_parts(record['condition_id']) if statuses.get(p['id']) != SHOWN]


def baseline_score(records, rubric):
    return score(records, {cid: credit_of(r) for cid, r in records.items()}, rubric)
