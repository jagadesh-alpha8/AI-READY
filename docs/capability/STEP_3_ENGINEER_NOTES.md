# Step 3: automatic assessment API and worker

Implemented on A1; inference is disabled by default. This stage adds backend plumbing;
the administrator frontend still uses the legacy score. Do not deploy or merge main
as part of uploading this package. These instructions are for the engineer's development
environment, after reviewing the changes.

## Development setup

1. Pull A1 and install existing backend requirements. Apply `python manage.py migrate`.
   New migrations: scoring 0010 (execution ledger) and extraction 0014 (usage/run link),
   in addition to step 2's scoring 0009. No historical CRI/baseline rows are changed.
2. Reuse the existing provider settings (`AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL` or
   `AI_PROCESSING_MODE=multi_router` with router settings). Do not send institutional
   documents to a new provider without authorization. No key belongs in the repo.
3. Configure model pricing in `AI_PRICING_JSON` where the existing table lacks a match:
   `{"your-configured-model":{"input":INPUT_USD_PER_MILLION,"output":OUTPUT_USD_PER_MILLION}}`.
   Replace the symbolic prices with actual reviewed numbers. Unknown or invalid prices
   fail before a request. For a router combo, configure a conservative rate covering
   all possible routed models; model identity returned by the provider is retained.
4. Set `CAPABILITY_ASSESSMENT_ENABLED=true` in the development environment. Restart
   the API and Celery worker so they use the same code, settings and schema. Defaults:
   max 72 HTTP requests; USD 2 in conservative reservations; 3000 output tokens/request;
   60-second request timeout. Settings: `CAPABILITY_MAX_HTTP_CALLS`,
   `CAPABILITY_MAX_COST_USD`, `CAPABILITY_OUTPUT_TOKENS`,
   `CAPABILITY_REQUEST_TIMEOUT_SECONDS`, `CAPABILITY_STALE_SECONDS` (default 900).
5. Run the existing broker and Celery worker. When EXTRACTION_QUEUE is configured,
   the new scoring task routes there; otherwise it uses the normal default queue.
   Multi-router calls acquire/release the existing router lease; no provider fallback
   or extra model service is introduced. Inference disabled is also checked in workers.
6. Use authorized test-institution pages and a small reviewed budget for the first
   real assessment. Compare condition decisions with human-labelled evidence. Mocked
   tests do not establish model accuracy or real endpoint compatibility.

## API contract

All paths start with `/api/v1/sprints/{sprint_id}`. Both trailing slash forms work.
Existing authentication and institution-access rules apply. IQAC coordinators can
start/cancel their institution's assessments; consultant approval is not required.

| Method/path | Behaviour |
| --- | --- |
| GET `/capability-runs` | Paginated history; `page`, `page_size` (up to 100); enabled flag. No inference. |
| POST `/capability-runs` | Start once with `Idempotency-Key` header; returns 202. Same key/body returns original run (200); changed body/key collision or concurrent active run returns 409. |
| GET `/capability-runs/{run_id}` | Status, progress, frozen profile/source manifest, partial decisions or one completed assessment snapshot. |
| GET `/capability-runs/{run_id}/evidence?condition_id=AIQIF-C1.1.F1` | Frozen decisions and cited source excerpts. Omit condition_id for all assessed requirements. |
| POST `/capability-runs/{run_id}/cancel` | Stops future requests/publication. Already in-flight calls may finish and be billed. Repeated cancellation is harmless. |

Start request JSON:

```json
{"population":"All faculty and students across the institution","reference_period":"2025-26"}
```

Use a fresh client-generated idempotency key for each intentional new assessment.
Read/refresh requests never spend credits. The same key never creates a new run,
even if the original failed or configuration/evidence later changed. A new key
requires an intentional new start. One active assessment per sprint is enforced
with sprint locking and database uniqueness. Successful publication is atomic;
failed runs retain partial indicator decisions without a headline score.

## Request accounting and failure policy

The existing OpenAI/compatible or Anthropic client is created via get_ai_service.
A per-run SDK proxy disables SDK retries and intercepts every actual SDK request,
including the client's format/sampling fallbacks and JSON correction. One bounded
transient retry per indicator is allowed (short Retry-After only); there are no
whole-run Celery retries or automatic cross-provider retries. Every attempt reserves
its full budget envelope before sending, and every returned response is associated
with the run through the existing AIUsage table. Run events retain request hash,
schema/settings, configured and returned model, tokens, duration and outcome. No API
keys, credential-bearing base URLs or raw exception messages are exposed by this API.

Reservations use UTF-8 request bytes plus a 4096-token protocol allowance, capped
output tokens and the largest configured input/cache rate. They are conservative
application estimates, not a provider-enforced USD guarantee: router transformations,
undocumented billing, inaccurate prices or external retries/fees can differ. Failed
or ambiguous requests retain their full reservation. Missing usage stops further
calls; returned token counts above the reserved token envelope stop the run. Pair
this with provider-side spending limits for actual billing protection.

A broker failure records a terminal safe error; a late delivery skips it. Duplicate
task delivery cannot claim a running or terminal ledger. A killed worker is NOT
silently replayed: a request may already have been billed. History shows stalled
queued/running jobs after CAPABILITY_STALE_SECONDS; cancel the old run, inspect billing,
then explicitly start another. A terminal run never changes to completed afterward.
Completed indicator checkpoints and request outcomes remain available for diagnosis.
A corpus with no readable pages completes all 216 conditions as unknown without
constructing a provider client, acquiring a router or making an inference call.

## Validation and remaining integration checks

Automated tests use injected SDK responses, not real inference. They cover all 36
indicator outputs, tenancy, same-key replay/conflict, duplicate task delivery,
queued/in-flight cancellation, request and cost budgets, corrective/transient requests,
missing usage/prices, safe provider/broker errors, both clients and router lifecycle.

Before deployment, exercise real Celery/Redis, PostgreSQL concurrent requests and
worker termination, real configured provider output caps and usage reporting, and
condition accuracy against the actual corpus. SQLite unit tests do not prove row-lock
behaviour in PostgreSQL. Existing source snapshots retain current-sprint page text;
retention and full-corpus quality remain integration concerns.

Next: grounded tailored recommendations (step 4), administrator UI/report adoption
(step 5), and corpus/live validation (step 6). No frontend scoring headline has changed.
