"""Priority plan: a short, ranked set of actions tied to the single part-credit score (no model calls).

Assumptions (12 Nov 2026, recorded for Harsha in "AI-READY second layer: decisions for Harsha to review"):
- A short ranked plan, not one item per requirement: at most MAX_ACTIONS key indicators and MAX_CONDITIONS
  requirements, enough to reach the next 10-point step of the score the report shows.
- The gap decides the action. Nothing found -> establish it (missing evidence usually means the thing is missing; the
  "if you already do this, upload it" route is the questionnaire's job). Partial credit -> complete it, naming the parts
  not shown. Full credit -> a strength to build on. Sources disagree -> reconcile first (listed, not planned).
- Order follows the rubric's own levels: an activity requirement is planned only once its key indicator has some
  provision credited or planned, an outcome only once it has some activity. Within that, the largest score gain for the
  least effort comes first; completing partial credit counts as less effort than establishing.
- Tiers are provisional score bands on the final score (CAPABILITY_PROVISIONAL_TIERS, default Silver 70, Gold 80,
  Platinum 90), not the rubric's uncalibrated badge policy, which stays untouched.
Projections use the engine's documented() arithmetic, the same as the headline score; they are projections, not
promises, and completing an action changes no score until a reassessment finds the evidence.
"""
from .engine import LEVELS, documented

VERSION = 'priority-plan-0.1'
MAX_ACTIONS = 8          # key indicators in the plan
MAX_CONDITIONS = 24      # requirements in the plan
STEP = 10                # the target is the next multiple of STEP above the current score
EFFORT = {('complete', 'F'): 1, ('complete', 'A'): 1.5, ('complete', 'O'): 2,
          ('establish', 'F'): 2, ('establish', 'A'): 3, ('establish', 'O'): 4}
DEFAULT_TIERS = (('Silver', 70), ('Gold', 80), ('Platinum', 90))


def tiers():
    """[(name, threshold)] from CAPABILITY_PROVISIONAL_TIERS ("Silver:70,Gold:80,Platinum:90"), ascending."""
    from django.conf import settings
    raw = getattr(settings, 'CAPABILITY_PROVISIONAL_TIERS', '') or ''
    parsed = []
    for item in raw.split(','):
        name, _, value = item.partition(':')
        try:
            parsed.append((name.strip(), float(value)))
        except ValueError:
            continue
    parsed = [(n, v) for n, v in parsed if n and 0 < v <= 100]
    return sorted(parsed or DEFAULT_TIERS, key=lambda t: t[1])


def tier_for(score):
    """The provisional tier a score reaches, the next one, and the points to it."""
    bands = tiers()
    reached = [t for t in bands if score >= t[1]]
    ahead = [t for t in bands if score < t[1]]
    return {'current': reached[-1][0] if reached else None,
            'next': ahead[0][0] if ahead else None,
            'next_threshold': ahead[0][1] if ahead else None,
            'points_to_next': round(ahead[0][1] - score, 2) if ahead else 0,
            'thresholds': [{'name': n, 'score': v} for n, v in bands], 'provisional': True,
            'note': 'Provisional score bands on the final score, pending calibration across colleges.'}


def credit_of(record):
    if record.get('credit') is not None:
        return float(record['credit'])
    return 1.0 if record.get('state') == 'met' else 0.0


def gap_of(record):
    """'strength', 'complete', 'establish', 'reconcile' or 'rerun' for one assessment record."""
    from .decision_causes import is_processing
    if is_processing(record):
        return 'rerun'
    if record.get('state') == 'conflicting':
        return 'reconcile'
    credit = credit_of(record)
    if credit >= 1:
        return 'strength'
    return 'complete' if credit > 0 else 'establish'


def missing_parts(record):
    """What a partly credited requirement still has to show: the parts not credited in full."""
    from .part_judgment import _load
    spec = {p['id']: p for p in ((_load()[0]['conditions'].get(record['condition_id']) or {}).get('parts') or [])}
    missing = []
    for part in record.get('parts') or []:
        if part.get('credited_as') == 'full' and part.get('second_credited_as', 'full') == 'full':
            continue
        text = (spec.get(part['id']) or {}).get('full') or ''
        if text:
            missing.append(text)
    return missing


def _score(credits, rubric):
    return documented(credits, rubric)['overall']


