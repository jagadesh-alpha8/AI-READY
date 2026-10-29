"""Put an AI router back into rotation after its provider's quota / credit was restored.

    python manage.py ai_router_reactivate                  # list the routers marked out of credit
    python manage.py ai_router_reactivate 2                # reactivate router2 (by number or label)
    python manage.py ai_router_reactivate --all            # reactivate every router
    python manage.py ai_router_reactivate 2 --resume       # ...and re-queue documents waiting for a router now

A router is marked out of credit only when a real request is refused for it (router_pool.mark_exhausted); no
health check can see a balance, so reactivating is a deliberate admin step. Never prints a key.
"""
from django.core.management.base import BaseCommand, CommandError

from ...services.router_pool import get_router_pool


class Command(BaseCommand):
    help = 'Reactivate AI routers marked out of quota/credit (lists them without arguments).'

    def add_arguments(self, parser):
        parser.add_argument('routers', nargs='*', help='Router numbers (1, 2, ...) or labels (router2).')
        parser.add_argument('--all', action='store_true', help='Reactivate every router.')
        parser.add_argument('--resume', action='store_true',
                            help='Re-queue documents that are waiting for a router, now instead of at their next check.')

    def handle(self, *args, **opts):
        pool = get_router_pool()
        if pool is None:
            raise CommandError('AI_PROCESSING_MODE is not multi_router: there are no routers to reactivate.')
        try:
            exhausted = pool.exhausted()
        except Exception as exc:
            raise CommandError(f'Redis is unreachable, so router marks cannot be read or cleared ({exc}).')
        if not opts['all'] and not opts['routers']:
            if not exhausted:
                self.stdout.write('No router is marked out of credit.')
            for label, info in exhausted.items():
                self.stdout.write(f'{label}: out of credit since {info.get("since", "?")} -- {info.get("reason", "")}')
            return
        chosen = pool.routers if opts['all'] else [self._find(pool, name) for name in opts['routers']]
        for router in chosen:
            was = pool.reactivate(router)
            self.stdout.write(f'{router.label}: {"reactivated" if was else "was not marked out of credit"}.')
        # The per-key "out of quota / credit" marks other workers check before calling (services/rate_limit.py).
        from ...services import rate_limit
        try:
            cleared = rate_limit.clear_exhausted()
            if cleared:
                self.stdout.write(f'Cleared {cleared} shared out-of-credit mark(s).')
        except Exception as exc:
            self.stderr.write(f'Could not clear shared out-of-credit marks: {exc}')
        if opts['resume']:
            self.stdout.write(f'Re-queued {self._resume()} document(s) waiting for a router.')

    @staticmethod
    def _find(pool, name):
        name = str(name).strip().lower()
        for router in pool.routers:
            if name in (str(router.index), f'router{router.index}', router.label.lower()):
                return router
        raise CommandError(f'No router {name!r}; routers: {", ".join(r.label for r in pool.routers)}.')

    @staticmethod
    def _resume():
        """Dispatch the jobs whose last attempt is waiting for a router (a new task id makes the scheduled
        check a no-op: tasks.py skips a stale message)."""
        from ...models import ExtractionJob
        from ...views import dispatch_job

        count = 0
        for job in ExtractionJob.objects.filter(status=ExtractionJob.Status.RETRYING):
            if (job.attempts or [{}])[-1].get('outcome') == 'waiting':
                dispatch_job(job)
                count += 1
        return count
