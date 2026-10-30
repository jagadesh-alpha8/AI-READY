# Step 4 — grounded institution-specific recommendations

Branch: `a1-step4-recommendations`. PR base: **A1**. Includes exact Step 3 checkpoint
`2d72b8efd078d1ac55a5918fc8137465c6fe4edd` because remote A1 lacked it at implementation time.
Step 4 is a separate subsequent commit. Preserve the engineer's integration fixes when reconciling.
No deployment or production migration was performed. Frontend adoption remains Step 5.

## Behaviour

Code selects action IDs and sufficient scenarios from the completed frozen assessment, all 36 indicators,
and the pinned rubric. The plan includes current standing with uncertainty, immediate next-level actions,
an experimental next-overall threshold, and Silver/Gold/Platinum scenarios. No optimality or guaranteed
uplift is claimed. The proposed 10-point threshold sequence is versioned in recommendation_policy_v0_1.json;
target selection uses exact weighted levels, not rounded presentation scores.

Unknown conditions get deterministic requests for evidence covering the frozen population/period, never
model-generated capability interventions. Proven shortfalls and contradictions are tailored per indicator
using only the frozen profile, requirement decisions and their exact citations. Conflict advice must retain
both sides. Suggested roles, effort, steps and completion evidence remain proposals. Canonical requirements
and canonical completion evidence remain in the deterministic plan beside the enrichment.

Advice validation rejects wrong/missing/duplicate action IDs, changed operation types, unsupported citations,
missing factual bases, dropped conflict citations, malformed responses and cyclic/foreign dependencies.
Dependencies are limited to the same indicator's requested actions. Related indicators are not prerequisites.
Validation is not a semantic truth guarantee; live corpus quality evaluation remains required.

## Storage and execution

- RecommendationSnapshot: immutable pinned assessment event/hash, profile, period, deterministic plan,
  policy, prompt/schema version/hashes and per-generation budgets.
- RecommendationEvent: append-only reservations, outcomes, validated batch checkpoints and completed artifact.
- RecommendationExecution: independent mutable dispatch, budget, heartbeat and idempotency ledger.
- RecommendationActionState: user-managed owner/feasibility/status separate from historical model advice.
- AIUsage links both the assessment and recommendation snapshot, with capability_recommendations stage.

Assessment history is never reopened or appended to during advice generation. Failed/cancelled generations
keep the complete deterministic fallback; partial advice is not published. In-flight requests can still be
billed after cancellation, with their outcomes recorded only in recommendation history. Same key returns
same version without spending. Intentional new generations use new keys. One active generation per
assessment is enforced by row locking plus database uniqueness. No worker-loss replay or whole-task retry.

Shared metering retains existing provider factories, router leases, disabled SDK retries, bounded transient/
JSON correction requests, conservative reservations, pricing checks and usage validation. Per-execution
ceilings are the existing CAPABILITY_MAX_HTTP_CALLS, CAPABILITY_MAX_COST_USD,
CAPABILITY_OUTPUT_TOKENS and CAPABILITY_REQUEST_TIMEOUT_SECONDS settings, pinned at start. Advice uses a
separate opt-in `CAPABILITY_RECOMMENDATIONS_ENABLED=true`; defaults false. No provider keys are bundled.
No readable evidence or no model-eligible actions completes deterministically without constructing a client.
Budgets are application estimates at configured prices, not provider-side spending guarantees.

## Additive migrations

Install requirements (now explicitly includes jsonschema), then review/apply migrations in a development
environment: scoring 0011 and extraction 0015, after Step 3's scoring 0010/extraction 0014.
No legacy score, baseline or completed assessment rows are rewritten. Migration names/dependencies may
need reconciliation if the engineer creates migrations with the same numbers on his branch.

## API

Prefix: `/api/v1/sprints/{sprint_id}/capability-runs/{run_id}/recommendations`.
Existing CanManageSprint and institution access apply. Both trailing slash forms work.

| Method and suffix | Behaviour |
|---|---|
| GET prefix | Paginated generation history and enabled flag. No inference. |
| POST prefix | Empty JSON `{}` and Idempotency-Key required; 202 new / 200 reused; 409 active generation. Requires completed assessment. |
| GET `/{snapshot_id}` | Pinned deterministic plan, completed tailoring (or fallback), status/error/cost and separate user workflow state. No inference. |
| POST `/{snapshot_id}/cancel` | Idempotently stop future requests and publication. |
| PATCH `/{snapshot_id}/actions/{condition_id}` | Update only owner, feasibility (unreviewed/feasible/blocked), status (proposed/in_progress/completed/dismissed). No score changes or inference. |

Example explicit generation:

```http
POST /api/v1/sprints/SPRINT/capability-runs/RUN/recommendations
Idempotency-Key: recommendations-2026-10-30-1
Content-Type: application/json

{}
```

The detail endpoint always exposes the canonical deterministic plan. `tailoring` is present only after
atomic completion; `mode=deterministic` / `fallback=true` identifies generations without model enrichment.
Stalled active jobs can be cancelled before intentionally starting a new budgeted version.

## Validation

Final regression: 491 tests ran, OK with 1 skipped (490 passed), including 20 new recommendation tests. Model checks pass with only the unconfigured-key warning; migration consistency reports no changes. See STEP_4_VALIDATION.md and the packaged final log. Tests use mocked SDK responses, temporary
SQLite databases and no live provider inference. They cover full framework/pathway advice, unknown-evidence
exclusion from model inputs, preserved uncertainty, contradiction citations, action/dependency grounding,
tenancy, idempotency, duplicate/late task delivery, cancellation, budgets, missing telemetry/prices, both
provider clients, router release, safe fallback and workflow completion leaving scores/history untouched.

Before enabling for users, test real Celery/Redis, PostgreSQL concurrency, killed workers, approved provider
compatibility and advice quality on actual institution evidence. No live spending is authorized by this package.
