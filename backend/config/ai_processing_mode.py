"""The one switch between the two AI processing methods.

    AI_PROCESSING_MODE=single        one AI connection (AI_BASE_URL / AI_API_KEY),
                                     2 worker slots by default
    AI_PROCESSING_MODE=multi_router  the routers in AI_ROUTER_URLS, each running
                                     AI_ROUTER_MAX_CONCURRENT jobs at once
                                     (4 routers x 2 = 8 worker slots by default)

Read once in settings.py, which is why this module imports nothing from Django
settings. Everything else asks `settings.AI_PROCESSING_MODE`; nothing else
decides the mode.
"""
from django.core.exceptions import ImproperlyConfigured

SINGLE = 'single'
MULTI_ROUTER = 'multi_router'
MODES = (SINGLE, MULTI_ROUTER)
DEFAULT_MODE = SINGLE

#: Worker slots in single mode when CELERY_WORKER_CONCURRENCY isn't set.
SINGLE_MODE_WORKERS = 2


def parse_mode(raw):
    """Validated mode from the raw env value; blank means the default."""
    mode = (raw or '').strip().lower() or DEFAULT_MODE
    if mode not in MODES:
        raise ImproperlyConfigured(
            f'AI_PROCESSING_MODE={raw!r} is not valid. Use one of: {", ".join(MODES)} '
            f'(default {DEFAULT_MODE}).'
        )
    return mode


def router_count(urls):
    return len([u for u in (urls or '').split(',') if u.strip()])


def default_worker_concurrency(mode, *, routers, per_router):
    """Worker slots the mode needs: 2 for single, one per router slot otherwise."""
    if mode == MULTI_ROUTER:
        return max(1, routers) * max(1, per_router)
    return SINGLE_MODE_WORKERS
