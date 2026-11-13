"""Pure conditional arithmetic; no inference, probabilities or baseline edits.

The headline is a part-credit projection (credit_projection): the same documented() arithmetic as the reported score
and the priority plan, so a plan's gain is one number in the same units. The strict met/not-met result and the paired
bounds (64 cases per indicator) are kept beside it for audit only.
"""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import re
from .engine import ENGINE_VERSION, LEGACY_ENGINE_VERSION, STATES, assess, documented, indicator_bounds, number, validate_release

VERSION = 'conditional-scenario-0.3'
RESULT_WORDS = re.compile(r'competenc|measured|demonstrably|sustained|improved|compare.+(?:outcome|benefit)|show.+(?:benefit|improvement)', re.I)


def result_dependent(condition):
    if 'result_evidence_required' in condition:
        return condition['result_evidence_required']
    return condition['level'] == 'O' or condition['id'] in {
        'AIQIF-C3.4.A1', 'AIQIF-C4.1.A1', 'AIQIF-C4.2.A1', 'AIQIF-C4.4.A1',
        'AIQIF-C5.1.A1', 'AIQIF-C5.2.A1', 'AIQIF-C5.3.A1', 'AIQIF-C8.4.A1',
    } or bool(RESULT_WORDS.search(condition['text']))


def validate_overlays(baseline, mappings, rubric):
    """Structural checks do not establish semantic entailment; mappings are hypotheses."""
    conditions = {c['id']: c for i in rubric['indicators'] for c in i['conditions']}
    if set(baseline) != set(conditions) or any(s not in STATES for s in baseline.values()):
        raise ValueError('Scenario requires every frozen baseline decision exactly once.')
    grouped, rejected = {}, []
    for mapping in mappings:
        m = deepcopy(mapping)
        cid = m.get('condition_id')
        issue = None
        if cid not in conditions:
            issue = 'Unknown requirement.'
        elif m.get('state') not in {'met', 'not_met'}:
            issue = 'Only conditional presence or withdrawal can be overlaid.'
        elif m.get('kind') == 'evidence_clarification':
            issue = 'Documentation gathering does not establish capability development.'
        elif m.get('kind') not in {'development', 'withdrawal'}:
            issue = 'Unknown action kind.'
        elif (m['kind'] == 'withdrawal') != (m['state'] == 'not_met'):
            issue = 'Withdrawal removes credit; development requires demonstration.'
        elif m.get('coverage') != 'complete' or m.get('scope_compatible') is not True:
            issue = 'Partial or incompatible coverage receives no automatic stage credit.'
        elif m.get('phase') not in {'implementation', 'results'}:
            issue = 'Explicit implementation/results phase required.'
        elif not isinstance(m.get('assumptions'), list) or not m['assumptions'] or any(not isinstance(a, str) or not a.strip() for a in m['assumptions']):
            issue = 'Explicit completion assumptions required.'
        elif baseline[cid] == 'conflicting':
            issue = 'A plan cannot resolve a baseline contradiction.'
        if issue:
            rejected.append({'mapping': m, 'reason': issue})
            continue
        if m['state'] == 'met' and result_dependent(conditions[cid]):
            m['phase'] = 'results'
        grouped.setdefault(cid, []).append(m)
    accepted = []
    for cid, items in grouped.items():
        if len({m['state'] for m in items}) > 1:
            rejected.extend({'mapping': m, 'reason': 'Contradictory plan actions target the same requirement.'} for m in items)
            continue
        # Each admitted mapping independently covers the complete requirement. A later
        # alternative cannot remove a sufficient delivery-only path or duplicate its credit.
        selected = next((m for m in items if m['phase'] == 'implementation'), items[0])
        accepted.append({**selected, 'action_ids': sorted({m['action_id'] for m in items}),
                         'alternative_mappings': items})
    return accepted, rejected


