# AI processing modes

One setting in `backend/.env` chooses how extraction jobs reach the AI:

| `AI_PROCESSING_MODE` | AI connection | Worker slots (default) |
|---|---|---|
| `single` (default) | `AI_BASE_URL` + `AI_API_KEY` + `AI_MODEL` | 2 |
| `multi_router` | the routers in `AI_ROUTER_URLS`, keys in `AI_ROUTER_API_KEYS`, model `AI_ROUTER_MODEL` (or `AI_MODEL`) | routers x `AI_ROUTER_MAX_CONCURRENT` = 4 x 2 = 8 |

`CELERY_WORKER_CONCURRENCY` overrides the worker count only if you set it; leave it empty and the mode decides.
An invalid mode stops Django and the worker from starting (`AI_PROCESSING_MODE='x' is not valid`).

Code: `config/ai_processing_mode.py` (the switch), `apps/extraction/services/router_pool.py` (router leasing),
`apps/extraction/services/ai_service.py` (which endpoint each AI call uses),
`apps/extraction/services/processing_status.py` + `manage.py ai_mode_status` (health).

## How multi_router assigns work

All documents go into one Celery queue. Each of the 8 worker slots takes the next document, then leases a
slot on the least-busy healthy router (Redis keys, 2 per router), and every AI call for that document goes to
that router. So each router never runs more than 2 documents at once, and no document is pinned to a router:
if router 3 is down, its share goes to the other three instead of waiting.

- A router that fails with a recoverable error (rate limit, timeout, unreachable, 5xx) is used last for
  `AI_ROUTER_COOLDOWN_SECONDS` (60 s); the Celery retry then leases another router.
- multi_router never falls back to `AI_BASE_URL`: an AI call without a router lease is refused.
- If every slot is busy, a job waits up to `AI_ROUTER_WAIT_SECONDS` (300 s), then retries later.
- Duplicate protection is the same in both modes: a job only starts from pending/retrying/running, a finished
  job is never re-run, and an old queue message for a re-processed job is skipped.

## Switching modes (Windows dev setup)

From the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\switch-ai-mode.ps1 -Mode multi_router
powershell -ExecutionPolicy Bypass -File .\switch-ai-mode.ps1 -Mode single -With9Router
```

The script:

1. sets `AI_PROCESSING_MODE` in `backend/.env` (the only line it changes);
2. asks the running worker to shut down warmly -- running jobs finish first, queued jobs stay in Redis
   (force-stopped only after `-WaitSeconds`, default 600);
3. runs `start-dev.ps1`: Redis, the 4 WSL routers in multi_router mode (`-With9Router` starts the Windows
   9router on 20128 for single mode), one new worker, and the health check.

Only the Celery worker needs restarting; Django only queues jobs and behaves the same in both modes.
Normal daily start (no switch): `powershell -ExecutionPolicy Bypass -File .\start-dev.ps1`.

Docker: set `AI_PROCESSING_MODE` in `.env` and `docker compose up -d celery` (the compose command no longer
forces `--concurrency`).

## Health check

```powershell
cd backend
python manage.py ai_mode_status --workers
```

Shows the mode, configuration problems, each endpoint/router (reachable, latency, slots in use, cooling down,
whether the model is listed) and the running workers with their concurrency. Exit code 1 = not healthy.
It does not prove a key works: 9router serves `/models` without a key, and a test completion would spend
quota upstream. The worker also logs `ai.mode ...` at startup. No log line contains an API key.

## multi_router checklist

1. Each of the 4 routers has a combo with the same name (`AI_ROUTER_MODEL`, e.g. `my-combo`) and the same
   providers/models in the same order -- otherwise results differ by router.
2. Each router's API key is in `AI_ROUTER_API_KEYS`, in URL order.
3. `ai_mode_status` shows all 4 routers `ok` with the model listed.

## Concurrency and performance -- what to expect

- 8 slots is a ceiling, not a 4x speed-up. Throughput is limited by the slowest shared resource:
  - Upstream provider quotas. If the 4 routers use the same provider accounts, they share one rate limit;
    8 parallel jobs then mostly produce 429s and retries. Real gains need different upstream accounts per
    router.
  - The combo itself: a slow first model in a 9router combo (seen: 80-120 s for a tiny request) makes every
    call slow in either mode.
  - OCR runs one page at a time per worker process (thread-safety lock); OCR-heavy batches gain less.
  - SQLite allows one writer at a time; 8 workers writing facts can contend. PostgreSQL removes this.
- single mode: 2 documents at a time, one quota, simplest to run and debug.
- multi_router: up to 8 documents at a time, router failover, more moving parts (4 routers to keep
  configured identically and running).
