"""Bulk confirmation of AI-QIF category tags (FactAIQIFMapping) in one sprint.

Confirms tag *mappings* only: the fact itself (status, value, review) is never touched. A tag is eligible
when it is still unreviewed, the AI was confident about it (status MAPPED, i.e. at or above
AIQIF_MAPPING_MIN_CONFIDENCE -- the existing policy: "needs review" tags are reviewed one by one, never in
bulk) and its indicator code is a real AI-QIF indicator. Rejected and confirmed tags are left as they are,
so repeating the request changes nothing.

Each fact whose tags were confirmed gets one FactReviewHistory row (action AIQIF_TAGS_CONFIRMED: reviewer,
time, sprint, the codes and the size of the bulk action). Afterwards the CRI is recalculated with the normal
engine, so AI-QIF Evidence Coverage and the Coverage-adjusted CRI reflect the new tags; the Raw CRI is
calculated from facts only and does not change because of tags.
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.scoring.constants import AIQIF_INDICATORS

from .models import FactAIQIFMapping, FactReviewHistory

Review = FactAIQIFMapping.ReviewStatus


def _pending(sprint, mapping_ids=None):
    qs = FactAIQIFMapping.objects.filter(fact__sprint=sprint, review_status=Review.UNREVIEWED).select_related('fact')
    if mapping_ids is not None:
        qs = qs.filter(pk__in=mapping_ids)
    return qs


def summary(sprint, mapping_ids=None):
    """What a bulk confirmation would do: counts, confidence range, and what is left for individual review."""
    pending = list(_pending(sprint, mapping_ids))
    eligible = [m for m in pending if m.status == FactAIQIFMapping.Status.MAPPED and m.indicator_code in AIQIF_INDICATORS]
    low = [m for m in pending if m.status != FactAIQIFMapping.Status.MAPPED]
    confidences = [m.confidence for m in eligible]
    return {
        'pending_count': len(pending),
        'eligible_count': len(eligible),
        'eligible_ids': [str(m.id) for m in eligible],
        'low_confidence_count': len(low),
        'low_confidence_threshold': settings.AIQIF_MAPPING_MIN_CONFIDENCE,
        'confidence_min': min(confidences) if confidences else None,
        'confidence_max': max(confidences) if confidences else None,
        'facts_count': len({m.fact_id for m in eligible}),
    }


def confirm_pending(sprint, user, mapping_ids=None, note=''):
    """Confirm every eligible pending tag (of `mapping_ids`, or the whole sprint). Returns the result summary."""
    plan = summary(sprint, mapping_ids)
    note = (note or '').strip()
    now = timezone.now()
    confirmed, by_fact = [], {}
    for mapping in FactAIQIFMapping.objects.filter(pk__in=plan['eligible_ids']).select_related('fact'):
        with transaction.atomic():
            # Only if still unreviewed now (another reviewer may have decided it meanwhile): idempotent.
            updated = FactAIQIFMapping.objects.filter(pk=mapping.pk, review_status=Review.UNREVIEWED).update(
                review_status=Review.CONFIRMED, reviewed_by=user, reviewed_at=now,
                review_note=note or 'Confirmed with "Confirm all pending tags".')
        if updated:
            confirmed.append(str(mapping.id))
            by_fact.setdefault(mapping.fact, []).append(mapping.indicator_code)
    for fact, codes in by_fact.items():
        FactReviewHistory.objects.create(
            fact=fact, action=FactReviewHistory.Action.AIQIF_TAGS_CONFIRMED, original_value=fact.value, user=user,
            reason=(f'AI-QIF tags confirmed in bulk ({", ".join(sorted(codes))}); one action confirming '
                    f'{len(confirmed)} tag(s) in sprint {sprint.sprint_code}. The fact itself was not changed.'
                    + (f' Note: {note}' if note else '')))
    remaining = _pending(sprint, mapping_ids)
    result = {
        'confirmed_count': len(confirmed),
        'confirmed_ids': confirmed,
        'already_decided_count': len(plan['eligible_ids']) - len(confirmed),
        'still_pending_count': remaining.count(),
        'still_pending': [{'id': str(m.id), 'fact_id': str(m.fact_id), 'indicator_code': m.indicator_code,
                           'reason': 'low AI confidence: review individually'
                           if m.status != FactAIQIFMapping.Status.MAPPED else 'not an AI-QIF indicator code'}
                          for m in remaining[:200]],
        'low_confidence_threshold': plan['low_confidence_threshold'],
        'coverage': None,
    }
    if confirmed:
        from apps.scoring.services import run_scoring_engine
        run = run_scoring_engine(sprint, triggered_by=user)
        cov = run.evidence_coverage or {}
        result['coverage'] = {
            'raw_cri': run.overall_cri, 'coverage_adjusted_cri': run.coverage_adjusted_cri,
            'covered_count': cov.get('covered_count'), 'applicable_count': cov.get('applicable_count'),
            'ratio': cov.get('ratio'), 'scoring_run_id': str(run.id),
        }
    return result
