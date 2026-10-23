"""What the active AI processing mode looks like right now -- shared by the
worker startup log, the Django system check and `manage.py ai_mode_status`.

Never returns or logs an API key: routers are described by label and URL,
and a key only as present / missing.
"""
import time
from urllib.parse import urlsplit

from django.conf import settings

from config.ai_processing_mode import MULTI_ROUTER


def describe():
    """The configured mode, as plain data (no secrets)."""
    from .router_pool import configured_routers, processing_mode

    mode = processing_mode()
    info = {
        'mode': mode,
        'worker_concurrency': settings.CELERY_WORKER_CONCURRENCY,
        'worker_pool': getattr(settings, 'CELERY_WORKER_POOL', 'default'),
        'model': settings.AI_MODEL or settings.OPENAI_EXTRACTION_MODEL or '(provider default)',
        'routers': [],
    }
    if mode == MULTI_ROUTER and settings.AI_ROUTER_MODEL:
        info['model'] = settings.AI_ROUTER_MODEL
    if mode == MULTI_ROUTER:
        info['slots_per_router'] = settings.AI_ROUTER_MAX_CONCURRENT
        info['routers'] = [
            {'label': r.label, 'base_url': r.base_url, 'key': 'set' if r.api_key else 'MISSING'}
            for r in configured_routers()
        ]
    else:
        info['endpoint'] = urlsplit(settings.AI_BASE_URL).netloc if settings.AI_BASE_URL else '(provider API)'
        info['key'] = 'set' if (settings.AI_API_KEY or settings.OPENAI_API_KEY) else 'MISSING'
    return info


def summary_line(info=None):
    info = info or describe()
    if info['mode'] == MULTI_ROUTER:
        routers = ', '.join(r['label'] for r in info['routers'])
        return (f"mode={info['mode']} routers={len(info['routers'])} [{routers}] "
                f"slots_per_router={info['slots_per_router']} worker_concurrency={info['worker_concurrency']} "
                f"pool={info['worker_pool']} model={info['model']}")
    return (f"mode={info['mode']} endpoint={info['endpoint']} key={info['key']} "
            f"worker_concurrency={info['worker_concurrency']} pool={info['worker_pool']} model={info['model']}")


def router_model():
    return settings.AI_ROUTER_MODEL or settings.AI_MODEL or settings.OPENAI_EXTRACTION_MODEL


def configuration_problems():
    """(errors, warnings) for the active mode -- plain strings, used by the system check."""
    from .router_pool import configured_routers, processing_mode

    errors, warnings = [], []
    try:
        mode = processing_mode()
    except Exception as exc:
        return [str(exc)], []
    concurrency = settings.CELERY_WORKER_CONCURRENCY
    if mode == MULTI_ROUTER:
        try:
            routers = configured_routers()
        except Exception as exc:  # key count mismatch
            return [str(exc)], []
        if not routers:
            errors.append('AI_PROCESSING_MODE=multi_router but AI_ROUTER_URLS is empty.')
        if any(not r.api_key for r in routers):
            errors.append('A router has no API key (AI_ROUTER_API_KEYS).')
        if not (settings.AI_ROUTER_MODEL or settings.AI_MODEL or settings.OPENAI_EXTRACTION_MODEL):
            errors.append('multi_router mode needs AI_ROUTER_MODEL or AI_MODEL (the same model on every router).')
        slots = len(routers) * max(1, settings.AI_ROUTER_MAX_CONCURRENT)
        if routers and concurrency != slots:
            warnings.append(
                f'CELERY_WORKER_CONCURRENCY={concurrency} but the routers have {slots} slots '
                f'({len(routers)} x {settings.AI_ROUTER_MAX_CONCURRENT}); '
                + ('some slots will stay unused.' if concurrency < slots else 'extra workers will wait for a free slot.')
            )
        # Four endpoints are not four quotas when they bill the same account. Keys are compared, never shown.
        keys = [r.api_key for r in routers if r.api_key]
        if len(keys) > 1 and len(set(keys)) < len(keys):
            shared = len(keys) - len(set(keys)) + 1
            warnings.append(
                f'{shared} routers use the same API key: they share one provider quota/credit, so when it runs '
                'out they run out together and failover cannot help. Give each router its own account/key '
                'for independent quotas.')
    else:
        # AI_ROUTER_URLS may stay filled in: single mode simply doesn't use it.
        if not (settings.AI_API_KEY or settings.OPENAI_API_KEY):
            warnings.append('single mode has no AI_API_KEY; extraction will fail until one is set.')
    return errors, warnings


def check_router(router, timeout=5):
    """One router's health: GET {base_url}/models -- reachable, and (routers) the
    model listed. Does not prove the key works (see below). Never returns the key."""
    import httpx

    started = time.monotonic()
    try:
        resp = httpx.get(router.base_url.rstrip('/') + '/models',
                         headers={'Authorization': f'Bearer {router.api_key}'}, timeout=timeout)
        ok = resp.status_code == 200
        detail = 'ok' if ok else f'HTTP {resp.status_code}'
        if resp.status_code in (401, 403):
            detail += ' (key rejected)'
        model_listed = None
        if ok:
            try:
                ids = [m.get('id') for m in resp.json().get('data', [])]
                expected = router_model()
                model_listed = expected in ids if expected and router.index else None
            except ValueError:
                pass
        # The key is NOT verified here: some routers (9router) serve /models without
        # one, and any completion request -- even for a made-up model -- is forwarded
        # upstream, which spends quota and can trip provider cooldowns.
    except Exception as exc:
        ok, detail, model_listed = False, f'unreachable ({type(exc).__name__})', None
    # Credit is never claimed: a /models answer says nothing about the account's remaining balance, and no
    # supported balance-check API is called. Out-of-credit is known only from a real request's answer
    # (router_pool.mark_exhausted), and shown as such.
    return {'label': router.label, 'ok': ok, 'detail': detail, 'model_listed': model_listed,
            'ms': round((time.monotonic() - started) * 1000), 'credit': 'not verified'}


def exhausted_routers(pool):
    """{router label: {reason, since}} for routers out of quota/credit, or None if Redis is unreachable."""
    try:
        return pool.exhausted()
    except Exception:
        return None


def slot_usage(pool):
    """{router label: (busy slots, cooling down)} from Redis, or None if Redis is unreachable."""
    try:
        client = pool._client()
        out = {}
        for r in pool.routers:
            busy = sum(1 for v in client.mget([pool._slot_key(r, s) for s in range(pool.max_concurrent)]) if v)
            out[r.label] = (busy, bool(client.get(pool._cooldown_key(r))))
        return out
    except Exception:
        return None
