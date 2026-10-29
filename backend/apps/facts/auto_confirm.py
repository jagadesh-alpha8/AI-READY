"""Automatic confirmation of extracted facts -- now decided by the shared verification pipeline.

Since apps/facts/verification/, a fact is confirmed without a person only when verification proves it
(citation and page exist, the quote is on the cited page, the quote states the value or a checked calculation
produces it, every deterministic validation passes, no comparable source disagrees) AND the automation policy
allows its risk level (verification/policy.py), with FACT_VERIFICATION_MODE='enforce'. AI confidence alone
never confirms a fact: FACT_AUTO_CONFIRM_MIN_CONFIDENCE is no longer a confirmation rule.

What stays here: the system account every automatic confirmation is recorded as
(`auto.confirm@system.ingage.local`, inactive, cannot sign in), `is_auto_confirmed`, and `auto_confirm()` for the
`auto_confirm_facts` command, which now runs the same pipeline. Unlike a person's decision, a re-extraction may
still update an auto-confirmed fact (ExtractionPipeline._persist_facts), which is then verified again.
"""
from django.conf import settings
from django.contrib.auth import get_user_model

from .models import ExtractedFact

AUTO_CONFIRM_EMAIL = 'auto.confirm@system.ingage.local'


def threshold():
    """The legacy confidence setting (informational only: it no longer confirms anything)."""
    value = getattr(settings, 'FACT_AUTO_CONFIRM_MIN_CONFIDENCE', None)
    return None if value is None else float(value)


def system_user():
    User = get_user_model()
    user = User.objects.filter(email=AUTO_CONFIRM_EMAIL).first()
    if user is None:
        user = User(email=AUTO_CONFIRM_EMAIL, username='auto-confirm', first_name='Auto', last_name='Confirm',
                    role=User.Role.CONSULTANT, is_active=False)
        user.set_unusable_password()
        user.save()
    return user


def is_auto_confirmed(fact):
    return fact.status == ExtractedFact.Status.CONFIRMED and fact.reviewed_by_id is not None and (
        getattr(fact.reviewed_by, 'email', None) == AUTO_CONFIRM_EMAIL)


def auto_confirm(facts_queryset, *, dry_run=False):
    """Verify the unreviewed facts of `facts_queryset` and let the policy decide them.

    dry_run: nothing is written at all (no verification record, no status) -- the rules are replayed in memory.
    Otherwise each fact's verification is recorded and the policy applied in the configured mode (shadow records
    what it would do; enforce confirms). Returns {'confirmed': [ids confirmed, or that would be],
    'skipped': {reason: n}, 'mode'}."""
    from .evidence_requests import open_request_for
    from .verification import engine, metrics, policy, precedent, scope

    current = policy.mode()
    result = {'confirmed': [], 'skipped': {}, 'mode': 'dry run' if dry_run else current}
    for fact in facts_queryset.filter(status=ExtractedFact.Status.EXTRACTED).select_related(
            'source_document', 'document', 'sprint'):
        if dry_run:
            verified = engine.verify_snapshot(engine.Snapshot.of(fact))
            decision = policy.decide(fact, verified, precedent=precedent.find(fact, scope.read_scope(fact)),
                                     has_open_request=bool(open_request_for(fact)), current_mode='shadow')
            action, why = decision.action, decision.reason
        else:
            run = engine.verify_fact(fact, source='reverify', apply_policy=True, current_mode=current)
            action, why = run.automation_decision, run.automation_reason
        if action in ('auto_verified', 'precedent', 'would_auto_verify', 'would_precedent'):
            result['confirmed'].append(str(fact.id))
        else:
            reason = metrics.GROUP_LABELS.get(metrics._blocker_code(why), 'Other')
            result['skipped'][reason] = result['skipped'].get(reason, 0) + 1
    return result
