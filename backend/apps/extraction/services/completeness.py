"""How completely a sprint's documents have been processed -- one place, used by the AI Processing Monitor,
the review / CRI / baseline / report screens and the baseline approval gate.

Per included document (not rejected, not superseded by a newer version), from its latest extraction job in
the sprint:

  complete       the job completed and every text chunk was read (or completed before chunk checks existed:
                 `checked` is then false)
  partial        the job completed, but a chunk failed or was skipped, pages were unreadable or the file
                 could not be read -- some of the document's facts may be missing
  failed         the latest job failed or was stopped
  active         queued, running or retrying
  not_processed  no extraction job yet

Only "complete" counts as processed. The five counts always add up to `counts.total` (the current documents).

Documents that are not current are listed separately in `excluded` / `excluded_documents`, never in the counts:

  earlier_version  replaced by a newer version of the same file in this sprint (kept, with its facts, as history)
  rejected         rejected by a reviewer

Nothing here changes data.
"""
from collections import Counter

from apps.documents.models import Document

from ..models import ExtractionJob

COMPLETE, PARTIAL, FAILED, ACTIVE, NOT_PROCESSED = 'complete', 'partial', 'failed', 'active', 'not_processed'
STATES = (COMPLETE, PARTIAL, FAILED, ACTIVE, NOT_PROCESSED)
LABELS = {
    COMPLETE: 'Fully processed',
    PARTIAL: 'Partially processed - some content was not read',
    FAILED: 'Failed or stopped',
    ACTIVE: 'Processing',
    NOT_PROCESSED: 'Not processed yet',
}
_ACTIVE = (ExtractionJob.Status.PENDING, ExtractionJob.Status.RUNNING, ExtractionJob.Status.RETRYING)
EARLIER_VERSION, REJECTED = 'earlier_version', 'rejected'
EXCLUDED_NOTE = 'excluded from current-document counts'


def included_documents(sprint):
    return (sprint.documents.exclude(status=Document.Status.REJECTED).filter(superseded_at__isnull=True)
            .order_by('original_filename', 'created_at'))


def excluded_documents(sprint):
    """The sprint's documents that are not current: rejected, or superseded by a newer version."""
    from django.db.models import Q
    return (sprint.documents.filter(Q(status=Document.Status.REJECTED) | Q(superseded_at__isnull=False))
            .prefetch_related('newer_versions').order_by('original_filename', 'version_number', 'created_at'))


def _excluded_row(doc):
    """Why a non-current document is left out. A rejected file is "rejected" even if a later version exists."""
    if doc.status == Document.Status.REJECTED:
        state, label = REJECTED, f'Rejected \u2014 {EXCLUDED_NOTE}.'
        replaced_by = None
    else:
        newer = sorted(doc.newer_versions.all(), key=lambda d: d.version_number)
        replaced_by = newer[0].version_number if newer else None
        state = EARLIER_VERSION
        label = (f'Earlier version \u2014 replaced by version {replaced_by}; {EXCLUDED_NOTE}.' if replaced_by
                 else f'Earlier version \u2014 replaced by a newer version; {EXCLUDED_NOTE}.')
    return {'document_id': str(doc.id), 'filename': doc.original_filename or doc.title, 'state': state,
            'label': label, 'version_number': doc.version_number, 'replaced_by_version': replaced_by}


def _state(job):
    if job is None:
        return NOT_PROCESSED
    if job.status in _ACTIVE:
        return ACTIVE
    if job.status == ExtractionJob.Status.COMPLETED:
        return PARTIAL if job.completeness == ExtractionJob.Completeness.PARTIAL else COMPLETE
    return FAILED  # failed or cancelled


def processing_summary(sprint):
    """{complete, counts: {state: n, total}, documents, incomplete, excluded: {earlier_version, rejected, total},
    excluded_documents}. `counts` covers current documents only; `excluded*` the rest of the sprint's documents."""
    docs = list(included_documents(sprint))
    latest = {}
    for job in ExtractionJob.objects.filter(sprint=sprint, document__in=docs).order_by('created_at'):
        latest[job.document_id] = job  # oldest first, so the newest wins
    rows = []
    for doc in docs:
        job = latest.get(doc.id)
        state = _state(job)
        rows.append({
            'document_id': str(doc.id), 'filename': doc.original_filename or doc.title,
            'state': state, 'label': LABELS[state],
            'job_id': str(job.id) if job else None, 'job_status': job.status if job else None,
            'checked': bool(job and job.completeness), 'chunks_total': job.chunks_total if job else 0,
            'chunks_completed': job.chunks_completed if job else 0,
            'warnings': list(job.extraction_warnings or []) if job else [],
            'error': (job.error_message or '')[:500] if job and state == FAILED else '',
        })
    counts = Counter(r['state'] for r in rows)
    incomplete = [r for r in rows if r['state'] != COMPLETE]
    excluded = [_excluded_row(d) for d in excluded_documents(sprint)]
    excluded_counts = Counter(r['state'] for r in excluded)
    return {
        'complete': not incomplete,
        'counts': {**{s: counts.get(s, 0) for s in STATES}, 'total': len(rows)},
        'documents': rows,
        'incomplete': incomplete,
        'excluded': {EARLIER_VERSION: excluded_counts.get(EARLIER_VERSION, 0),
                     REJECTED: excluded_counts.get(REJECTED, 0), 'total': len(excluded)},
        'excluded_documents': excluded,
    }


def describe(summary):
    """One sentence: "2 of 14 documents are not fully processed (1 partial, 1 failed)." or ''."""
    if summary['complete']:
        return ''
    c = summary['counts']
    parts = [f'{c[s]} {name}' for s, name in ((PARTIAL, 'partial'), (FAILED, 'failed'), (ACTIVE, 'still processing'),
                                              (NOT_PROCESSED, 'not processed')) if c[s]]
    return (f'{len(summary["incomplete"])} of {c["total"]} included document(s) are not fully processed '
            f'({", ".join(parts)}).')


def snapshot(summary):
    """The compact form stored with a baseline decision or a report (no per-document warnings list)."""
    return {'complete': summary['complete'], 'counts': summary['counts'], 'description': describe(summary),
            'incomplete': [{k: r[k] for k in ('document_id', 'filename', 'state', 'label')}
                           for r in summary['incomplete']]}
