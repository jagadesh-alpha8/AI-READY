"""Bring extraction jobs back after a worker, Redis or server interruption. PostgreSQL is the source of truth.

Run every EXTRACTION_RECOVERY_INTERVAL_SECONDS by celery beat (tasks.recover_extraction_jobs), once shortly
after a worker starts, and on demand with `manage.py recover_extraction_jobs [--dry-run]`.

A job is handed to the broker again (views.dispatch_job: a NEW task id, so any old message for it that still
turns up is skipped as stale by tasks.run_extraction_job) only when it is one of:

  never_published  pending with no task id, older than EXTRACTION_RECOVERY_GRACE_SECONDS (the request that
                   created it died before publishing)
  message_lost     pending / retrying whose task id is in neither the broker queue nor its unacked set, and
                   which is overdue (queued or due more than EXTRACTION_RECOVERY_PENDING_SECONDS ago) -- e.g.
                   Redis restarted without persistence
  worker_lost      running, but no heartbeat for EXTRACTION_STALE_SECONDS (its worker died or was killed)
  worker_gone      running on a worker that no longer answers a ping, with no heartbeat for
                   EXTRACTION_RECOVERY_DEAD_WORKER_SECONDS (e.g. the container was replaced by a deploy)

Completed, failed and stopped jobs are never touched. A queued job whose message is still in the broker is
left alone however long it waits (a long queue is not a lost message). When the broker cannot be read, only
`never_published` and `worker_lost` are recovered -- never a guess about lost messages.

Two workers never process one document at once: a recovered running job can only be claimed once its heartbeat
is stale (tasks._claim), and the old worker, if it was only slow, sees the new task id at its next checkpoint
and abandons the job (pipeline._is_cancelled -> ExtractionSuperseded). Pages and chunks it already saved are
reused by the new attempt, so nothing is redone or duplicated.
"""
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

_LOCK_KEY = 'aios:extraction-recovery-lock'


def _redis():
    import redis
    return redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=5, socket_connect_timeout=5)


def broker_task_ids(client=None):
    """Task ids the broker still holds for the extraction queues (waiting, or reserved by a worker and not yet
    acknowledged -- including scheduled retries). None when the broker can't be read."""
    try:
        client = client or _redis()
        ids = set()
        queues = {settings.EXTRACTION_QUEUE or 'celery', settings.OCR_QUEUE or 'celery'}
        for queue in queues:
            # kombu's redis transport keeps a priority's messages under '<queue>\x06\x16<priority>'.
            for key in [queue] + [f'{queue}\x06\x16{p}' for p in (3, 6, 9)]:
                for raw in client.lrange(key, 0, -1):
                    task_id = _task_id(raw)
                    if task_id:
                        ids.add(task_id)
        for raw in client.hvals('unacked'):
            try:
                message = json.loads(raw)[0]
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            task_id = _task_id(message)
            if task_id:
                ids.add(task_id)
        return ids
    except Exception as exc:
        logger.warning('extraction.recovery.broker_unreadable error=%s', exc)
        return None


def _task_id(raw):
    try:
        message = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        return (message.get('headers') or {}).get('id')
    except (TypeError, ValueError, AttributeError):
        return None


def live_workers():
    """Hostnames of the Celery workers that answer a ping, or None when unknown (no reply, broker down, or the
    solo pool, whose busy worker cannot reply)."""
    if (getattr(settings, 'CELERY_WORKER_POOL', '') or '').lower() == 'solo':
        return None
    try:
        from config.celery import app
        replies = app.control.ping(timeout=2.0) or []
    except Exception as exc:
        logger.warning('extraction.recovery.ping_failed error=%s', exc)
        return None
    names = {name for reply in replies for name in reply}
    return names or None


