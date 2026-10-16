import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, acks_late=True)
def draft_source_requirements(self, version_id, actor='requirement_drafting'):
    """Sections + AI requirement drafts for one source version.

    Takes a router slot in multi_router mode, exactly like an extraction job,
    so drafting shares the same capacity limits and never bypasses the mode.
    """
    from apps.extraction.services.router_pool import get_router_pool, use_lease

    from .models import SourceVersion
    from .services.requirement_drafting import draft_version

    # Claim: only a queued version starts, so a duplicate message (acks_late)
    # or a second click can never draft the same version twice at once.
    claimed = SourceVersion.objects.filter(pk=version_id, extraction_status=SourceVersion.Extraction.QUEUED).update(
        extraction_status=SourceVersion.Extraction.RUNNING, extraction_note='')
    if not claimed:
        logger.info('benchmarks.drafting.skipped version=%s (not queued)', version_id)
        return None
    version = SourceVersion.objects.select_related('document').get(pk=version_id)

    pool = lease = None
    try:
        pool = get_router_pool()
        if pool is not None:
            lease = pool.acquire()
        with use_lease(lease):
            kept, dropped = draft_version(version, actor=actor)
        version.extraction_status = SourceVersion.Extraction.DONE
        version.extraction_note = (f'{kept} draft requirement(s) ready for review'
                                   + (f'; {dropped} AI suggestion(s) dropped because their quote was not in the source.'
                                      if dropped else '.'))
    except Exception as exc:
        logger.exception('benchmarks.drafting.failed version=%s', version_id)
        version.extraction_status, version.extraction_note = SourceVersion.Extraction.FAILED, str(exc)[:2000]
    finally:
        if lease is not None:
            pool.release(lease)
    version.save(update_fields=['extraction_status', 'extraction_note', 'updated_at'])
    return str(version.pk)


@shared_task(acks_late=False, ignore_result=True)
def run_source_watcher(trigger='schedule'):
    """Stage 4: daily check of every enabled source feed. Records snapshots and
    change events only; it never edits a source, benchmark or release."""
    from django.core.cache import cache

    from .services.watcher import run_watcher

    # One run at a time, even if beat and a manual "check all" overlap.
    if not cache.add('benchmarks:watcher:lock', trigger, timeout=2 * 60 * 60):
        logger.info('benchmarks.watcher.skipped (another run is in progress)')
        return None
    try:
        run, results = run_watcher(trigger=trigger)
        logger.info('benchmarks.watcher.done run=%s feeds=%s changes=%s status=%s',
                    run.pk, run.feeds_checked, run.changes_detected, run.status)
        return str(run.pk)
    finally:
        cache.delete('benchmarks:watcher:lock')


@shared_task(acks_late=False, ignore_result=True)
def ai_draft_benchmark(benchmark_id):
    """AI-write one draft benchmark's content (services/ai_drafting.py) on a leased
    router (retrying once on another router if the call fails), so several of
    these run side by side across the router pool."""
    from .models import Benchmark
    from .services.ai_drafting import draft_with_router

    benchmark = Benchmark.objects.select_related('pillar', 'capability').filter(pk=benchmark_id).first()
    if benchmark is None:
        return None
    try:
        result = draft_with_router(benchmark)
        logger.info('benchmarks.ai_draft.task code=%s ok=%s %s', result.code, result.ok, result.detail)
    except Exception:
        logger.exception('benchmarks.ai_draft.task_failed benchmark=%s', benchmark_id)
    return None
