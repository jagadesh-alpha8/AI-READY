"""Offline arithmetic experiment; intentionally unused by production services.

States must already have been adjudicated against the supplied requirements.
This module does not translate findings between methodologies or award badges.
"""
import hashlib
import json
from fractions import Fraction

VERSION = 'independent-component-bounds-0.1'
STATES = frozenset(('met', 'not_met', 'unknown', 'conflicting'))


def component_bounds(requirements, decisions, *, methodology_id):
    """Equal-weight assertion bounds within F/A/O, never a headline score.

    A met assertion contributes [1,1], not_met [0,0], unresolved [0,1].
    No cross-stage prerequisites, guessed weights or implicit exclusions.
    Fractions are serialized as numerator/denominator for exact replay.
    """
    if not isinstance(decisions, dict):
        raise ValueError('Decisions must be an object.')
    try:
        rows = list(requirements)
    except TypeError:
        raise ValueError('Requirements must be iterable.') from None
    if any(not isinstance(r, dict) for r in rows):
        raise ValueError('Each requirement must be an object.')
    ids = [r.get('id') for r in rows]
    if (not isinstance(methodology_id, str) or not methodology_id.strip() or not rows
            or any(not isinstance(i, str) or not i for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('A methodology and unique nonempty requirements are required.')
    if any(r.get('stage') not in ('F', 'A', 'O') for r in rows):
        raise ValueError('Unsupported stage.')
    if set(decisions) - set(ids) or any(not isinstance(s, str) or s not in STATES for s in decisions.values()):
        raise ValueError('Unknown requirement or invalid state; no implicit N/A.')
    result = {}
    for stage in ('F', 'A', 'O'):
        selected = [r for r in rows if r['stage'] == stage]
        if not selected:
            continue
        states = [decisions.get(r['id'], 'unknown') for r in selected]
        lower = Fraction(100 * states.count('met'), len(states))
        upper = Fraction(100 * (len(states) - states.count('not_met')), len(states))
        result[stage] = {
            'lower': str(lower), 'upper': str(upper), 'assertions': len(states),
            'resolved': states.count('met') + states.count('not_met'),
            'unknown': states.count('unknown'), 'conflicting': states.count('conflicting'),
        }
    payload = {'methodology_id': methodology_id, 'requirements': rows,
               'decisions': decisions}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    return {'engine_version': VERSION, 'status': 'experimental_not_active',
            'methodology_id': methodology_id, 'input_hash': digest,
            'components': result, 'headline_score': None,
            'badge_status': 'not_assessed',
            'limitation': 'Equal assertion counts are a sensitivity convention, not calibrated capability weights.'}


def compare_source_export(report):
    """Isolate arithmetic on ORIGINAL wording; never reuse as candidate findings."""
    from .engine import assess, validate_release
    rubric = report['rubric']
    validate_release(rubric)
    records = report['assessment']['records']
    expected = {c['id'] for i in rubric['indicators'] for c in i['conditions']}
    ids = [r['condition_id'] for r in records]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError('A complete unique source decision set is required.')
    decisions = {r['condition_id']: r['state'] for r in records}
    original = assess(decisions, rubric)
    snapshot_hash = hashlib.sha256(json.dumps(rubric, sort_keys=True,
                                            separators=(',', ':')).encode()).hexdigest()
    requirements = [{**c, 'stage': c['level']}
                    for i in rubric['indicators'] for c in i['conditions']]
    alternative = component_bounds(requirements, decisions,
                                   methodology_id='source-wording-arithmetic-only:' + snapshot_hash)
    from .assessment_audit import issue_for, VALIDATION_REASONS
    affected = sorted(r['condition_id'] for r in records
                      if r['state'] == 'unknown' and issue_for(r) in VALIDATION_REASONS)
    optimistic = dict(decisions)
    optimistic.update({cid: 'met' for cid in affected})
    optimistic_source = assess(optimistic, rubric)
    optimistic_components = component_bounds(requirements, optimistic,
                                             methodology_id='source-wording-arithmetic-only:' + snapshot_hash)
    foundations = [c['id'] for i in rubric['indicators'] for c in i['conditions'] if c['level'] == 'F']
    per_indicator = []
    for item, saved in zip(rubric['indicators'], original['indicators']):
        subset = [{**c, 'stage': c['level']} for c in item['conditions']]
        ids = {c['id'] for c in subset}
        local = component_bounds(subset, {k: v for k, v in decisions.items() if k in ids},
                                 methodology_id='source-wording-arithmetic-only:' + snapshot_hash)
        per_indicator.append({'indicator': item['code'],
                              'source_bounds': {'lower': saved['lower'], 'upper': saved['upper']},
                              'independent_components': local['components']})
    return {
        'comparison_version': 'range-replay-0.2',
        'purpose': 'Arithmetic sensitivity only; original wording and decisions unchanged.',
        'run_id': report.get('run_id'),
        'source_rubric_snapshot_hash': snapshot_hash,
        'source_replay_matches_saved': original == report['assessment']['result'],
        'source_bounds': {'lower': original['lower'], 'upper': original['upper']},
        'independent_components': alternative,
        'source_range_diagnostics': {
            'decision_states': {state: sum(value == state for value in decisions.values()) for state in sorted(STATES)},
            'zero_lower_indicators': sum(i['lower'] == 0 for i in original['indicators']),
            'full_width_indicators': sum(i['lower'] == 0 and i['upper'] == 100 for i in original['indicators']),
            'foundation_states': {state: sum(decisions[cid] == state for cid in foundations) for state in sorted(STATES)},
            'negative_decisions': sum(state == 'not_met' for state in decisions.values()),
        },
        'per_indicator_arithmetic': per_indicator,
        'optimistic_validator_counterfactual': {
            'status': 'diagnostic_only_not_evidence_or_a_repaired_assessment',
            'assumption': 'Set every unknown validator-affected finding to met, without asserting that its evidence supports it.',
            'changed_condition_ids': affected,
            'source_bounds': {'lower': optimistic_source['lower'], 'upper': optimistic_source['upper']},
            'independent_components': optimistic_components['components'],
        },
        'candidate_rubric_rescored': False,
        'candidate_retrieval_revalidation_required': True,
        'limitations': [
            'Does not validate source evidence interpretation or retrieval completeness.',
            'Source indicator weights and tier gates are not used in independent components.',
            'Revised requirements need new adjudication; old decisions cannot be relabelled.',
            'Old passage selections targeted old requirements; candidate retrieval needs separate validation.',
        ],
    }
