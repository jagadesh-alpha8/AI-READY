"""Inference-free diagnosis of stored decisions, not a new evidence judgement.

Known old publication paths erased validation_issue while retaining its fixed reason.
Recognise only those exact internal reason strings; never classify arbitrary model prose
as a validator error. Do not infer that the supplied corpus is the full institution corpus.
"""
from collections import Counter

from .decision_causes import cause_of
from .evidence_parts import APPROVAL_MISSING

VALIDATION_REASONS = frozenset({
    APPROVAL_MISSING,
    'Condition decision missing or duplicated.', 'Invalid state or missing rationale.',
    'Invalid citations.', 'Invalid citation record.', 'Quote does not match a supplied source passage.',
    'A substantive decision needs source support.', 'A conflict requires two distinct source passages.',
    'Applicable population or reporting period not established.',
})


def issue_for(record):
    return record.get('validation_issue') or (record.get('reason') if record.get('reason') in VALIDATION_REASONS else '')


def _blocker_kind(row, issue):
    """Classify a foundation blocker by its structured cause, not by reason text."""
    from .decision_causes import cause_of
from .evidence_parts import APPROVAL_MISSING, NOT_EVALUATED, RESPONSE_INVALID, SCOPE_OR_PERIOD_UNSUPPORTED, REVIEW_GUARD
    if not row:
        return 'evaluation_unavailable'
    cause = cause_of(row)
    if cause == NOT_EVALUATED:
        return 'evaluation_unavailable'
    if cause == RESPONSE_INVALID:
        return 'response_validation'
    if cause == SCOPE_OR_PERIOD_UNSUPPORTED:
        return 'scope_or_period_unsupported'
    if cause == REVIEW_GUARD:
        return 'review_guard'
    return 'unresolved_evidence' if row.get('state') in ('unknown', 'conflicting') else 'documented_shortfall'


def diagnose(assessment, *, rubric=None, manifest=None):
    records = assessment.get('records', [])
    traces = assessment.get('traces', [])
    result = assessment.get('result', {})
    issues = Counter(issue_for(r) for r in records if issue_for(r))
    states = Counter(r.get('state', 'unknown') for r in records)
    decisions = {r['condition_id']: r for r in records}
    indicators = rubric.get('indicators', []) if rubric else result.get('indicators', [])
    expected = {c['id'] for i in indicators for c in i['conditions']}
    counts = Counter(r['condition_id'] for r in records)
    record_contract = {'expected': len(expected), 'returned': len(records),
        'missing_ids': sorted(expected - set(counts)), 'duplicate_ids': sorted(cid for cid, n in counts.items() if n > 1),
        'unexpected_ids': sorted(set(counts) - expected)}
    record_contract['complete'] = bool(expected) and len(records) == len(expected) and set(counts) == expected
    foundations = []
    for indicator in indicators:
        foundational = [c for c in indicator['conditions'] if c['level'] == 'F']
        blockers = []
        for c in foundational:
            row = decisions.get(c['id'], {})
            if row.get('state') != 'met':
                issue = issue_for(row)
                blockers.append({'condition_id': c['id'], 'requirement': c['text'],
                    'state': row.get('state', 'unknown'), 'reason': row.get('reason', 'No saved decision.'),
                    'validation_issue': issue,
                    'cause': cause_of(row) if row else 'not_evaluated',
                    'kind': _blocker_kind(row, issue)})
        if blockers:
            foundations.append({'indicator': indicator['code'], 'blockers': blockers})
    calls = assessment.get('inference', {}).get('calls', [])
    outcomes = [c for c in calls if c.get('kind') == 'request_outcome']
    reservations = [c for c in calls if c.get('kind') == 'request_reserved']
    outputs = [c.get('tokens', {}).get('completion_tokens', c.get('tokens', {}).get('output_tokens')) for c in outcomes]
    outputs = [n for n in outputs if type(n) is int]
    selected = {s['id'] for t in traces for s in t.get('source_excerpts', [])}
    return {'version': 'assessment-cause-audit-0.1', 'record_contract': record_contract,
        'state_counts': {s: states[s] for s in ('met', 'not_met', 'unknown', 'conflicting')},
        'conditions_with_issues': sum(issues.values()),
        'validator_affected_conditions': sum(n for reason, n in issues.items() if reason in VALIDATION_REASONS),
        'evaluation_unavailable_conditions': sum(n for reason, n in issues.items() if reason not in VALIDATION_REASONS),
        'validation_issues': [{'reason': reason, 'count': n} for reason, n in sorted(issues.items())],
        'unknown_without_validator_issue': sum(r.get('state') == 'unknown' and not issue_for(r) for r in records),
        'legacy_issue_fields_recovered': sum(not r.get('validation_issue') and r.get('reason') in VALIDATION_REASONS for r in records),
        'foundation_blockers': foundations,
        'bounded_context_indicators': sum(bool(t.get('context_is_subset')) for t in traces),
        'unique_selected_source_pages': len(selected),
        'source_documents': len(manifest) if manifest is not None else None,
        'manifest_pages': sum(len(d.get('pages', [])) for d in manifest) if manifest is not None else None,
        'manifest_page_statuses': dict(Counter(p.get('status', 'unspecified') for d in (manifest or []) for p in d.get('pages', []))),
        'reserved_requests': len(reservations), 'response_outcomes': len(outcomes),
        'received_responses': sum(c.get('outcome') == 'response_received' for c in outcomes),
        'maximum_recorded_output_tokens': max(outputs) if outputs else None,
        'configured_output_token_limit': assessment.get('inference', {}).get('settings', {}).get('output_tokens'),
        'actual_models': sorted({c['actual_model'] for c in outcomes if c.get('actual_model')}),
        'limitations': [
            'No source is reinterpreted and no scores are changed by this diagnosis.',
            'An unknown model judgement is not proof that the full documents lack the evidence.',
            'Selected context is a subset; page coverage does not measure semantic retrieval recall.',
            'The active-source manifest does not establish full-folder import completeness.',
        ]}
