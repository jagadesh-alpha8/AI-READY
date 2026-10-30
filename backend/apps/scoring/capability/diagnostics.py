"""Read-only explanations of frozen results; never reinterpret or change a score."""
from collections import Counter


def explain(inputs, assessment):
    records = assessment['records']
    counts = Counter(r['state'] for r in records)
    issues = Counter(r.get('validation_issue') for r in records if r.get('validation_issue'))
    decisions = {r['condition_id']: r['state'] for r in records}
    blocked = []
    for indicator in inputs['rubric']['indicators']:
        missing = [c['id'] for c in indicator['conditions']
                   if c['level'] == 'F' and decisions.get(c['id']) != 'met']
        if missing:
            blocked.append({'indicator': indicator['code'], 'requirements': missing})
    manifest = inputs['manifest']
    readable = len(inputs['sources'])
    result = assessment['result']
    if counts['unknown'] == len(records):
        explanation = ('No requirement was established from the supplied passages. '
                       'The zero lower bound is not a finding that the institution has no AI capability.')
    elif result['lower'] == 0 and result['exact_score'] is None:
        explanation = ('No indicator has every foundational requirement demonstrated. '
                       'Unresolved evidence remains possible capability, not a documented failure.')
    elif result['exact_score'] == 0:
        explanation = ('The frozen decisions establish a zero score under this rubric. '
                       'Inspect the documented foundational shortfalls and their citations.')
    else:
        explanation = ('The lower bound counts demonstrated capability; the upper bound includes unresolved possibilities. '
                       'Both use the same fixed prerequisite rules.')
    return {'version': 'capability-diagnostics-0.1', 'state_counts': {s: counts[s] for s in (
                'met', 'not_met', 'unknown', 'conflicting')},
            'source_documents': len(manifest), 'readable_pages': readable,
            'unreadable_or_unavailable_pages': sum(max(d.get('expected_pages') or 0, len(d['pages']))
                                                 for d in manifest) - readable,
            'validation_issues': [{'reason': k, 'count': v} for k, v in sorted(issues.items())],
            'foundation_blockers': blocked,
            'indicators_with_bounded_context': sum(bool(t.get('context_is_subset'))
                                                  for t in assessment.get('traces', [])),
            'explanation': explanation,
            'limitations': 'These diagnostics explain stored decisions, not their semantic accuracy. '
                          'Bounded retrieval can miss evidence. A document count alone cannot establish the cause of a low score.'}
