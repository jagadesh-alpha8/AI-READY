# Default assessment scope and institutional plan comparison

2 November 2026 · Experimental implementation; no production deployment or real-institution rescore.

## Repository and integration

Started from A1 `f837d86a3ee1bdd43c3b9df30e03a7e17a25b532`. PR #4 is still an open draft,
head `24153c5cb697f910fb4a46b33bbf74c469c2b08e`. Its frontend, SQLite and PostgreSQL checks
are green; deployment/image jobs are skipped. This branch includes that head locally without
changing either remote A1 or the report branch. A draft PR may expose this dependent work to A1;
merge PR #4 first and refresh/rebase this branch onto the actual A1 head before final integration.
Main remains unchanged.

## Default overview and refinement

`POST /sprints/{sprint}/capability-runs` accepts `{}` or `{"scope_mode":"default"}`. No
population/year is invented. The saved label is an institutional overview with finding-specific
coverage and evidence periods. Legacy requests supplying population + reference_period remain
custom scope, with their historical normalized request digest shape. Partial custom input or
mixing default with overrides is rejected. Optional `refines_run_id` must name a completed run
in the same authorized sprint.

The start transaction checks an existing idempotency key against normalized requested intent
BEFORE reading sources/resolving defaults. Retries reuse the first frozen input; new uploads
cannot silently change that request. New refinements get their own run/input hash and parent
identity. Their advice and scenarios are new; nothing rewrites an earlier assessment.

The versioned scope record preserves profile identity basis, explicit user intent/overrides,
exact source spans for labelled populations and date declarations, unresolved questions,
source IDs and inference limitations. A conservative deterministic adapter recognizes explicit
labels such as Programme, Academic year, Policy effective and Curriculum regulation. It is
**not** exhaustive semantic inference. A source identity mismatch is flagged for review without
renaming the profile; absence of a labelled identity remains unconfirmed. The evaluator must
establish ownership from the actual evidence. Global questions are visible below the result;
this does not implement the persisted initial question queue.

Provider context gets only declarations from selected source windows (bounded to 100), not the
whole scope inventory. Activity dates, policy intervals and curriculum regulations remain distinct;
filenames/upload times do not establish currency. Neither default mode nor a narrowed custom
cohort relaxes universal/institution-wide rubric conditions. Prompt protocol is bumped to 0.4;
old queued jobs with an incompatible saved prompt fail safely rather than run a new protocol.

The initial UI starts the overview. After analysis/recommendations, optional refinement asks for
both custom fields and explains that changing scope is not institutional improvement. Sprint
Setup's year is now a blank optional workspace label, not an assessment-period setting.

## Plan lifecycle and arithmetic

`POST /sprints/{sprint}/capability-runs/{run}/plan-evaluations` accepts `plan_text` up to
30,000 characters with an Idempotency-Key. List/detail/cancel/report endpoints follow the same
path. Plans require a completed, replayable baseline; all reads are tenant-authorized. Separate
models retain immutable InstitutionalPlanVersion (submitted/suggested with parent), PlanScenario
(frozen inputs) and append-only events. The execution ledger handles status/billing/idempotency.

The baseline pins run/input identity, completed assessment-event/hash, exact rubric snapshot,
engine and scope. Actual decisions replay under the pinned engine before scenario creation and
publication. Export/detail identity checks also verify the original/suggested plan text hashes,
parent linkage, baseline identity and completed comparison hash.

Up to seven logical model operations, each through the existing metered SDK boundary (an input with no actionable commitments returns a qualitative limitation after parsing):

1. Parse original text into cited actions, resource/timing/budget constraints and ambiguities.
2. Propose requirement mappings without scores.
3. Separately challenge each mapping's semantic support, scope and phase.
4. After calculating the original scenario, critique/revise the original actions.
5. Parse the suggested text independently.
6. Map the suggested actions under the same rubric/scope/baseline and original constraints.
7. Separately challenge those mappings, then recalculate deterministically.

Exact action spans use zero-based Python character offsets; UI does not interpret those offsets.
Every mapping cites an exact substring of a known action, names a known requirement, and receives
exactly one separate review. Improvements account for every original action using retain/change/
replace/remove, with additions separately labelled, suggested owner, dependencies, completion
measurement and resource tradeoffs. Claimed existing assets must cite exact bounded frozen source
passages. These checks cannot prove all prose is entailed or practically sound; empirical evaluation
is still necessary. The same configured model can perform both mapping and review; this is a
separate challenge pass, not independent human verification.

