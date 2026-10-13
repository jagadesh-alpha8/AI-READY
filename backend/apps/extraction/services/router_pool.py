"""Spreading extraction jobs across several OpenAI-compatible routers.

Used only when AI_PROCESSING_MODE=multi_router (config/ai_processing_mode.py).
In single mode `get_router_pool()` returns None and everything uses
`AI_BASE_URL` exactly as before.

With routers configured, `run_extraction_job` leases one router per job
(`RouterPool.acquire`) and runs the whole pipeline inside `use_lease(...)`;
`get_ai_service()` reads the active lease, so every AI call of that job goes
to the same router without the classifier / fact extractor / conflict
checker knowing routers exist. Same model (AI_MODEL), prompts and schema on
every router -- only the URL and key differ.

Leases are Redis keys shared by every worker process: each router has
`AI_ROUTER_MAX_CONCURRENT` slot keys, a job takes a free slot on the least
busy router, and releases it when done. Slots expire on their own
(`AI_ROUTER_LEASE_SECONDS`, extended on every AI call) so a killed worker
can't hold one forever. A router whose call failed with a recoverable error
is deprioritised for `AI_ROUTER_COOLDOWN_SECONDS`, so the Celery retry lands
on another router. If Redis can't be reached the pool still works, just
without the per-router limit (random router).
"""
import contextvars
import logging
import random
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ..exceptions import RecoverableExtractionError

logger = logging.getLogger(__name__)

_KEY_PREFIX = 'aiready:ai_router'

# Delete a slot only if this lease still owns it (it may have expired and
# been taken by another job).
_RELEASE_SCRIPT = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"


@dataclass(frozen=True)
class Router:
    index: int  # 1-based, as listed in AI_ROUTER_URLS
    base_url: str
    api_key: str

    @property
    def label(self):
        """What ExtractionJob.ai_router stores, e.g. 'router2 (localhost:20229)'."""
        return f'router{self.index} ({urlsplit(self.base_url).netloc})'


@dataclass
class Lease:
    router: Router
    slot_key: str = ''  # '' when Redis wasn't available
    token: str = ''
    pool: 'RouterPool' = None

    def touch(self):
        if self.pool is not None:
            self.pool.extend(self)


def _split(value):
    return [item.strip() for item in (value or '').split(',') if item.strip()]


def _normalize_url(url):
    """'http://localhost:20228' -> 'http://localhost:20228/v1' (the OpenAI SDK
    appends /chat/completions to the base URL)."""
    url = url.rstrip('/')
    return url if urlsplit(url).path else f'{url}/v1'


def configured_routers():
    """Routers from AI_ROUTER_URLS / AI_ROUTER_API_KEYS. AI_ROUTER_API_KEYS is
    one key per router (same order), or a single key shared by all; empty
    falls back to AI_API_KEY."""
    urls = _split(settings.AI_ROUTER_URLS)
    if not urls:
        return []
    keys = _split(settings.AI_ROUTER_API_KEYS)
    if not keys:
        keys = [settings.AI_API_KEY or settings.OPENAI_API_KEY]
    if len(keys) == 1:
        keys = keys * len(urls)
    if len(keys) != len(urls):
        raise ImproperlyConfigured(
            f'AI_ROUTER_API_KEYS has {len(keys)} keys for {len(urls)} AI_ROUTER_URLS -- '
            'give one key per router (same order), or a single key for all of them.'
        )
    return [
        Router(index=i, base_url=_normalize_url(url), api_key=key)
        for i, (url, key) in enumerate(zip(urls, keys), start=1)
    ]


