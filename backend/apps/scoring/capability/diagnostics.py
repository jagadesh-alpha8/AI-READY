"""Read-only explanations of frozen results; never reinterpret or change a score."""
from collections import Counter
from .assessment_audit import diagnose, issue_for


def explain(inputs, assessment):
    records = assessment['records']
    counts = Counter(r['state'] for r in records)
    issues = Counter(issue_for(r) for r in records if issue_for(r))
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
    if inputs['rubric'].get('aggregation') == 'independent_conditions':
        explanation = ('Each supported assertion contributes independently to the lower bound; unresolved assertions expand the upper bound. '
                       'A missing foundation does not erase other demonstrated capability. '
                       'Default findings may describe the period reported by a source, rather than current operation.')
        if not counts['met']:
            explanation = ('No positive assertion has been established for this scope and period. '
                           'This is not a finding of zero capability. Check identity, dates, retrieval and validation reasons; unknown is not absence.')
    return {'version': 'capability-diagnostics-0.3',
            'cause_audit': diagnose(assessment, rubric=inputs['rubric'], manifest=manifest), 'state_counts': {s: counts[s] for s in (
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
