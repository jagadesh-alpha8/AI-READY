"""Consistency of a part-credit assessment, from its export alone (no model calls).

Within one run (both judging passes are recorded per condition in `pass_credits`):
* pass_agreement: share of conditions whose first two passes' credits differ by less than CREDIT_GAP;
* score_gap: headline score from pass 1 alone versus pass 2 alone;
* area_gap: the largest such gap for one of the nine readiness areas;
* mean_credit_gap: mean absolute difference between the two passes' credits.

Between two runs of the same corpus (optional second export): headline difference, largest area difference, and
the share of conditions with the same status (demonstrated / partly / not found).

TARGETS are the acceptance range set on 11 Nov 2026 before the first reviewer-standard run. One condition is worth
about 0.46 points of the headline score, so 3 points is roughly six or seven conditions changing outright.
"""
from statistics import mean

from .engine import documented
from .part_judgment import CREDIT_GAP

TARGETS = {'pass_agreement': 0.90, 'score_gap': 3.0, 'area_gap': 10.0, 'mean_credit_gap': 0.08,
           'run_score_gap': 3.0, 'run_area_gap': 10.0, 'run_same_status': 0.90}


def _status(credit):
    return 'demonstrated' if credit >= 1 else 'partly' if credit > 0 else 'not_found'


def _scores(credits, rubric):
    result = documented(credits, rubric)
    return result['overall'], {p['code']: p['score'] for p in result['pillars']}


def within_run(report):
    rubric = report['rubric']
    records = report['assessment']['records']
    paired = [r for r in records if len(r.get('pass_credits') or []) >= 2]
    if not paired:
        return {'available': False, 'note': 'No per-pass credits recorded (not a two-pass part-credit run).'}
    first = {r['condition_id']: r['pass_credits'][0] for r in paired}
    second = {r['condition_id']: r['pass_credits'][1] for r in paired}
    s1, a1 = _scores(first, rubric)
    s2, a2 = _scores(second, rubric)
    gaps = [abs(first[c] - second[c]) for c in first]
    third = [r['condition_id'] for r in records if len(r.get('pass_credits') or []) == 3]
    result = {'available': True, 'conditions_with_two_passes': len(paired),
              'pass_agreement': round(sum(g < CREDIT_GAP for g in gaps) / len(gaps), 3),
              'mean_credit_gap': round(mean(gaps), 3), 'score_pass_1': s1, 'score_pass_2': s2,
              'score_gap': round(abs(s1 - s2), 2), 'area_gap': round(max(abs(a1[k] - a2[k]) for k in a1), 2),
              'decided_by_third_pass': len(third),
              'largest_disagreements': sorted(({'condition_id': c, 'credits': [first[c], second[c]]} for c in first
                                               if abs(first[c] - second[c]) >= CREDIT_GAP),
                                              key=lambda row: -abs(row['credits'][0] - row['credits'][1]))[:15]}
    result['checks'] = {k: (result[k] >= TARGETS[k] if k == 'pass_agreement' else result[k] <= TARGETS[k])
                        for k in ('pass_agreement', 'score_gap', 'area_gap', 'mean_credit_gap')}
    return result


def credits_of(report):
    """Condition credits of any export: part credit when present, otherwise met = 1 and anything else = 0."""
    return {r['condition_id']: r.get('credit', 1.0 if r['state'] == 'met' else 0.0)
            for r in report['assessment']['records']}


def between_runs(report, other):
    rubric = report['rubric']
    mine, theirs = credits_of(report), credits_of(other)
    s1, a1 = _scores(mine, rubric)
    s2, a2 = _scores(theirs, rubric)
    same = sum(_status(mine[c]) == _status(theirs.get(c, 0.0)) for c in mine) / len(mine)
    records = {r['condition_id']: r for r in report['assessment']['records']}
    gained = sorted(c for c in mine if mine[c] > theirs.get(c, 0.0))
    lost = sorted(c for c in mine if mine[c] < theirs.get(c, 0.0))
    result = {'score': s1, 'other_score': s2, 'run_score_gap': round(abs(s1 - s2), 2),
              'run_area_gap': round(max(abs(a1[k] - a2[k]) for k in a1), 2), 'run_same_status': round(same, 3),
              'gained': [{'condition_id': c, 'credit': mine[c], 'before': theirs.get(c, 0.0),
                          'reason': records[c].get('reason', ''),
                          'quotes': [q['quote'] for q in records[c].get('citations', [])][:3]} for c in gained],
              'lost': [{'condition_id': c, 'credit': mine[c], 'before': theirs.get(c, 0.0)} for c in lost]}
    result['checks'] = {k: (result[k] >= TARGETS[k] if k == 'run_same_status' else result[k] <= TARGETS[k])
                        for k in ('run_score_gap', 'run_area_gap', 'run_same_status')}
    return result
