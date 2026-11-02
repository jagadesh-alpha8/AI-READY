"""Pure capability arithmetic. No database, inference, confidence weights or approval gates.

All comparisons use Fraction (including 100/3 boundaries). Rounding is presentation only.
An unresolved assertion permits either outcome. Frozen 0.2 rubrics retain cumulative gates;
0.3 counts supported assertions independently. Related-capability links have no scoring effect.
"""
import hashlib
import json
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

STATES = frozenset({'met', 'not_met', 'unknown', 'conflicting'})
LEVELS = ('F', 'A', 'O')
DEFAULT_METHODOLOGY = 'AIQIF-CAP-0.3'
ENGINE_VERSION = 'capability-engine-0.3.0'
LEGACY_ENGINE_VERSION = 'capability-engine-0.2.0'


@lru_cache(maxsize=1)
def _release_text(version):
    files = {'AIQIF-CAP-0.2': 'rubric_v0_2.json', 'AIQIF-CAP-0.3': 'rubric_v0_3.json'}
    if version not in files:
        raise ValueError('Unsupported capability release.')
    return Path(__file__).with_name(files[version]).read_text()


def release(version=DEFAULT_METHODOLOGY):
    # Return a fresh copy: callers must never mutate the cached release.
    value = json.loads(_release_text(version))
    value['content_hash'] = hashlib.sha256(_release_text(version).encode()).hexdigest()
    validate_release(value)
    return value


def validate_release(rubric):
    """Reject malformed methodology content before it can affect any assessment."""
    items = rubric['indicators']
    codes = {i['code'] for i in items}
    if len(items) != 36 or len(codes) != 36:
        raise ValueError('A capability release must contain 36 unique indicators.')
    if sum(Fraction(str(i['weight_units'])) for i in items) != 1000:
        raise ValueError('Indicator weights must total 1000.')
    independent = rubric.get('aggregation') == 'independent_conditions'
    if rubric.get('aggregation') not in (None, 'independent_conditions'):
        raise ValueError('Unsupported aggregation method.')
    if independent and (rubric.get('engine_version') != ENGINE_VERSION or rubric.get('badge_policy') != 'not_calibrated'):
        raise ValueError('Independent release requires its matching engine and explicit badge policy.')
    pillars, conditions = {}, set()
    for item in items:
        pillars[item['pillar']] = pillars.get(item['pillar'], 0) + 1
        if (item.get('scoring_mode') == 'independent_conditions') != independent:
            raise ValueError('Mixed indicator arithmetic is not supported.')
        if Fraction(str(item['weight_units'])) <= 0:
            raise ValueError('Indicator weights must be positive.')
        expected = {f'{item["code"]}.{level}{n}' for level in LEVELS for n in (1, 2)}
        actual = {c['id'] for c in item['conditions']}
        if len(item['conditions']) != 6 or actual != expected or actual & conditions:
            raise ValueError('Each indicator needs six unique, stable condition IDs.')
        conditions |= actual
        if any(c['level'] not in LEVELS or not c['id'].split('.')[-1].startswith(c['level'])
               for c in item['conditions']):
            raise ValueError('Condition level does not match its ID.')
        if set(item['related_indicators']) - codes:
            raise ValueError('Related indicator does not exist.')
        if item['hard_prerequisites']:
            raise ValueError('Hard prerequisites are not defined in methodology v0.2.')
    if len(pillars) != 9 or any(n != 4 for n in pillars.values()):
        raise ValueError('The framework requires nine pillars, each with four indicators.')
    if independent:
        from .credit_groups import SHARED_GROUPS
        groups, group_counts = {}, {}
        for item in items:
            group = SHARED_GROUPS.get(item['code'], item['code'])
            if item.get('credit_group') != group:
                raise ValueError('Invalid readiness credit group.')
            groups[group] = groups.get(group, Fraction()) + Fraction(str(item['weight_units']))
            group_counts[group] = group_counts.get(group, 0) + 1
        if len(groups) != 32 or any(weight != Fraction(1000, 32) for weight in groups.values()):
            raise ValueError('Readiness groups require exactly one equal shared budget each.')
        if any(Fraction(str(i['weight_units'])) != Fraction(1000, 32 * group_counts[i['credit_group']]) for i in items):
            raise ValueError('Shared group members must split their budget equally.')
    if [t['name'] for t in rubric['tiers']] != ['Silver', 'Gold', 'Platinum']:
        raise ValueError('Expected three ordered institutional tiers.')
    if independent:
        if any(t['threshold'] is not None or t['pillar_floor'] is not None or t['gates'] for t in rubric['tiers']):
            raise ValueError('Uncalibrated readiness release cannot declare numeric badge thresholds.')
        return
    previous_threshold = previous_floor = Fraction(-1)
    for tier in rubric['tiers']:
        threshold, floor = Fraction(str(tier['threshold'])), Fraction(str(tier['pillar_floor']))
        if not (0 <= threshold <= 100 and previous_threshold <= threshold
                and 0 <= floor <= 100 and previous_floor <= floor):
            raise ValueError('Tier thresholds and pillar floors must be ordered and at most 100.')
        if set(tier['gates']) - codes or any(type(v) is not int or v not in (1, 2, 3)
                                             for v in tier['gates'].values()):
            raise ValueError('Invalid tier gate.')
        previous_threshold, previous_floor = threshold, floor