def _candidates(now, in_broker):
    from ..models import ExtractionJob

    S = ExtractionJob.Status
    grace = now - timedelta(seconds=settings.EXTRACTION_RECOVERY_GRACE_SECONDS)
    overdue = now - timedelta(seconds=settings.EXTRACTION_RECOVERY_PENDING_SECONDS)
    stale = now - timedelta(seconds=settings.EXTRACTION_STALE_SECONDS)
    found = []
    for job in ExtractionJob.objects.filter(status=S.PENDING, celery_task_id='', created_at__lt=grace):
        found.append((job, 'never_published'))
    for job in ExtractionJob.objects.filter(status=S.RUNNING).filter(
            Q(heartbeat_at__lt=stale) | Q(heartbeat_at__isnull=True, updated_at__lt=stale)):
        found.append((job, 'worker_lost'))
    # Faster after a deploy / restart: a running job whose worker no longer answers at all (the worker list came
    # back, and its hostname is not on it) is recovered after EXTRACTION_RECOVERY_DEAD_WORKER_SECONDS instead of
    # the full stale window. Not with the solo pool, where a busy worker cannot answer.
    alive = live_workers()
    if alive:
        dead_after = now - timedelta(seconds=settings.EXTRACTION_RECOVERY_DEAD_WORKER_SECONDS)
        listed = {job.id for job, _reason in found}
        for job in ExtractionJob.objects.filter(status=S.RUNNING, heartbeat_at__lt=dead_after).exclude(worker=''):
            if job.id not in listed and job.worker not in alive:
                found.append((job, 'worker_gone'))
    # Pending with a heartbeat: its pages were being read on the OCR queue (tasks.read_document_pages).
    for job in ExtractionJob.objects.filter(status=S.PENDING, heartbeat_at__lt=stale):
        found.append((job, 'worker_lost'))
    if in_broker is not None:
        lost = ExtractionJob.objects.exclude(celery_task_id='').filter(
            Q(status=S.PENDING, dispatched_at__lt=overdue)
            | Q(status=S.PENDING, dispatched_at__isnull=True, updated_at__lt=overdue)
            | Q(status=S.RETRYING, next_retry_at__lt=overdue)
            | Q(status=S.RETRYING, next_retry_at__isnull=True, updated_at__lt=overdue))
        for job in lost:
            if job.celery_task_id not in in_broker:
                found.append((job, 'message_lost'))
    return found[:settings.EXTRACTION_RECOVERY_BATCH]


def _still_eligible(job, reason, now):
    """Re-checked on the locked row: the job may have moved on since it was listed."""
    from ..models import ExtractionJob

    S = ExtractionJob.Status
    stale = now - timedelta(seconds=settings.EXTRACTION_STALE_SECONDS)
    if reason == 'never_published':
        return job.status == S.PENDING and not job.celery_task_id
    if reason == 'worker_gone':
        return job.status == S.RUNNING
    if reason == 'worker_lost':
        if job.status == S.PENDING:
            return bool(job.heartbeat_at and job.heartbeat_at < stale)
        return job.status == S.RUNNING and ((job.heartbeat_at and job.heartbeat_at < stale)
                                            or (job.heartbeat_at is None and job.updated_at < stale))
    return job.status in (S.PENDING, S.RETRYING)


def recover(*, dry_run=False, now=None):
    """Re-dispatch the jobs listed above. Returns [{job_id, document, reason, action}]."""
    from ..models import ExtractionJob
    from ..tasks import _end_attempt
    from ..views import dispatch_job

    now = now or timezone.now()
    lock = None
    if not dry_run:
        try:
            lock = _redis()
            if not lock.set(_LOCK_KEY, '1', nx=True, ex=max(60, settings.EXTRACTION_RECOVERY_INTERVAL_SECONDS)):
                logger.info('extraction.recovery.skipped reason=another_run_in_progress')
                return []
        except Exception as exc:  # Redis down: the per-row locks below still keep runs apart
            logger.warning('extraction.recovery.lock_unavailable error=%s', exc)
            lock = None
    try:
        report = []
        for job, reason in _candidates(now, broker_task_ids()):
            entry = {'job_id': str(job.id), 'document': job.document_id and str(job.document_id), 'reason': reason,
                     'status': job.status, 'action': 'would re-queue' if dry_run else 're-queued'}
            if dry_run:
                report.append(entry)
                continue
            with transaction.atomic():
                locked = (ExtractionJob.objects.select_for_update(skip_locked=True)
                          .filter(id=job.id).first())
                if locked is None or not _still_eligible(locked, reason, now):
                    continue
                if reason in ('worker_lost', 'worker_gone'):
                    _end_attempt(locked, 'recovered', 'The worker running this document stopped responding; '
                                                      'continuing on another worker.')
                    # Running -> retrying: only now can another worker claim it. A pending one (its pages were
                    # being read) stays pending, so its page reading starts again (reusing pages already read).
                    ExtractionJob.objects.filter(id=locked.id).update(
                        status=(ExtractionJob.Status.RETRYING if locked.status == ExtractionJob.Status.RUNNING
                                else ExtractionJob.Status.PENDING),
                        heartbeat_at=None, updated_at=now,
                        error_message='Recovered: its worker stopped responding. Continuing where it left off.')
                elif reason == 'message_lost':
                    _end_attempt(locked, 'recovered', 'Its queue message was lost (broker restart); queued again.')
                locked.refresh_from_db()
            dispatch_job(locked)
            logger.warning('extraction.recovery.requeued job_id=%s reason=%s', job.id, reason)
            report.append(entry)
        return report
    finally:
        if lock is not None:
            try:
                lock.delete(_LOCK_KEY)
            except Exception:
                pass
