"""Tagging after extraction (evidence map step 3). Off unless EVIDENCE_MAP_AUTO_TAG.

When a sprint's extraction jobs have all finished, one tagging pass is queued for it. The pass tags only pages with no
tagged row for the current map version and model (tagging.plan), so a re-upload or a new document costs only its new
pages. One pass per sprint at a time: a running job younger than EVIDENCE_MAP_STALE_SECONDS blocks another."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def running_job(sprint):
    from .models import MapJob
    fresh = timezone.now() - timedelta(seconds=getattr(settings, 'EVIDENCE_MAP_STALE_SECONDS', 6 * 3600))
    return MapJob.objects.filter(sprint=sprint, status=MapJob.Status.RUNNING, started_at__gte=fresh).first()


def queue_after_extraction(sprint):
    """Queue a tagging pass for the sprint if the setting is on, no extraction job is still active and no pass is
    running. Never raises: tagging must not disturb extraction."""
    if not getattr(settings, 'EVIDENCE_MAP_AUTO_TAG', False):
        return False
    try:
        from apps.extraction.models import ExtractionJob
        active = sprint.extraction_jobs.filter(status__in=[ExtractionJob.Status.PENDING, ExtractionJob.Status.RUNNING,
                                                           ExtractionJob.Status.RETRYING]).exists()
        if active or running_job(sprint) is not None:
            return False
        sprint_id = str(sprint.pk)
        transaction.on_commit(lambda: tag_sprint.delay(sprint_id))
        return True
    except Exception:
        logger.exception('evidence_map.queue failed sprint=%s', sprint.pk)
        return False


@shared_task(ignore_result=True)
def tag_sprint(sprint_id):
    """One tagging pass over the sprint's untagged pages, at the configured shape, concurrency and spend cap."""
    from apps.sprints.models import Sprint
    from . import tagging
    shape = getattr(settings, 'EVIDENCE_MAP_SHAPE', 'one')
    # Check and claim under the sprint's row lock: two extraction jobs finishing together queue two tasks, and the
    # check alone (before any job row existed) let both start a pass, doubling the spend.
    with transaction.atomic():
        sprint = Sprint.objects.select_for_update().filter(pk=sprint_id).first()
        if sprint is None or running_job(sprint) is not None:
            return None
        claimed = tagging.start_job(sprint, shape=shape)
    job = tagging.run(sprint, shape=shape, concurrency=getattr(settings, 'EVIDENCE_MAP_CONCURRENCY', 4), job=claimed)
    logger.info('evidence_map.tag_sprint sprint=%s job=%s status=%s tagged=%s failed=%s', sprint_id, job.pk,
                job.status, job.pages_tagged, job.pages_failed)
    return str(job.pk)