def number(value):
    return float(round(value, 2))


def indicator_bounds(indicator, decisions):
    if indicator.get('scoring_mode') == 'independent_conditions':
        states = [decisions.get(c['id'], 'unknown') for c in indicator['conditions']]
        if any(state not in STATES for state in states):
            raise ValueError('Unsupported condition state.')
        return (Fraction(states.count('met'), 2),
                Fraction(len(states) - states.count('not_met'), 2))
    lower = upper = 0
    for index, level in enumerate(LEVELS, 1):
        required = [c for c in indicator['conditions'] if LEVELS.index(c['level']) < index]
        states = [decisions.get(c['id'], 'unknown') for c in required]
        if any(s not in STATES for s in states):
            raise ValueError('Unsupported condition state; N/A requires a versioned rubric alternative.')
        if all(s == 'met' for s in states):
            lower = index
        if not any(s == 'not_met' for s in states):
            upper = index
    return lower, upper


def _totals(rubric, levels):
    overall, pillars = Fraction(), {}
    for item in rubric['indicators']:
        score = Fraction(100, 3) * Fraction(str(levels[item['code']]))
        weight = Fraction(str(item['weight_units']))
        overall += score * weight / 1000
        total, denominator = pillars.get(item['pillar'], (Fraction(), Fraction()))
        pillars[item['pillar']] = total + score * weight, denominator + weight
    return overall, {key: total / weight for key, (total, weight) in pillars.items()}


def _tier_pass(tier, overall, pillars, levels):
    return (overall >= Fraction(str(tier['threshold']))
            and all(p >= Fraction(str(tier['pillar_floor'])) for p in pillars.values())
            and all(levels[code] >= level for code, level in tier['gates'].items()))


def assess(decisions, rubric=None):
    rubric = rubric or release()
    condition_ids = {c['id'] for i in rubric['indicators'] for c in i['conditions']}
    if set(decisions) - condition_ids:
        raise ValueError('Unknown rubric condition ID.')
    if any(state not in STATES for state in decisions.values()):
        raise ValueError('Invalid condition decision.')
    lo, hi, indicators = {}, {}, []
    coverage = Fraction()
    for item in rubric['indicators']:
        low, high = indicator_bounds(item, decisions)
        code = item['code']
        lo[code], hi[code] = low, high
        if low == high:
            coverage += Fraction(str(item['weight_units'])) / 1000
        indicators.append({
            'code': code, 'name': item['name'], 'pillar': item['pillar'],
            'weight_units': item['weight_units'], 'lower_level': number(low) if rubric.get('aggregation') else low,
            'upper_level': number(high) if rubric.get('aggregation') else high,
            'lower': number(Fraction(100 * low, 3)), 'upper': number(Fraction(100 * high, 3)),
            'resolved': low == high,
            'conditions': [{**c, 'state': decisions.get(c['id'], 'unknown')} for c in item['conditions']],
        })
    lower, p_lower = _totals(rubric, lo)
    upper, p_upper = _totals(rubric, hi)
    if rubric.get('badge_policy') == 'not_calibrated':
        tiers = [{'name': t['name'], 'threshold': None, 'pillar_floor': None, 'gates': {},
                  'eligibility': 'unresolved'} for t in rubric['tiers']]
    else:
        tiers = []
        # Higher tiers inherit every lower tier's rules, even if future gate lists omit them.
        passed_low = passed_high = True
        for tier in rubric['tiers']:
            passed_low = passed_low and _tier_pass(tier, lower, p_lower, lo)
            passed_high = passed_high and _tier_pass(tier, upper, p_upper, hi)
            tiers.append({'name': tier['name'], 'threshold': tier['threshold'],
                          'pillar_floor': str(tier['pillar_floor']), 'gates': tier['gates'],
                          'eligibility': 'demonstrated' if passed_low else 'requirements_unmet' if not passed_high
                          else 'unresolved'})
    demonstrated = [t['name'] for t in tiers if t['eligibility'] == 'demonstrated']
    unresolved = [t for t in tiers if t['eligibility'] == 'unresolved']
    return {
        'engine_version': rubric.get('engine_version', LEGACY_ENGINE_VERSION),
        'methodology': rubric['version'], 'rubric_hash': rubric['content_hash'],
        'methodology_status': rubric['status'], 'lower': number(lower), 'upper': number(upper),
        'exact_score': number(lower) if lower == upper else None,
        'assessment_coverage': number(coverage * 100),
        'condition_decision_coverage': number(Fraction(sum(decisions.get(c) in ('met', 'not_met')
                                                     for c in condition_ids), len(condition_ids)) * 100),
        **({'aggregation': rubric['aggregation'], 'badge_policy': rubric['badge_policy'],
            'scoring_note': rubric['release_note']} if rubric.get('aggregation') == 'independent_conditions' else {}),
        'highest_demonstrated_tier': demonstrated[-1] if demonstrated else None,
        'tier_is_certain': not unresolved, 'tiers': tiers, 'indicators': indicators,
        'pillars': [{'code': key, 'lower': number(p_lower[key]), 'upper': number(p_upper[key])}
                    for key in p_lower],
    }
