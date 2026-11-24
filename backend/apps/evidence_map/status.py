"""The sprint's evidence map at a glance, for the Assessment page (its own endpoint: never in the run detail).

Read from the latest tagging job for the current map version, not from the pages: building the pages' text re-renders
every page, which is what made the review count slow (issue 60)."""
from django.conf import settings

from . import spec
from .models import MapJob

#: Below this share of readable pages tagged, the Assessment page warns (starting value in the specification).
WARN_BELOW = 0.95


def current_version():
    rubric, profiles, parts = spec.rubric_sources()
    return spec.map_version(getattr(settings, 'EVIDENCE_MAP_SHAPE', 'one'), rubric, profiles, parts)


def status(sprint):
    """{'used_by_runs', 'map_version', 'job', 'tagged_share', 'documents_changed', 'warning'}.

    warning: None, or one of no_map (never tagged at this version), tagging_in_progress, map_out_of_date (a document's
    extraction finished after the last pass started), map_incomplete (under WARN_BELOW of the pages tagged, or the last
    pass failed or stopped at its spend cap). Warnings never block a run."""
    from apps.extraction.models import ExtractionJob
    version = current_version()
    used = getattr(settings, 'CAPABILITY_RETRIEVAL_MODE', 'bm25') == 'map'
    job = MapJob.objects.filter(sprint=sprint, map_version=version).order_by('-started_at').first()
    out = {'used_by_runs': used, 'map_version': version, 'job': None, 'tagged_share': None,
           'documents_changed': False, 'warning': None, 'warn_below': WARN_BELOW}
    if job is None:
        out['warning'] = 'no_map'
        return out
    readable = max(0, job.pages_total)
    done_before = max(0, job.pages_total - job.pages_to_tag)
    share = (done_before + job.pages_tagged) / readable if readable else 1.0
    out['job'] = {'id': str(job.pk), 'status': job.status, 'model': job.model, 'shape': job.shape,
                  'pages_total': job.pages_total, 'pages_to_tag': job.pages_to_tag, 'pages_tagged': job.pages_tagged,
                  'pages_failed': job.pages_failed, 'pages_unreadable': job.pages_skipped,
                  'chunks_total': job.chunks_total, 'chunks_done': job.chunks_done, 'spend_usd': str(job.spend_usd),
                  'started_at': job.started_at.isoformat(),
                  'finished_at': job.finished_at.isoformat() if job.finished_at else None}
    out['tagged_share'] = round(share, 4)
    out['documents_changed'] = ExtractionJob.objects.filter(
        sprint=sprint, status=ExtractionJob.Status.COMPLETED, completed_at__gt=job.started_at).exists()
    if job.status == MapJob.Status.RUNNING:
        out['warning'] = 'tagging_in_progress'
    elif out['documents_changed']:
        out['warning'] = 'map_out_of_date'
    elif job.status != MapJob.Status.COMPLETED or share < WARN_BELOW:
        out['warning'] = 'map_incomplete'
    return out
