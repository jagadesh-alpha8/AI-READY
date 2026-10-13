"""Health check for the active AI processing mode.

    python manage.py ai_mode_status            # mode, config problems, endpoint / router health, slots
    python manage.py ai_mode_status --workers  # + the running Celery workers and their concurrency

Exit code 1 when the configuration is invalid or an endpoint / router is down,
so a start script can stop on it. Never prints an API key.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from config.ai_processing_mode import MULTI_ROUTER

from ...services.processing_status import (
    check_router, configuration_problems, describe, router_model, slot_usage, summary_line,
)
from ...services.router_pool import Router, configured_routers, get_router_pool


class Command(BaseCommand):
    help = 'Show the active AI processing mode and check its endpoint(s).'

    def add_arguments(self, parser):
        parser.add_argument('--workers', action='store_true', help='Also ask running Celery workers (slower).')

    def handle(self, *args, **opts):
        healthy = True
        info = describe()
        self.stdout.write(f'AI processing: {summary_line(info)}')

        errors, warnings = configuration_problems()
        for msg in errors:
            self.stdout.write(self.style.ERROR(f'  config error: {msg}'))
        for msg in warnings:
            self.stdout.write(self.style.WARNING(f'  config warning: {msg}'))
        if errors:
            return self._exit(False)

        if info['mode'] == MULTI_ROUTER:
            pool = get_router_pool()
            slots = slot_usage(pool)
            if slots is None:
                self.stdout.write(self.style.WARNING('  Redis unreachable: slot usage unknown.'))
            for router in configured_routers():
                h = check_router(router)
                busy, cooling = slots.get(router.label, (0, False)) if slots else ('?', False)
                model = {True: 'model listed', False: f'MODEL {router_model()!r} NOT LISTED', None: ''}[h['model_listed']]
                line = (f'  {router.label:<28} {h["detail"]:<22} {h["ms"]:>5} ms  slots {busy}/{pool.max_concurrent}'
                        f'{"  cooling down" if cooling else ""}  {model}')
                ok = h['ok'] and h['model_listed'] is not False
                self.stdout.write(self.style.SUCCESS(line) if ok else self.style.ERROR(line))
                healthy &= ok
        elif settings.AI_BASE_URL:
            key = settings.AI_API_KEY or settings.OPENAI_API_KEY
            h = check_router(Router(index=0, base_url=settings.AI_BASE_URL, api_key=key))
            line = f'  endpoint {info["endpoint"]:<28} {h["detail"]:<22} {h["ms"]:>5} ms'
            self.stdout.write(self.style.SUCCESS(line) if h['ok'] else self.style.ERROR(line))
            healthy &= h['ok']
        else:
            self.stdout.write('  endpoint: provider API chosen from the key format (not probed).')

        if opts['workers']:
            self._workers()
        return self._exit(healthy)

    def _workers(self):
        from config.celery import app

        try:
            stats = app.control.inspect(timeout=5).stats() or {}
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'  workers: could not ask the broker ({exc})'))
            return
        if not stats:
            self.stdout.write(self.style.ERROR('  workers: none running.'))
            return
        for name, st in stats.items():
            pool = st.get('pool', {})
            self.stdout.write(f'  worker {name}: pool={str(pool.get("implementation", "?")).split(":")[-1]} '
                              f'concurrency={pool.get("max-concurrency", "?")}')
        if len(stats) > 1:
            self.stdout.write(self.style.WARNING(
                f'  {len(stats)} workers are running. After a mode switch only one should be -- '
                'stop the old one (switch-ai-mode.ps1 does this).'))

    def _exit(self, ok):
        self.stdout.write(self.style.SUCCESS('OK') if ok else self.style.ERROR('NOT HEALTHY'))
        if not ok:
            raise SystemExit(1)