class RouterPool:
    def __init__(self, routers, *, redis_client=None):
        self.routers = routers
        self.max_concurrent = max(1, settings.AI_ROUTER_MAX_CONCURRENT)
        self._redis = redis_client

    # -- redis ---------------------------------------------------------------

    def _client(self):
        if self._redis is None:
            import redis

            url = settings.AI_ROUTER_REDIS_URL or settings.CELERY_BROKER_URL
            self._redis = redis.Redis.from_url(url, socket_timeout=3, socket_connect_timeout=3)
        return self._redis

    def _slot_key(self, router, slot):
        return f'{_KEY_PREFIX}:{router.index}:slot:{slot}'

    def _cooldown_key(self, router):
        return f'{_KEY_PREFIX}:{router.index}:cooldown'

    # -- leasing -------------------------------------------------------------

    def acquire(self, *, avoid=''):
        """Lease a slot on the least busy router, waiting up to
        AI_ROUTER_WAIT_SECONDS for one to free up. `avoid` is the label of the
        router the previous attempt used -- picked only if nothing else is
        free. Raises RecoverableExtractionError if every slot stays busy."""
        deadline = time.monotonic() + settings.AI_ROUTER_WAIT_SECONDS
        while True:
            try:
                lease = self._try_acquire(avoid)
            except Exception as exc:  # Redis down: still spread the load, unlimited
                logger.warning('extraction.router.redis_unavailable error=%s', exc)
                return Lease(router=random.choice(self.routers))
            if lease is not None:
                return lease
            if time.monotonic() >= deadline:
                raise RecoverableExtractionError(
                    f'All {len(self.routers)} AI routers are busy '
                    f'({self.max_concurrent} jobs each); will retry.'
                )
            time.sleep(1 + random.random())

    def _try_acquire(self, avoid):
        client = self._client()
        slot_keys = [self._slot_key(r, s) for r in self.routers for s in range(self.max_concurrent)]
        taken = client.mget(slot_keys)
        cooling = client.mget([self._cooldown_key(r) for r in self.routers])

        candidates = []
        for i, router in enumerate(self.routers):
            busy = sum(1 for v in taken[i * self.max_concurrent:(i + 1) * self.max_concurrent] if v)
            if busy >= self.max_concurrent:
                continue
            # Healthy before cooling-down, a fresh router before the one that
            # just failed this job, then least busy; random among equals.
            candidates.append((bool(cooling[i]), router.label == avoid, busy, random.random(), router))

        token = uuid.uuid4().hex
        for *_, router in sorted(candidates, key=lambda c: c[:4]):
            for slot in range(self.max_concurrent):
                key = self._slot_key(router, slot)
                if client.set(key, token, nx=True, ex=settings.AI_ROUTER_LEASE_SECONDS):
                    return Lease(router=router, slot_key=key, token=token, pool=self)
        return None

    def extend(self, lease):
        if not lease.slot_key:
            return
        try:
            self._client().expire(lease.slot_key, settings.AI_ROUTER_LEASE_SECONDS)
        except Exception as exc:
            logger.warning('extraction.router.extend_failed router=%s error=%s', lease.router.label, exc)

    def release(self, lease):
        if not lease.slot_key:
            return
        try:
            self._client().eval(_RELEASE_SCRIPT, 1, lease.slot_key, lease.token)
        except Exception as exc:  # the slot simply expires on its own
            logger.warning('extraction.router.release_failed router=%s error=%s', lease.router.label, exc)

    def mark_unhealthy(self, router):
        try:
            self._client().set(self._cooldown_key(router), '1', ex=settings.AI_ROUTER_COOLDOWN_SECONDS)
        except Exception as exc:
            logger.warning('extraction.router.cooldown_failed router=%s error=%s', router.label, exc)


def processing_mode():
    """settings.AI_PROCESSING_MODE, validated again (tests override settings)."""
    from config.ai_processing_mode import parse_mode
    return parse_mode(settings.AI_PROCESSING_MODE)


def get_router_pool():
    """The router pool in multi_router mode; None in single mode, where
    AI_ROUTER_URLS is ignored even if it's set."""
    from config.ai_processing_mode import MULTI_ROUTER

    if processing_mode() != MULTI_ROUTER:
        return None
    routers = configured_routers()
    if not routers:
        raise ImproperlyConfigured(
            'AI_PROCESSING_MODE=multi_router but AI_ROUTER_URLS is empty. List the router URLs, '
            'or set AI_PROCESSING_MODE=single.'
        )
    return RouterPool(routers)


# -- the router the current job's AI calls go to ---------------------------

_lease = contextvars.ContextVar('ai_router_lease', default=None)


def current_lease():
    return _lease.get()


@contextmanager
def use_lease(lease):
    token = _lease.set(lease)
    try:
        yield
    finally:
        _lease.reset(token)
