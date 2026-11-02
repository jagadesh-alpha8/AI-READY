"""Offline candidate aggregation and proposed gate checks. No live wiring."""
import hashlib
import json
from fractions import Fraction

from .experimental_ladder import component_bounds

VERSION = 'grouped-candidate-bounds-0.1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def evaluate_candidate(candidate, profiles, decisions, *, profile_id, gate_context):
    """Check adjudicated candidate states; no inference, N/A, headline or badges.

    Four overlapping indicator pairs share one experimental budget each. Bounds
    average assertions within each group, then average groups within each stage.
    Profiles are draft evidence routes, not automatic applicability exclusions.
    """
    if candidate.get('version') != 'LADDER-CANDIDATE-0.2' or candidate.get('status') != 'experimental_not_active':
        raise ValueError('Unsupported candidate release.')
    rows = candidate['requirements']
    expected = {f'AIQIF-C{p}.{i}.{s}{n}' for p in range(1, 10) for i in range(1, 5)
                for s in ('F', 'A', 'O') for n in (1, 2)}
    sources = [r['source_condition_id'] for r in rows]
    if len(rows) != 216 or set(sources) != expected:
        raise ValueError('Candidate must map all 216 source requirements exactly once.')
    for row in rows:
        if (row['candidate_id'] != row['source_condition_id'].replace('AIQIF-', 'LADDER02-')
                or row['stage'] != row['source_condition_id'].split('.')[-1][0]
                or not isinstance(row['credit_group'], str) or not row['credit_group']):
            raise ValueError('Invalid candidate identity, stage or credit group.')
    if (profiles.get('version') != 'LADDER-PROFILES-0.1'
            or profiles.get('methodology') != candidate['version']
            or profiles.get('status') != 'experimental_not_active'):
        raise ValueError('Profile release does not match candidate.')
    profile = profiles['profiles'].get(profile_id)
    if not profile or profile.get('calibrated') is not False:
        raise ValueError('Only explicit uncalibrated candidate profiles are supported.')
    required_context = {'scope_verified', 'currency_verified', 'coverage_verified', 'critical_risks'}
    if set(gate_context) != required_context:
        raise ValueError('Gate context must explicitly declare scope, currency, coverage and risks.')
    if any(gate_context[k] is not None and type(gate_context[k]) is not bool
           for k in required_context - {'critical_risks'}):
        raise ValueError('Verification flags must be true, false or null.')
    if gate_context['critical_risks'] not in ('clear', 'open', 'unknown'):
        raise ValueError('Unsupported critical risk status.')
    requirements = [{'id': r['candidate_id'], 'stage': r['stage']} for r in rows]
    # Validates decisions globally before evaluating subsets.
    raw = component_bounds(requirements, decisions, methodology_id=candidate['version'])
    groups = {}
    for group in sorted({r['credit_group'] for r in rows}):
        subset = [{'id': r['candidate_id'], 'stage': r['stage']}
                  for r in rows if r['credit_group'] == group]
        group_ids = {r['id'] for r in subset}
        groups[group] = component_bounds(subset, {k: v for k, v in decisions.items() if k in group_ids},
                                        methodology_id=candidate['version'])['components']
    components = {}
    for stage in ('F', 'A', 'O'):
        parts = [g[stage] for g in groups.values() if stage in g]
        components[stage] = {
            'lower': str(sum((Fraction(g['lower']) for g in parts), Fraction()) / len(parts)),
            'upper': str(sum((Fraction(g['upper']) for g in parts), Fraction()) / len(parts)),
            'credit_groups': len(parts),
        }
    rule = profile['silver_proposal']
    known = {r['id'] for r in requirements}
    all_of, any_of = rule['all_of'], rule['any_of']
    if (not all_of or not any_of or any(not group for group in any_of)
            or set(all_of) - known or any(set(group) - known for group in any_of)):
        raise ValueError('Invalid proposed gate requirement.')
    states = [decisions.get(i, 'unknown') for i in all_of]
    alternative_states = [[decisions.get(i, 'unknown') for i in group] for group in any_of]
    blocked = (any(s == 'not_met' for s in states)
               or any(all(s == 'not_met' for s in group) for group in alternative_states)
               or gate_context['critical_risks'] == 'open'
               or any(gate_context[k] is False for k in required_context - {'critical_risks'}))
    passed = (all(s == 'met' for s in states)
              and all('met' in group for group in alternative_states)
              and gate_context['critical_risks'] == 'clear'
              and all(gate_context[k] is True for k in required_context - {'critical_risks'}))
    return {
        'engine_version': VERSION, 'methodology': candidate['version'],
        'candidate_hash': digest(candidate), 'profile_release_hash': digest(profiles),
        'input_hash': digest({'candidate': candidate, 'profiles': profiles, 'profile_id': profile_id,
                              'decisions': decisions, 'gate_context': gate_context}),
        'profile': profile_id, 'status': 'experimental_not_active',
        'components': components, 'groups': groups, 'assertion_counts': raw['components'],
        'proposed_silver_gate': {
            'status': 'blocked' if blocked else 'satisfied_for_review' if passed else 'unresolved',
            'unresolved_all_of': [i for i in all_of if decisions.get(i, 'unknown') in ('unknown', 'conflicting')],
            'unmet_all_of': [i for i in all_of if decisions.get(i) == 'not_met'],
            'alternative_groups': [{'ids': ids, 'satisfied': any(decisions.get(i) == 'met' for i in ids)} for ids in any_of],
            'context': dict(gate_context),
        },
        'headline_score': None, 'badge_status': 'not_awarded_uncalibrated',
        'limitations': ['Equal group budgets are an experimental convention, not validated weights.',
                        'No causal benefit, institutional reach or sustained impact is inferred from component bounds.',
                        'No task or hypothetical plan changes the verified baseline.'],
    }
