"""Offline candidate aggregation and proposed gate checks. No live wiring."""
import hashlib
import json
from fractions import Fraction

from .experimental_ladder import component_bounds, STATES

VERSION = 'grouped-candidate-bounds-0.2'
CONTEXT_FLAGS = frozenset(('scope_verified', 'currency_verified', 'coverage_verified',
                           'consequential_ai_use'))
CONTEXT_KEYS = CONTEXT_FLAGS | {'critical_risks'}
SHARED_GROUPS = {
    'AIQIF-C3.2': 'literacy_provision', 'AIQIF-C5.1': 'literacy_provision',
    'AIQIF-C3.4': 'student_ai_projects', 'AIQIF-C5.3': 'student_ai_projects',
    'AIQIF-C6.1': 'learning_compute', 'AIQIF-C6.4': 'learning_compute',
    'AIQIF-C5.4': 'career_pathways', 'AIQIF-C8.3': 'career_pathways',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _validate(candidate, profiles, decisions, profile_id, gate_context):
    if not all(isinstance(v, dict) for v in (candidate, profiles, decisions, gate_context)):
        raise ValueError('Candidate, profiles, decisions and gate context must be objects.')
    if candidate.get('version') != 'LADDER-CANDIDATE-0.3' or candidate.get('status') != 'experimental_not_active':
        raise ValueError('Unsupported candidate release; older findings require new adjudication.')
    rows = candidate.get('requirements')
    expected = {f'AIQIF-C{p}.{i}.{s}{n}' for p in range(1, 10) for i in range(1, 5)
                for s in ('F', 'A', 'O') for n in (1, 2)}
    if not isinstance(rows, list) or len(rows) != 216 or any(not isinstance(r, dict) for r in rows):
        raise ValueError('Candidate must contain 216 requirement objects.')
    sources = [r.get('source_condition_id') for r in rows]
    if any(not isinstance(s, str) for s in sources) or set(sources) != expected:
        raise ValueError('Candidate must map all 216 source requirements exactly once.')
    for row in rows:
        source = row['source_condition_id']
        indicator = source.rsplit('.', 1)[0]
        if (row.get('candidate_id') != source.replace('AIQIF-', 'LADDER03-')
                or row.get('stage') != source.split('.')[-1][0]
                or row.get('indicator') != indicator
                or row.get('credit_group') != SHARED_GROUPS.get(indicator, indicator)
                or row.get('re_adjudication_required') is not True
                or any(not isinstance(row.get(k), str) or not row[k].strip()
                       for k in ('requirement', 'scope_rule', 'period_rule', 'evidence_rule', 'context_rule'))):
            raise ValueError('Invalid candidate identity, assertion, scope or shared credit group.')
    known = {r['candidate_id'] for r in rows}
    if set(decisions) - known or any(not isinstance(v, str) or v not in STATES for v in decisions.values()):
        raise ValueError('Unknown candidate requirement or invalid state; no implicit N/A.')
    if (profiles.get('version') != 'LADDER-PROFILES-0.2'
            or profiles.get('methodology') != candidate['version']
            or profiles.get('status') != 'experimental_not_active'
            or not isinstance(profiles.get('profiles'), dict)
            or not isinstance(profile_id, str)):
        raise ValueError('Profile release does not match candidate.')
    profile = profiles['profiles'].get(profile_id)
    if not isinstance(profile, dict) or profile.get('calibrated') is not False:
        raise ValueError('Only explicit uncalibrated candidate profiles are supported.')
    if set(gate_context) != CONTEXT_KEYS:
        raise ValueError('Gate context must explicitly declare scope, currency, coverage, risks and consequential use.')
    if any(gate_context[k] is not None and type(gate_context[k]) is not bool for k in CONTEXT_FLAGS):
        raise ValueError('Context flags must be true, false or null.')
    if gate_context['critical_risks'] not in ('clear', 'open', 'unknown'):
        raise ValueError('Unsupported critical risk status.')
    rule = profile.get('silver_proposal')
    if not isinstance(rule, dict):
        raise ValueError('Missing proposed Silver rule.')

    def valid_ids(values):
        return (isinstance(values, list) and bool(values)
                and all(isinstance(i, str) and i in known for i in values)
                and len(values) == len(set(values)))

    any_of = rule.get('any_of')
    conditional = rule.get('conditional_all_of')
    declared_context = rule.get('additional_gate_context')
    if (not valid_ids(rule.get('all_of'))
            or not isinstance(any_of, list) or not any_of or not all(valid_ids(g) for g in any_of)
            or not isinstance(conditional, dict) or set(conditional) != {'consequential_ai_use'}
            or not valid_ids(conditional['consequential_ai_use'])
            or not isinstance(declared_context, list)
            or not all(isinstance(k, str) for k in declared_context)
            or len(declared_context) != len(CONTEXT_KEYS) or set(declared_context) != CONTEXT_KEYS):
        raise ValueError('Invalid proposed gate requirements or context contract.')
    return rows, rule


def evaluate_candidate(candidate, profiles, decisions, *, profile_id, gate_context):
    """Evaluate adjudicated candidate states; no inference, N/A, headline or badges.

    Assertions average within each of 32 fixed groups, then groups average within
    F/A/O. Consequential-use uncertainty never waives the proposed oversight gate.
    """
    rows, rule = _validate(candidate, profiles, decisions, profile_id, gate_context)
    requirements = [{'id': r['candidate_id'], 'stage': r['stage']} for r in rows]
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
        parts = [g[stage] for g in groups.values()]
        components[stage] = {
            'lower': str(sum((Fraction(g['lower']) for g in parts), Fraction()) / len(parts)),
            'upper': str(sum((Fraction(g['upper']) for g in parts), Fraction()) / len(parts)),
            'credit_groups': len(parts),
        }
    conditional = rule['conditional_all_of']['consequential_ai_use']
    applies = gate_context['consequential_ai_use']
    all_of = rule['all_of'] + (conditional if applies is True else [])
    states = [decisions.get(i, 'unknown') for i in all_of]
    alternative_states = [[decisions.get(i, 'unknown') for i in group] for group in rule['any_of']]
    verified_flags = CONTEXT_FLAGS - {'consequential_ai_use'}
    blocked = (any(s == 'not_met' for s in states)
               or any(all(s == 'not_met' for s in group) for group in alternative_states)
               or gate_context['critical_risks'] == 'open'
               or any(gate_context[k] is False for k in verified_flags))
    passed = (all(s == 'met' for s in states)
              and all('met' in group for group in alternative_states)
              and gate_context['critical_risks'] == 'clear'
              and applies is not None
              and all(gate_context[k] is True for k in verified_flags))
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
            'alternative_groups': [{'ids': list(ids), 'satisfied': any(decisions.get(i) == 'met' for i in ids)}
                                   for ids in rule['any_of']],
            'conditional_oversight': {'applies': applies, 'ids': list(conditional)},
            'context': dict(gate_context),
        },
        'headline_score': None, 'badge_status': 'not_awarded_uncalibrated',
        'limitations': ['Equal group budgets are an experimental convention, not validated weights.',
                        'No causal benefit, institutional reach or sustained impact is inferred from component bounds.',
                        'No task or hypothetical plan changes the verified baseline.'],
    }
