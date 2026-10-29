"""When a verified fact may be confirmed without a person -- configurable by fact type and risk level.

Settings (config/settings.py):

- FACT_VERIFICATION_MODE: 'shadow' (default) records every verification and what the policy *would* do, and
  changes no fact; 'enforce' lets the policy confirm eligible facts. Switch to 'enforce' only after the shadow
  report (`python manage.py fact_verification_report`) shows the rules agree with reviewers.
- FACT_RISK_BY_TYPE: data type -> risk ('low' | 'medium' | 'high'); FACT_RISK_BY_FIELD: {field_key regex: risk}
  overrides it. A calculated value, a fact read by the vision fallback and an institution-profile fact are always
  'high'.
- FACT_AUTOMATION_POLICY: risk -> {'automate': bool, 'allow_precedent': bool}. 'automate' lets a verified fact of
  that risk be confirmed by the rules; 'allow_precedent' lets an exact earlier reviewer decision (precedent.py)
  stand in for a person when 'automate' is off.
- FACT_REVIEW_BELOW_CONFIDENCE: facts the extractor itself rated below this are always sent to a person. This only
  ever adds review -- extraction confidence never confirms anything, and a high confidence never overrides a
  failed citation, arithmetic, scope or conflict check. A threshold that *allows* automation must come from the
  calibration in the shadow report (FACT_CONFIDENCE_CALIBRATION), never be picked by hand.

The required checks are the same for every fact (engine.verify): citation valid, quote found on the cited page,
value stated by the quote (or a passing calculation), every deterministic validation passing, and no comparable
source disagreeing. Only a fact whose verification outcome is `verified` is ever eligible.
"""
import re
from dataclasses import dataclass, field

from django.conf import settings

RISKS = ('low', 'medium', 'high')
DEFAULT_RISK_BY_TYPE = {'string': 'low', 'list': 'medium', 'boolean': 'medium', 'date': 'medium',
                        'number': 'medium', 'percentage': 'medium', 'currency': 'high'}
DEFAULT_POLICY = {
    'low': {'automate': True, 'allow_precedent': True},
    'medium': {'automate': True, 'allow_precedent': True},
    'high': {'automate': False, 'allow_precedent': True},
}


def mode():
    value = str(getattr(settings, 'FACT_VERIFICATION_MODE', 'shadow') or 'shadow').lower()
    return value if value in ('shadow', 'enforce') else 'shadow'


def policy():
    configured = getattr(settings, 'FACT_AUTOMATION_POLICY', None) or {}
    return {risk: {**DEFAULT_POLICY[risk], **(configured.get(risk) or {})} for risk in RISKS}


def risk_level(fact, derivation=None):
    """('low' | 'medium' | 'high', why)."""
    if derivation:
        return 'high', 'a calculated value'
    if (getattr(fact, 'extraction_method', '') or '') == 'vision':
        return 'high', 'read by the vision fallback'
    if getattr(fact, 'fact_kind', '') == 'profile':
        return 'high', 'an institution-profile fact (decides which benchmarks apply)'
    for pattern, risk in (getattr(settings, 'FACT_RISK_BY_FIELD', None) or {}).items():
        if risk in RISKS and re.search(pattern, fact.field_key or '', re.I):
            return risk, f'field rule {pattern}'
    by_type = {**DEFAULT_RISK_BY_TYPE, **(getattr(settings, 'FACT_RISK_BY_TYPE', None) or {})}
    risk = by_type.get(fact.data_type, 'medium')
    return (risk if risk in RISKS else 'medium'), f'{fact.data_type} value'


@dataclass
class Decision:
    #: auto_verified | precedent | would_auto_verify | would_precedent | review | not_applicable
    action: str
    reason: str
    eligible: bool = False
    blockers: list = field(default_factory=list)


def decide(fact, result, *, precedent=None, has_open_request=False, current_mode=None):
    """What the rules do with a fact after `result` (engine.VerificationResult). Only unreviewed facts are decided."""
    current_mode = current_mode or mode()
    if fact.status != 'extracted':
        return Decision('not_applicable', 'Already reviewed; verification is shown for information only.')
    blockers = []
    if result.outcome != 'verified':
        blockers.append(f'Verification: {result.outcome.replace("_", " ")} -- {result.reason}')
    if has_open_request:
        blockers.append('An evidence request is open; its reviewer decides.')
    if (getattr(fact, 'extraction_method', '') or '') == 'vision':
        blockers.append('Read by the vision fallback; always reviewed by a person.')
    floor = getattr(settings, 'FACT_REVIEW_BELOW_CONFIDENCE', None)
    if floor is not None and (fact.confidence_score or 0) < float(floor):
        blockers.append(f'Extraction confidence {fact.confidence_score:.2f} is below {float(floor):.2f} '
                        '(the extractor was unsure it read the value correctly).')
    rules = policy()[result.risk_level]
    via_precedent = False
    if not rules['automate']:
        if rules['allow_precedent'] and precedent and precedent.get('match') == 'exact':
            via_precedent = True
        else:
            blockers.append(f'{result.risk_level.capitalize()}-risk facts ({result.risk_reason}) are reviewed by a '
                            'person' + (' unless an earlier reviewer decision matches exactly.'
                                        if rules['allow_precedent'] else '.'))
    if blockers:
        return Decision('review', blockers[0], eligible=False, blockers=blockers)
    if via_precedent:
        who = precedent.get('decided_by_name') or 'a reviewer'
        reason = f'Matches {who}\'s {precedent.get("action", "decision")} of the same quote on an earlier version.'
        return Decision('precedent' if current_mode == 'enforce' else 'would_precedent', reason, eligible=True)
    reason = 'Every required check passed: ' + '; '.join(result.passed_summary)
    return Decision('auto_verified' if current_mode == 'enforce' else 'would_auto_verify', reason, eligible=True)
