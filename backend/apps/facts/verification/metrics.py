"""Is automation reducing review work -- and is it right? Read-only measurements.

- `workload(sprint)`: facts verified / eligible / automatically confirmed / sent to review, reviewer overrides of
  automatic decisions, open exception groups.
- `shadow_report(facts)`: replays the CURRENT rules over facts a PERSON already decided, on the value and citation
  as originally extracted (never the corrected value), and counts how often the rules would have agreed:
    would_auto_and_confirmed  -- the rules would have saved this review, and been right;
    would_auto_but_changed    -- the rules would have confirmed a value the person corrected or rejected (a false
                                 automatic decision -- the number that must be ~0 before enabling 'enforce');
    would_review              -- the rules send it to a person anyway.
  Plus a calibration table: reviewer agreement by extraction-confidence band, the only sound basis for any
  confidence threshold.
- `historical_audit(facts)`: what verification says about existing facts today, without changing any.

Nothing here writes to the database: verify_snapshot is pure, and these functions never call verify_fact.
"""
from collections import Counter

from django.db.models import Q

from apps.facts.models import ExtractedFact, FactReviewHistory

from . import engine, policy, precedent as precedent_mod

BANDS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 0.95), (0.95, 1.01)]


def _system_email():
    from apps.facts.auto_confirm import AUTO_CONFIRM_EMAIL
    return AUTO_CONFIRM_EMAIL


def workload(sprint):
    facts = ExtractedFact.objects.filter(sprint=sprint)
    auto_rows = FactReviewHistory.objects.filter(
        fact__sprint=sprint, action=FactReviewHistory.Action.CONFIRMED,
        decision_source__in=[FactReviewHistory.DecisionSource.RULE, FactReviewHistory.DecisionSource.PRECEDENT])
    auto_fact_ids = set(auto_rows.values_list('fact_id', flat=True))
    overrides = FactReviewHistory.objects.filter(fact__sprint=sprint, details__overrides_auto=True)
    reversed_ids = set(overrides.values_list('fact_id', flat=True)) & auto_fact_ids
    decisions = Counter(facts.values_list('automation_decision', flat=True))
    outcomes = Counter(facts.values_list('verification_status', flat=True))
    return {
        'mode': policy.mode(),
        'facts': facts.count(),
        'verified_once': facts.exclude(verification_status='').count(),
        'outcomes': {k or 'not_checked': v for k, v in outcomes.items()},
        'eligible': sum(decisions.get(k, 0) for k in ('auto_verified', 'precedent', 'would_auto_verify',
                                                        'would_precedent')),
        'auto_verified': auto_rows.filter(decision_source=FactReviewHistory.DecisionSource.RULE)
        .values('fact_id').distinct().count(),
        'auto_by_precedent': auto_rows.filter(decision_source=FactReviewHistory.DecisionSource.PRECEDENT)
        .values('fact_id').distinct().count(),
        'would_auto_verify': decisions.get('would_auto_verify', 0) + decisions.get('would_precedent', 0),
        'sent_to_review': facts.filter(automation_decision='review', status=ExtractedFact.Status.EXTRACTED).count(),
        'reviewer_overrides': overrides.count(),
        'reversed_automatic_decisions': len(reversed_ids),
        'legacy_auto_confirmed': facts.filter(reviewed_by__email=_system_email()).exclude(
            id__in=auto_fact_ids).count(),
    }


def _band(confidence):
    for low, high in BANDS:
        if low <= (confidence or 0) < high:
            return f'{low:.2f}–{min(high, 1):.2f}'
    return 'unknown'


def _as_extracted(fact):
    """The fact as the extractor first recorded it (value and citation), for a fair replay."""
    first = fact.review_history.order_by('created_at').first()
    value = fact.original_value if fact.original_value is not None else (
        first.original_value if first is not None else fact.value)
    overrides = {'value': value, 'status': ExtractedFact.Status.EXTRACTED}
    if fact.original_source_page or fact.original_source_snippet:
        overrides.update(source_page=fact.original_source_page, source_snippet=fact.original_source_snippet,
                         source_document=fact.original_source_document or fact.document)
    return engine.Snapshot.of(fact, **overrides)


def _person_decided(qs):
    email = _system_email()
    return qs.filter(status__in=[ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.CORRECTED,
                                 ExtractedFact.Status.REJECTED], reviewed_by__isnull=False).exclude(
        reviewed_by__email=email)


def shadow_report(facts_queryset, *, limit=None):
    """Replay the rules over person-decided facts (read-only). See module docstring."""
    rows = _person_decided(facts_queryset).select_related('source_document', 'document', 'reviewed_by',
                                                          'original_source_document')
    if limit:
        rows = rows[:limit]
    totals = Counter()
    blockers = Counter()
    calibration = {}
    false_auto = []
    for fact in rows:
        snap = _as_extracted(fact)
        result = engine.verify_snapshot(snap, exclude_ids=[])
        probe = _Probe(snap, fact)
        decision = policy.decide(probe, result, precedent=None, current_mode='enforce')
        person = 'agreed' if fact.status == ExtractedFact.Status.CONFIRMED else 'changed'
        band = calibration.setdefault(_band(fact.confidence_score), Counter())
        band[person] += 1
        totals['replayed'] += 1
        if decision.eligible:
            if person == 'agreed':
                totals['would_auto_and_confirmed'] += 1
            else:
                totals['would_auto_but_changed'] += 1
                false_auto.append({'fact_id': str(fact.id), 'field_key': fact.field_key, 'extracted': snap.value,
                                   'decided': fact.get_status_display(), 'now': fact.value})
        else:
            totals['would_review'] += 1
            blockers[_blocker_code(decision.blockers[0] if decision.blockers else decision.reason)] += 1
    decided = totals['would_auto_and_confirmed'] + totals['would_auto_but_changed']
    return {
        'policy_version': engine.POLICY_VERSION, 'mode': policy.mode(), 'totals': dict(totals),
        'precision_if_enabled': round(totals['would_auto_and_confirmed'] / decided, 4) if decided else None,
        'review_saved_share': round(totals['would_auto_and_confirmed'] / totals['replayed'], 4)
        if totals['replayed'] else None,
        'review_reasons': dict(blockers.most_common()),
        'false_automatic_decisions': false_auto[:50],
        'calibration': {band: {'agreed': c['agreed'], 'changed': c['changed'],
                               'agreement': round(c['agreed'] / (c['agreed'] + c['changed']), 4)}
                        for band, c in sorted(calibration.items())},
        'note': 'Read-only replay of the current rules over decisions people already made; nothing was changed.',
    }