def build(rubric, records):
    """The priority plan for one assessment (records from its export or completed event)."""
    conditions = {c['id']: (indicator, c) for indicator in rubric['indicators'] for c in indicator['conditions']}
    order = {cid: n for n, cid in enumerate(conditions)}
    by_id = {r['condition_id']: r for r in records}
    credits = {cid: credit_of(by_id[cid]) if cid in by_id else 0.0 for cid in conditions}
    gaps = {cid: gap_of(by_id[cid]) if cid in by_id else 'establish' for cid in conditions}
    score = _score(credits, rubric)
    target = min(100, (int(score // STEP) + 1) * STEP) if score < 100 else None
    planned, chosen, indicators = dict(credits), [], []

    def eligible(cid):
        indicator, condition = conditions[cid]
        level = LEVELS.index(condition['level'])
        if level == 0:
            return True
        before = LEVELS[level - 1]
        return any(planned[c['id']] > 0 for c in indicator['conditions'] if c['level'] == before)

    def gain_of(cid):
        # The overall score is linear in credits: raising one requirement by d adds d x weight_units / 60
        # (documented(): 100/3 x (sum of credits / 2) x weight / 1000 per key indicator).
        return (1 - min(1.0, credits[cid])) * float(conditions[cid][0]['weight_units']) / 60

    current = score
    while target is not None and current < target and len(chosen) < MAX_CONDITIONS:
        best = None
        for cid in conditions:
            if cid in chosen or gaps[cid] not in ('establish', 'complete') or not eligible(cid):
                continue
            code = conditions[cid][0]['code']
            if len(indicators) >= MAX_ACTIONS and code not in indicators:
                continue
            gain = gain_of(cid)
            if gain <= 0:
                continue
            key = (-gain / EFFORT[(gaps[cid], conditions[cid][1]['level'])], order[cid])
            if best is None or key < best[0]:
                best = (key, cid, gain)
        if best is None:
            break
        _, cid, gain = best
        chosen.append(cid)
        planned[cid] = 1.0
        current += gain
        code = conditions[cid][0]['code']
        if code not in indicators:
            indicators.append(code)

    strengths = [{'condition_id': cid, 'indicator': conditions[cid][0]['code'],
                  'requirement': conditions[cid][1]['text'], 'basis': (by_id[cid].get('citations') or [])[:2]}
                 for cid in conditions if gaps[cid] == 'strength']
    actions = []
    for code in indicators:
        indicator = next(i for i in rubric['indicators'] if i['code'] == code)
        ids = [cid for cid in chosen if conditions[cid][0]['code'] == code]
        gain = sum(gain_of(cid) for cid in ids)
        actions.append({
            'indicator': code, 'name': indicator['name'], 'pillar': indicator.get('pillar'),
            'condition_ids': ids, 'score_gain': round(gain, 2),
            'conditions': [{'condition_id': cid, 'requirement': conditions[cid][1]['text'],
                            'level': conditions[cid][1]['level'], 'gap': gaps[cid], 'credit': credits[cid],
                            'missing_parts': missing_parts(by_id[cid]) if gaps[cid] == 'complete' and cid in by_id else []}
                           for cid in ids],
            'builds_on': [s['condition_id'] for s in strengths
                          if s['indicator'] == code
                          or conditions[s['condition_id']][0].get('pillar') == indicator.get('pillar')][:5]})
    remaining = {}
    for cid, gap in gaps.items():
        if cid in chosen or gap in ('strength',):
            continue
        pillar = conditions[cid][0].get('pillar') or conditions[cid][0]['code']
        remaining.setdefault(pillar, {'pillar': pillar, 'establish': 0, 'complete': 0, 'reconcile': 0, 'rerun': 0})
        remaining[pillar][gap] += 1
    projected = _score(planned, rubric)
    return {'version': VERSION, 'score': round(score, 2), 'tier': tier_for(score), 'target': target,
            'projected_score': round(projected, 2), 'projected_tier': tier_for(projected)['current'],
            'reaches_target': target is not None and projected >= target,
            'actions': actions, 'condition_ids': chosen, 'strengths': strengths,
            'remaining': [remaining[p] for p in sorted(remaining)],
            'note': ('A projection, not a promise: completing an action changes no score until a reassessment finds '
                     'the evidence. Effort weights are assumptions (completing partial credit counts as less effort '
                     'than establishing; provision before activity before outcomes).')}