`scenarios.evaluate_plan` is pure. It overlays only complete, scope-compatible conditional changes
with explicit assumptions. Partial mappings and documentation gathering earn no automatic credit;
contradictory mappings are rejected. Baseline conflicts remain conflicts. Duplicate requirements
count once. Cumulative foundation/adoption/outcome prerequisites remain those of `engine.assess`.
Withdrawals can reduce projected standing. Outcome requirements and explicitly enumerated
competence/attainment requirements cannot enter delivery-only credit. The semantic reviewer may
route other measured-result claims to the results-dependent phase conservatively.

Before/after comparisons enumerate the SAME unknown/conflicting binary completions within each
indicator (at most 64), apply the overlay, and aggregate paired change bounds using frozen Fraction
weights. They do not subtract independent endpoints, use midpoints or invent success probabilities.
Bounds assume the engine's independent unresolved conditions; real cross-condition correlations
may require more explicit constraints. Values are rounded only for presentation, as in the engine.

No task completion, plan submission or simulated score changes actual assessment events. A proposed
plan may be planning evidence only in a separate admissible actual reassessment, never by entering
this evaluator.

## Budgets and execution limits

No budget field/question is required. Named money amounts must be retained in the parsed budget
register; detected currency-prefixed amounts cannot silently disappear. Extracted constraints are
preserved verbatim in suggested text and passed to both mapping/review paths. Repetition of a
constraint is not proof of practical compliance; the reviewer must also challenge contradictions.
Preserve currency, period and per-cohort/whole-institution meaning. Same-envelope advice is soft:
reuse/reallocation is suggested where plausible; no prices, free capacity or cost-equivalence
promise are invented. Numeric amounts expressed without currency prefixes depend on parser quality.

`CAPABILITY_PLANS_ENABLED=false` by default. It is a separately configurable experimental feature,
not activated by this branch. It shares existing capability request/cost/output/timeout ceilings,
SDK retry disabling, per-HTTP-call reservation, pricing checks and telemetry requirements. Seven
logical operations can make extra HTTP calls through provider format/transient retries; every one
counts. No automatic whole-run retries. Reads, history and HTML/JSON exports invoke no model.
Stalled jobs require explicit cancellation and a new request; late outcomes retain billing history
but cannot publish after cancellation. AIUsage additionally links each billed call to its scenario.

Apply additive migrations scoring 0012 and extraction 0017 before enabling the feature. Restart
API/workers together; reconcile migration filenames against any unpublished engineer work first.
Do not enable the candidate revised readiness rubric as part of this feature.

## Presentation and limits

Below assessment/recommendations, optional plan text entry leads to a versioned comparison of actual
standing, original plan delivery/results scenarios and suggested-plan delivery/results scenarios.
It exposes concrete revisions, nine area implications, assumptions and uncredited mappings. A sparse
baseline retains ranges and allows qualitative feedback; no precise gain is manufactured. Printable
HTML and full JSON are separate plan-comparison exports, not silently inserted into the existing
leadership assessment PDF. Text input is supported; direct plan-document upload is not implemented.

The ordinary recommendation generator, persisted cross-pillar initiatives, reviewed-fact bridge,
authorised declarations, 25-question initial queue and one-action orchestration remain open.
The status dashboard and tour wording have been corrected so they do not describe obsolete
September architecture, false completion percentages or compulsory scope/approval gates.

Automated checks use synthetic/injected responses. They verify arithmetic, provenance, lifecycle,
limits and UI behavior; they do not measure real model interpretation accuracy. Before production
enablement, review examples covering vague plans, complete delivery commitments, measured outcomes,
shared prerequisites, contradictory/withdrawal actions, scoped cohorts, historical evidence,
prompt injection, named budgets and asset reuse. Also run a business-reader review of the advice.


## Verification checkpoint

- Full local backend run: 1,492 tests, one skipped, passed with the same `DEBUG=True` test
  environment used by CI. Later focused runs cover the final no-action input handling,
  cross-baseline isolation and readable plan-export labels.
- New scope/scenario/plan checks: 25 in total across the focused runs.
- Frontend: all 160 tests and the production build pass. Migration drift, Django system
  configuration and whitespace checks pass; the expected unconfigured AI-key warning remains.
- PR #5 targets A1 as a draft depending on PR #4. GitHub backend/PostgreSQL checks are pending
  at this checkpoint; frontend CI has passed. Neither PR is merged or deployed.
- The workspace had no installed browser executable, so browser visual QA could not be
  performed. Automated rendering/escaping checks are not described as visual verification.
