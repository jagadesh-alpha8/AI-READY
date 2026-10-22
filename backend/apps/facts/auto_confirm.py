"""Auto-confirm extracted facts whose AI confidence is above FACT_AUTO_CONFIRM_MIN_CONFIDENCE (default 0.80).

Run at the end of each extraction (ExtractionPipeline) and, for facts extracted earlier, by
`python manage.py auto_confirm_facts`. A fact is auto-confirmed only when ALL of these hold:

- it is still EXTRACTED (nobody has reviewed it) and its confidence is strictly above the threshold;
- it is not part of an open conflict (two facts disagreeing -- a person decides which is right);
- its value is supported by its own quote: for numbers, percentages and amounts, the number appears in the
  source snippet (an AI-filled number with no quote behind it -- e.g. a percentage the document never gives --
  is left for a person).

Every auto-confirmation is a FactReviewHistory CONFIRMED row by the system account
`auto.confirm@system.ingage.local` (inactive, cannot sign in), with the confidence in its reason, so it can be
told apart from a person's confirmation and found again. Auto-confirmed facts count in the CRI like any
confirmed fact. Unlike a person's decision, a re-extraction may still update an auto-confirmed fact
(ExtractionPipeline._persist_facts), which is then checked again.
"""
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import ExtractedFact, FactReviewHistory

AUTO_CONFIRM_EMAIL = 'auto.confirm@system.ingage.local'
NUMERIC_TYPES = (ExtractedFact.DataType.NUMBER, ExtractedFact.DataType.PERCENTAGE, ExtractedFact.DataType.CURRENCY)


def threshold():
    """The configured threshold, or None when auto-confirmation is switched off (empty / 'off')."""
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


def _number_forms(value):
    """The ways a numeric value can be written in a quote: 42, 42.0 -> '42'; 77.94; 1,234 -> '1234'."""
    try:
        number = float(str(value).replace(',', '').replace('%', '').strip())
    except (TypeError, ValueError):
        return set()
    forms = {f'{number:g}'}
    if number == int(number):
        forms.add(str(int(number)))
    else:
        forms |= {f'{number:.1f}', f'{number:.2f}'}
    return forms


def value_in_snippet(fact):
    """True when the fact's value is backed by its own quote (numbers must appear in it)."""
    snippet = fact.source_snippet or ''
    if not snippet.strip():
        return False
    if fact.data_type not in NUMERIC_TYPES:
        return True
    numbers_in_quote = set()
    for token in re.findall(r'\d[\d,]*(?:\.\d+)?', snippet):
        numbers_in_quote |= _number_forms(token)
    return bool(_number_forms(fact.value) & numbers_in_quote)



def _in_open_conflict(facts):
    from apps.gaps.models import GapItem
    ids = [f.id for f in facts]
    rows = GapItem.objects.filter(gap_type=GapItem.GapType.CONFLICT, status__in=GapItem.ACTIVE_STATUSES).filter(
        source_fact_id__in=ids).values_list('source_fact_id', flat=True)
    rows_b = GapItem.objects.filter(gap_type=GapItem.GapType.CONFLICT, status__in=GapItem.ACTIVE_STATUSES).filter(
        conflict_fact_b_id__in=ids).values_list('conflict_fact_b_id', flat=True)
    return set(rows) | set(rows_b)


def auto_confirm(facts_queryset, *, dry_run=False):
    """Auto-confirm the eligible facts of `facts_queryset`. Returns {'confirmed': [...ids], 'skipped': {reason: n}}."""
    from apps.gaps.services import resolve_unconfirmed_fact_gap

    limit = threshold()
    result = {'confirmed': [], 'skipped': {}, 'threshold': limit}
    if limit is None:
        return result
    candidates = list(facts_queryset.filter(status=ExtractedFact.Status.EXTRACTED, confidence_score__gt=limit))
    conflicted = _in_open_conflict(candidates)
    user = None if dry_run else system_user()
    for fact in candidates:
        reason = None
        if fact.id in conflicted:
            reason = 'open conflict'
        elif not value_in_snippet(fact):
            reason = 'value not in its quote'
        if reason:
            result['skipped'][reason] = result['skipped'].get(reason, 0) + 1
            continue
        result['confirmed'].append(str(fact.id))
        if dry_run:
            continue
        with transaction.atomic():
            # Only if still unreviewed at this moment (a person may have acted meanwhile).
            updated = ExtractedFact.objects.filter(pk=fact.pk, status=ExtractedFact.Status.EXTRACTED).update(
                status=ExtractedFact.Status.CONFIRMED, reviewed_by=user, reviewed_at=timezone.now(),
                updated_at=timezone.now())
            if not updated:
                result['confirmed'].pop()
                continue
            FactReviewHistory.objects.create(
                fact=fact, action=FactReviewHistory.Action.CONFIRMED, original_value=fact.value, user=user,
                reason=f'Auto-confirmed: AI confidence {fact.confidence_score:.2f} is above {limit:.2f}.')
            fact.refresh_from_db()
            resolve_unconfirmed_fact_gap(fact, user=user)
    return result