def paired_delta(baseline, overlay, rubric):
    overall_lo = overall_hi = Fraction()
    pillars = {}
    for indicator in rubric['indicators']:
        conditions = [c['id'] for c in indicator['conditions']]
        unresolved = [c for c in conditions if baseline[c] in {'unknown', 'conflicting'}]
        deltas = []
        for values in product(('not_met', 'met'), repeat=len(unresolved)):
            before = {c: baseline[c] for c in conditions}
            before.update(zip(unresolved, values))
            after = {**before, **{c: v for c, v in overlay.items() if c in conditions}}
            deltas.append(Fraction(100 * (indicator_bounds(indicator, after)[0] - indicator_bounds(indicator, before)[0]), 3))
        low, high = min(deltas), max(deltas)
        weight = Fraction(str(indicator['weight_units']))
        overall_lo += low * weight / 1000
        overall_hi += high * weight / 1000
        lo, hi, denominator = pillars.get(indicator['pillar'], (Fraction(), Fraction(), Fraction()))
        pillars[indicator['pillar']] = lo + low * weight, hi + high * weight, denominator + weight
    return {'lower': number(overall_lo), 'upper': number(overall_hi),
        'pillars': [{'code': p, 'lower': number(lo / w), 'upper': number(hi / w)} for p, (lo, hi, w) in pillars.items()],
        'basis': 'Paired completions under the recorded engine; independent unresolved conditions. Not probabilities or a guaranteed real-world gain.'}


def part_credit_rubric(rubric):
    return rubric.get('aggregation') == 'independent_conditions'


def credit_projection(credits, accepted, rubric, phase):
    """The part-credit score if the accepted actions for this phase are completed and shown: a development mapping
    takes its requirement to full credit (the plan plus what the baseline already shows covers every part); a
    withdrawal takes it to 0."""
    after = dict(credits)
    changed = []
    for m in accepted:
        if phase == 'results' or m['phase'] == 'implementation':
            cid = m['condition_id']
            value = 1.0 if m['state'] == 'met' else 0.0
            if after.get(cid, 0.0) != value:
                changed.append({'condition_id': cid, 'credit_before': credits.get(cid, 0.0), 'credit_after': value})
            after[cid] = value
    before, result = documented(credits, rubric), documented(after, rubric)
    pillars_before = {p['code']: p['score'] for p in before['pillars']}
    return {'score': result['overall'], 'gain': round(result['overall'] - before['overall'], 2),
            'pillars': [{'code': p['code'], 'score': p['score'], 'gain': round(p['score'] - pillars_before[p['code']], 2)}
                        for p in result['pillars']],
            'requirements': changed, 'basis': 'Part-credit score, as reported; assumes the mapped actions are completed and shown.'}


def evaluate_plan(baseline, mappings, rubric, *, engine_version=ENGINE_VERSION, credits=None):
    if engine_version not in {ENGINE_VERSION, LEGACY_ENGINE_VERSION}:
        raise ValueError('Recorded engine version is not supported.')
    validate_release(rubric)
    accepted, rejected = validate_overlays(baseline, mappings, rubric)
    scored = credits is not None and part_credit_rubric(rubric)
    result = {'version': VERSION, 'baseline': assess(baseline, rubric), 'accepted': accepted,
              'rejected': rejected, 'scenarios': {}, 'actual_assessment_changed': False,
              'baseline_score': documented(credits, rubric)['overall'] if scored else None,
              'note': 'If the actions are completed and the listed requirements shown, the recorded method would give these conditional scores. Mapping validity and institutional success are not established by this calculation.'}
    for phase in ('implementation', 'results'):
        overlay = {m['condition_id']: m['state'] for m in accepted if phase == 'results' or m['phase'] == 'implementation'}
        result['scenarios'][phase] = {'result': assess({**baseline, **overlay}, rubric), 'overlay': overlay,
                                    'paired_change': paired_delta(baseline, overlay, rubric),
                                    'score': credit_projection(credits, accepted, rubric, phase) if scored else None}
    return result
