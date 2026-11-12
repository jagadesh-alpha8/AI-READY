"""Retire absent machine observations only at a successful, complete extraction boundary."""
from django.db import transaction
from django.utils import timezone
from .models import ExtractedFact


@transaction.atomic
def reconcile_extraction(job, seen_ids, pages):
    from apps.extraction.models import ExtractionJob
    from apps.documents.models import Document
    from apps.extraction.exceptions import ExtractionCancelled, ExtractionSuperseded
    from .auto_confirm import is_auto_confirmed
    from .verification.grounding import parse_pages
    if job.completeness != ExtractionJob.Completeness.COMPLETE:
        return {'retired': 0, 'source_review': 0}
    Document.objects.select_for_update().get(pk=job.document_id)
    current = ExtractionJob.objects.select_for_update().get(pk=job.pk)
    token = getattr(job, 'task_token', '')
    if token and current.celery_task_id and current.celery_task_id != token:
        raise ExtractionSuperseded('Extraction was handed to another worker before fact reconciliation.')
    if current.status == ExtractionJob.Status.CANCELLED:
        raise ExtractionCancelled('Extraction was cancelled before fact reconciliation.')
    if (current.completeness != ExtractionJob.Completeness.COMPLETE or
            current.status not in (ExtractionJob.Status.PENDING, ExtractionJob.Status.RUNNING, ExtractionJob.Status.RETRYING)):
        return {'retired': 0, 'source_review': 0}
    # Use exactly the text supplied to extraction; quotations can be whitespace-normalized.
    text = {p['page_number']: ' '.join((p.get('text') or '').split()) for p in pages.get('pages', [])}
    changes, fields = {'retired': 0, 'source_review': 0}, set()
    now = timezone.now()
    for fact in ExtractedFact.objects.select_for_update(of=('self',)).filter(document_id=job.document_id).select_related('reviewed_by'):
        # Never retire an observation created by a later job.
        if job.started_at and fact.created_at > job.started_at and fact.pk not in seen_ids:
            continue
        machine = fact.status == ExtractedFact.Status.EXTRACTED or is_auto_confirmed(fact)
        if machine and fact.pk not in seen_ids:
            fact.retired_at = now
            fact.save(update_fields=['retired_at', 'updated_at'])
            fields.add(fact.field_key)
            changes['retired'] += 1
        elif not machine and (fact.source_document_id or fact.document_id) == job.document_id:
            quote = ' '.join(fact.source_snippet.split())
            supported = bool(quote) and any(quote in text.get(n, '') for n in parse_pages(fact.source_page))
            needs_review = not supported
            if fact.source_review_required != needs_review:
                fact.source_review_required = needs_review
                fact.save(update_fields=['source_review_required', 'updated_at'])
            changes['source_review'] += int(needs_review)
    # Resolve retired observation tasks, but preserve an active contradiction
    # when independent current alternatives still disagree in the same scope.
    from django.db.models import Q
    from apps.gaps.models import GapItem, GapEvent
    from .verification.conflicts import disagreements, comparable_pair, refresh, refresh_for_field
    from .verification.normalize import comparable_value
    retired = ExtractedFact.all_objects.filter(document_id=job.document_id, retired_at__isnull=False)
    affected = GapItem.objects.filter(sprint_id=job.sprint_id).filter(
        Q(source_fact__in=retired) | Q(conflict_fact_b__in=retired)).exclude(status='resolved').select_related('source_fact')
    for gap in affected:
        if gap.gap_type == GapItem.GapType.CONFLICT and gap.source_fact:
            candidates = ExtractedFact.objects.filter(sprint_id=job.sprint_id, field_key__iexact=gap.source_fact.field_key)
            groups = disagreements([f for f in candidates if comparable_pair(gap.source_fact, f)[0]])
            if groups:
                group = groups[0]
                first = group[0]
                other = next(f for f in group if comparable_value(f.value, f.data_type) != comparable_value(first.value, first.data_type))
                gap.source_fact, gap.conflict_fact_b = first, other
                gap.save(update_fields=['source_fact', 'conflict_fact_b', 'updated_at'])
                refresh(gap)
                continue
        gap.status, gap.resolved_at = 'resolved', now
        gap.resolution = 'Source observation retired after a complete re-extraction.'
        gap.save(update_fields=['status', 'resolved_at', 'resolution', 'updated_at'])
        GapEvent.objects.create(gap=gap, action=GapEvent.Action.AUTO_RESOLVED, note=gap.resolution)
    for key in fields:
        refresh_for_field(job.sprint_id, key)
    return changes