class _Probe:
    """What policy.decide reads, for a replayed snapshot (status as extracted)."""
    def __init__(self, snap, fact):
        self.status = ExtractedFact.Status.EXTRACTED
        self.confidence_score = fact.confidence_score
        self.extraction_method = fact.extraction_method
        self.field_key, self.data_type, self.fact_kind = fact.field_key, fact.data_type, fact.fact_kind


def _blocker_code(text):
    low = (text or '').lower()
    for code, needle in (('quote_not_found', 'quote is not on page'), ('value_not_in_quote', 'does not state'),
                         ('contradicts_quote', 'contradicts'), ('conflict', 'conflict'),
                         ('arithmetic', 'arithmetic'), ('high_risk', 'risk facts'), ('vision', 'vision'),
                         ('low_confidence', 'extraction confidence'), ('page_text_missing', 'not stored'),
                         ('no_page', 'no page'), ('warning', 'percent'), ('judgement', 'judgement')):
        if needle in low:
            return code
    return 'other'


def historical_audit(facts_queryset):
    """What verification would say about existing facts today -- read-only, nothing recorded or changed."""
    outcomes, examples = Counter(), {}
    for fact in facts_queryset.select_related('source_document', 'document'):
        result = engine.verify_snapshot(engine.Snapshot.of(fact))
        outcomes[(fact.status, result.outcome)] += 1
        bucket = examples.setdefault(f'{fact.status}/{result.outcome}', [])
        if len(bucket) < 5:
            bucket.append({'fact_id': str(fact.id), 'field_key': fact.field_key, 'value': fact.value,
                           'reason': result.reason})
    return {'counts': {f'{s}/{o}': n for (s, o), n in sorted(outcomes.items())},
            'examples': examples,
            'note': 'Read-only: no fact, review or score was changed. Reviewed facts keep their decisions.'}


# -- exception review ---------------------------------------------------------------------------------

GROUP_LABELS = {
    'contradicts_quote': 'Value contradicts its own quote', 'quote_not_found': 'Quote not found on the cited page',
    'value_not_in_quote': 'Quote does not state the value', 'conflict': 'Sources disagree',
    'arithmetic': 'Calculation does not add up', 'high_risk': 'High-risk value (policy: person reviews)',
    'vision': 'Read by the vision fallback', 'low_confidence': 'Extractor unsure it read the value',
    'page_text_missing': 'Page text not stored (cannot check)', 'no_page': 'No page cited',
    'warning': 'Unit or format warning', 'judgement': 'Judgement value (cannot be matched to the quote)',
    'invalid': 'Fails a validation rule', 'other': 'Other', 'not_checked': 'Not verified yet',
}
RISK_ORDER = {'high': 0, 'medium': 1, 'low': 2, '': 3}


def exception_queue(sprint):
    """Unreviewed facts that need a person, grouped by why and ordered by risk then CRI weight then confidence."""
    from apps.scoring.constants import AIQIF_PILLARS
    weight = {key: w for key, _c, _n, w, _k in AIQIF_PILLARS}
    facts = (ExtractedFact.objects.filter(sprint=sprint, status=ExtractedFact.Status.EXTRACTED)
             .filter(Q(automation_decision__in=['review', '']) | Q(verification_status__in=['invalid', 'conflicting',
                                                                                         'needs_review', ''])))
    groups = {}
    for fact in facts.only('id', 'field_key', 'field_name', 'value', 'pillar', 'risk_level', 'confidence_score',
                           'verification_status', 'automation_reason', 'automation_decision'):
        if not fact.verification_status:
            code = 'not_checked'
        elif fact.verification_status == 'invalid' and _blocker_code(fact.automation_reason) == 'other':
            code = 'invalid'
        else:
            code = _blocker_code(fact.automation_reason)
        group = groups.setdefault(code, {'code': code, 'label': GROUP_LABELS.get(code, code), 'items': []})
        group['items'].append({'fact_id': str(fact.id), 'field_key': fact.field_key, 'field_name': fact.field_name,
                               'value': fact.value, 'pillar': fact.pillar, 'risk_level': fact.risk_level,
                               'confidence_score': fact.confidence_score, 'status': fact.verification_status,
                               'reason': fact.automation_reason, 'impact': weight.get(fact.pillar, 0)})
    for group in groups.values():
        group['items'].sort(key=lambda i: (RISK_ORDER.get(i['risk_level'] or '', 3), -i['impact'],
                                           i['confidence_score'] or 0))
        group['count'] = len(group['items'])
        group['high_risk'] = sum(1 for i in group['items'] if i['risk_level'] == 'high')
    severity = {'contradicts_quote': 0, 'arithmetic': 0, 'invalid': 0, 'conflict': 1}
    return sorted(groups.values(), key=lambda g: (severity.get(g['code'], 2), -g['high_risk'], -g['count']))


def precedent_for(fact):
    from . import scope
    return precedent_mod.find(fact, scope.read_scope(fact))
