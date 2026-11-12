"""Why a requirement decision stands as it does, as a structured field rather than prose.

Every record leaving evaluation carries ``cause``. Report, diagnostics and advice read
it instead of matching reason strings, so an evidentiary unknown (the sources do not
establish the applicable population or period) is never treated as a processing
failure, and a processing failure is never presented as a finding about the institution.

Causes
- ``assessed``: the model's decision passed validation. This includes an ``unknown`` the
  model chose itself because the supplied evidence was insufficient.
- ``scope_or_period_unsupported``: the model proposed a substantive state but did not
  establish the applicable population or period. Evidentiary, not processing.
- ``review_guard``: a citation reused a rejected, corrected or actively disputed review
  claim. Independent evidence or a review decision is needed. Not processing.
- ``response_invalid``: the response broke the decision contract or its citations did not
  ground in the supplied passages. Processing.
- ``not_evaluated``: no judgement was made (no readable context, budget, provider failure,
  oversized input). Processing.
- ``assessor_disagreement``: two independent assessments of the same frozen packet reached
  different states, so the requirement is left unknown and routed to review. Not processing.

Records saved before this field existed are classified from their saved reason text by
``cause_of``; new records never depend on that fallback.
"""
from collections import Counter

ASSESSED = 'assessed'
SCOPE_OR_PERIOD_UNSUPPORTED = 'scope_or_period_unsupported'
REVIEW_GUARD = 'review_guard'
RESPONSE_INVALID = 'response_invalid'
NOT_EVALUATED = 'not_evaluated'
ASSESSOR_DISAGREEMENT = 'assessor_disagreement'

CAUSES = (ASSESSED, SCOPE_OR_PERIOD_UNSUPPORTED, REVIEW_GUARD, RESPONSE_INVALID, NOT_EVALUATED, ASSESSOR_DISAGREEMENT)
PROCESSING = frozenset({RESPONSE_INVALID, NOT_EVALUATED})

SCOPE_OR_PERIOD_ISSUE = 'Applicable population or reporting period not established.'
REVIEW_GUARD_PREFIX = 'Citation reuses a rejected or superseded claim'
NOT_EVALUATED_PREFIXES = ('Reviewed-evidence context exceeds', 'No readable source context',
                          'Evaluation call budget reached', 'Model evaluation failed')


def for_issue(issue):
    """The cause for a validation issue raised by validate_decisions (or '' for none)."""
    if not issue:
        return ASSESSED
    from .evidence_parts import APPROVAL_MISSING
    if issue == APPROVAL_MISSING:
        return ASSESSED
    if issue in (SCOPE_OR_PERIOD_ISSUE, 'A report timestamp alone cannot support a finding.'):
        return SCOPE_OR_PERIOD_UNSUPPORTED
    if issue.startswith(REVIEW_GUARD_PREFIX) or issue.startswith('Citation reuses'):
        return REVIEW_GUARD
    if issue.startswith(NOT_EVALUATED_PREFIXES):
        return NOT_EVALUATED
    return RESPONSE_INVALID


def cause_of(record):
    """The record's structured cause, or a conservative reading of a legacy saved reason."""
    cause = record.get('cause')
    if cause in CAUSES:
        return cause
    if record.get('state', 'unknown') != 'unknown':
        return ASSESSED
    from .assessment_audit import VALIDATION_REASONS
    issue = record.get('validation_issue') or ''
    reason = record.get('reason') or ''
    if issue:
        return for_issue(issue)
    if reason in VALIDATION_REASONS or reason.startswith(NOT_EVALUATED_PREFIXES) or reason.startswith(REVIEW_GUARD_PREFIX):
        return for_issue(reason)
    return ASSESSED


def is_processing(record):
    return record.get('state', 'unknown') == 'unknown' and cause_of(record) in PROCESSING


def summary(records):
    """Counts by state and cause, so 'unknown' can be read as evidence, review or processing."""
    counts = Counter((r.get('state', 'unknown'), cause_of(r)) for r in records)
    return {'version': 'decision-causes-1',
            'by_state_and_cause': [{'state': s, 'cause': c, 'count': n} for (s, c), n in sorted(counts.items())],
            'unknown_evidentiary': sum(n for (s, c), n in counts.items() if s == 'unknown' and c in (ASSESSED, SCOPE_OR_PERIOD_UNSUPPORTED)),
            'unknown_review': sum(n for (s, c), n in counts.items() if s == 'unknown' and c in (REVIEW_GUARD, ASSESSOR_DISAGREEMENT)),
            'unknown_processing': sum(n for (s, c), n in counts.items() if s == 'unknown' and c in PROCESSING)}
