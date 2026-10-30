"""Requirement-linked actions and sufficient (not cost-optimal) tier scenarios."""
from fractions import Fraction

from .engine import LEVELS, _tier_pass, _totals, assess, number, release


def actions_for(result):
    actions = []
    for item in result['indicators']:
        # Keep prerequisites for each next level visible; no cycles from related-indicator links.
        target = min(3, item['lower_level'] + 1)
        for condition in item['conditions']:
            if LEVELS.index(condition['level']) >= target or condition['state'] == 'met':
                continue
            state = condition['state']
            kind = {'unknown': 'supply_evidence', 'conflicting': 'resolve_contradiction',
                    'not_met': 'develop_capability'}[state]
            actions.append({'id': condition['id'], 'indicator': item['code'], 'type': kind,
                            'requirement': condition['text'],
                            'suggestion': condition['improvement_pattern'] if state == 'not_met'
                            else 'Provide current, scoped evidence for this requirement.' if state == 'unknown'
                            else 'Reconcile the contradictory source evidence for this requirement.',
                            'completion_evidence': condition['completion_evidence'],
                            'status': 'proposed', 'automatic_points': False})
    return actions


def roadmap(decisions, tier_name, rubric=None):
    rubric = rubric or release()
    current = assess(decisions, rubric)
    names = [t['name'] for t in rubric['tiers']]
    target_index = names.index(tier_name)
    tiers = rubric['tiers'][:target_index + 1]
    levels = {i['code']: i['lower_level'] for i in current['indicators']}
    original = dict(levels)

    def sufficient():
        overall, pillars = _totals(rubric, levels)
        return all(_tier_pass(t, overall, pillars, levels) for t in tiers)

    # First mandatory gates, then pillar floors, then overall threshold. At most 108 transitions.
    for tier in tiers:
        for code, required in tier['gates'].items():
            levels[code] = max(levels[code], required)
    floor = max(Fraction(str(t['pillar_floor'])) for t in tiers)
    items = sorted(rubric['indicators'], key=lambda i: (-i['weight_units'], i['code']))
    for _ in range(len(items) * 3 + 1):
        if sufficient():
            break
        _, pillars = _totals(rubric, levels)
        below = {p for p, value in pillars.items() if value < floor}
        candidates = [i for i in items if levels[i['code']] < 3
                      and (not below or i['pillar'] in below)]
        if not candidates:
            break
        levels[candidates[0]['code']] += 1
    requirement_ids, assumptions = [], []
    for item in rubric['indicators']:
        code = item['code']
        if levels[code] <= original[code]:
            continue
        for condition in item['conditions']:
            if LEVELS.index(condition['level']) < levels[code] and decisions.get(condition['id']) != 'met':
                requirement_ids.append(condition['id'])
                assumptions.append({'condition_id': condition['id'], 'current_state': decisions.get(condition['id'], 'unknown'),
                                    'assumed_state': 'met'})
    projected, _ = _totals(rubric, levels)
    baseline, _ = _totals(rubric, original)
    return {'target': tier_name, 'already_demonstrated': sufficient() and not requirement_ids,
            'scenario_sufficient': sufficient(), 'requirement_ids': requirement_ids, 'assumptions': assumptions,
            'projected_minimum': number(projected),
            'conditional_uplift': number(projected - baseline) if current['exact_score'] is not None else None,
            'note': 'A sufficient scenario, not an optimal or guaranteed plan. Unknown requirements need evidence '
                    'before prescribing new capability. All listed requirements must be demonstrated.'}
