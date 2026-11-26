"""Tagging after extraction (evidence map step 3). Off unless EVIDENCE_MAP_AUTO_TAG.

When a sprint's extraction jobs have all finished, one tagging pass is queued for it. The pass tags only pages with no
tagged row for the current map version and model (tagging.plan), so a re-upload or a new document costs only its new
pages. One pass per sprint at a time: a running job younger than EVIDENCE_MAP_STALE_SECONDS blocks another.

Two follow-ons, each off unless its setting is on (26 Nov):
- EVIDENCE_MAP_AUTO_CHECK: a completed tagging pass is followed by the requirement check on the same map
  (requirement_check.py), capped at EVIDENCE_MAP_CHECK_MAX_COST_USD.
- EVIDENCE_MAP_AUTO_LEARN: a completed assessment adds its credited quotations to the map (learn.py), on the run's
  own map version in map mode, else on the configured shape's. No model calls."""
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
    if job.status == job.Status.COMPLETED and getattr(settings, 'EVIDENCE_MAP_AUTO_CHECK', False):
        check_after_tagging(sprint, job)
    return str(job.pk)


def check_after_tagging(sprint, job):
    """The requirement check on the map a tagging job has just completed. Never raises."""
    from . import requirement_check
    try:
        check = requirement_check.run(sprint, map_version=job.map_version, model=job.model,
                                      max_cost_usd=getattr(settings, 'EVIDENCE_MAP_CHECK_MAX_COST_USD', 0.5))
        logger.info('evidence_map.check sprint=%s job=%s status=%s', sprint.pk, check.pk, check.status)
        return check
    except Exception:
        logger.exception('evidence_map.check failed sprint=%s', sprint.pk)
        return None


def queue_learning(run):
    """Queue learning from a completed run if EVIDENCE_MAP_AUTO_LEARN is on. Never raises."""
    if not getattr(settings, 'EVIDENCE_MAP_AUTO_LEARN', False):
        return False
    try:
        run_id = str(run.pk)
        transaction.on_commit(lambda: learn_from_run.delay(run_id))
        return True
    except Exception:
        logger.exception('evidence_map.queue_learning failed run=%s', run.pk)
        return False


def learning_target(run):
    """(map version, model) a run's credits go to: the run's own map in map mode, else the configured shape's map
    with the model of its latest job. (None, None) when there is no such map."""
    from . import spec
    from .models import MapJob
    policy = (run.inputs or {}).get('retrieval_policy') or {}
    if policy.get('map_version') and policy.get('map_model'):
        return policy['map_version'], policy['map_model']
    version = spec.map_version(getattr(settings, 'EVIDENCE_MAP_SHAPE', 'one'), *spec.rubric_sources())
    model = MapJob.objects.filter(sprint_id=run.sprint_id, map_version=version).order_by(
        '-started_at').values_list('model', flat=True).first()
    return (version, model) if model else (None, None)


@shared_task(ignore_result=True)
def learn_from_run(run_id):
    from apps.scoring.models import CapabilityRun
    from . import learn
    try:
        run = CapabilityRun.objects.get(pk=run_id)
        version, model = learning_target(run)
        if version is None:
            logger.info('evidence_map.learn run=%s: no map to add to', run_id)
            return 0
        added, counts = learn.from_run(run_id, map_version=version, model=model)
        logger.info('evidence_map.learn run=%s version=%s added=%s counts=%s', run_id, version, added, dict(counts))
        return added
    except Exception:
        logger.exception('evidence_map.learn failed run=%s', run_id)
        return 0
