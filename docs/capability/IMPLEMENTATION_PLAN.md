# Capability assessment implementation plan

Development branches submit PRs targeting **A1**. Step 4 used `a1-step4-recommendations`; Steps 5–6 use `a1-step5-6-experience`; never push directly to A1, modify main, merge PRs or deploy as part of this work.
Baseline inspected: `4f170d14eeb3e2b2aca7b9ab13656df76ffd6175`.

## Product contract

All nine pillars and 36 indicators are required. AI interprets evidence and tailors institutional advice.
Code determines numerical scores and tier eligibility from explicit requirement decisions. Do not use
extraction confidence as institutional capability. No consultant approval is required to view the new
assessment, recommendations or report. Missing evidence is unknown, not automatic failure. Preserve
history and distinguish methodology changes from institutional changes.

All new maturity conditions, tier thresholds, coverage rules and population standards are **experimental
internal proposals**. They are not external accreditation requirements or expert-validated standards.

## Sequence and progress

### 1. Scoring and evaluation foundation - implemented, not yet connected to the application

- `backend/apps/scoring/capability/rubric_v0_2.json`: versioned 36-indicator / 216-condition registry.
- `engine.py`: exact fractional arithmetic, full-framework bounds, pillar results and nested tier rules.
- `planning.py`: requirement-linked actions and sufficient tier scenarios; no claim of optimality.
- `evaluation.py`: injectable structured model evaluation with source/quote validation, per-indicator context
  bounds and a maximum of 36 indicator evaluations per invocation. No automatic provider calls.
- `backend/apps/scoring/test_capability.py`: numerical, uncertainty, tier, scenario and grounding fixtures.

The registry is a first structured content revision, **not a declaration that every rubric ambiguity is
solved**. Conditions include examples, unknown/failure rules and scope/period expectations. Further
indicator-specific counterexamples, competence tests, coverage thresholds and mission alternatives need
refinement. Two practical demonstrations replace plan-only literacy foundations. An 80% assessed-population
criterion for faculty/student literacy adoption is a newly proposed internal standard, not a confirmed
stakeholder rule. Outcomes currently require two completed academic-year cycles; this is an experimental
default to replace the ambiguous generic 'two cycles', and may be too restrictive for some indicators.

### 2. Immutable run storage and evidence adapter - storage stage implemented

Choose an additive capability-run model, pinned to a rubric snapshot/hash. Do not reinterpret historical
`ScoringRun` rows or existing baseline approvals. Include an institution profile/population, reference
period, source manifest, condition decisions/reasons/citations, inference metadata and result snapshot.

Adapter requirements:

- Read only the selected institution's current source pages; do not reuse superseded source versions.
- Include unreviewed but readable source passages where appropriate; requiring fact confirmation would
  reintroduce human gates. Readable text is a candidate source, not proof of authenticity or satisfaction.
- Track exact page/claim IDs and excerpts. The evaluator's source IDs are only trusted after tenant checks
  in this adapter. Engine/evaluator modules themselves do not implement authorization.
- Record actual model identity, prompt/schema/settings, selected context and per-call usage. Provider
  retries mean an indicator evaluation budget is not a monetary or HTTP-call budget.
- New/changed evidence must be matched against candidate requirements, including conditions never
  previously supported. Reverse citation links alone miss newly relevant contradictions.
- Atomically publish a completed snapshot; never mix scores from one run with tier/actions from another.
- Preserve partial/failed/cancelled state and actionable errors. Do not expose raw provider error messages.
- Decide source carry-over between sprints and explicit replacement for renamed documents.

### 3. Automatic API and task orchestration - implemented, mocked validation

Use existing Celery, AI provider abstraction, router leases where configured, and usage accounting. Add
institution-scoped endpoints to start/read runs and inspect condition evidence/history. Starting an
assessment is a permitted institution action, not consultant approval. Do not automatically spend API
credits from GET requests. Configure retry/cost ceilings and idempotency before enabling inference.

### 4. Grounded tailored recommendations — backend implemented, inference defaults off

Use the deterministic selector/scenario engine to identify conditions, then ask the model for contextual
actions. Validate referenced requirements and evidence. Keep evidence requests, contradictions and
capability development distinct. Completing a task does not change a score until evidence is reassessed.
Maintain ownership, feasibility and action status independently. Derive the next overall threshold from
an explicitly configured policy; a 10-point threshold remains proposed.

### 5. Administrator UI and report integration — implemented, local validation

Make capability the new product headline, with bounds and evidence completeness. Explicitly label legacy
CRI. Update all dashboard, score, report and recommendation consumers together; do not merely place a new
number beside the old headline. Show all 36 indicators, three tier pathways, source references and
unresolved items. Allow report export without baseline approval in the new automatic path.

### 6. End-to-end validation and demo preparation — automated/offline checks implemented; live acceptance outstanding

Select the actual institutional corpus and working provider. Measure live condition accuracy and cold-run
agreement separately from exact numerical replay. Test source updates, tenancy, failed formats, partial
OCR, failed provider requests and scenario boundaries. Demonstrate all 36 rubric outputs even if some
resolve to unknown. Do not imply complete evidence or validated institutional tiers from full rubric coverage.

## Audit disposition in the foundation

| Finding | Current treatment | Still required |
|---|---|---|
| A1 incomplete average | Removed from new arithmetic; full denominator and bounds | UI/report adoption |
| A2 vague conditions | Explicit IDs and structured records | Specific pass/fail examples and domain refinement |
| A3 scope gaming | Population/scope rules in prompt and registry | Profile adapter and population evidence tests |
| A4 cyclic links | Related links never enforced; no hard graph introduced | Action-level prerequisites when authored |
| A5 undefined N/A | Unsupported states rejected | Versioned alternatives if required |
| A6 tier certainty | Lower/upper rule checks, independent completeness status | User-facing wording |
| A7 cumulative levels | Exact rules checked against all 4,096 condition-state patterns | Evaluate prerequisite policy with domain examples |
| A8 plan-only capability | Initial literacy foundation corrections | Review other foundation conditions |
| A9-A15 integration/ops | Sequenced above | Not solved by foundation code |

## Validation commands

From `backend/`:

```bash
python -m unittest apps.scoring.test_capability -v
python manage.py check
SECURE_SSL_REDIRECT=False python manage.py test apps.scoring --noinput
```

The pure tests require no credentials or database. Citation fixtures establish validation behaviour, not
LLM interpretation accuracy. No live model experiment has been run; the current workspace has no AI key
configured. The existing application still uses legacy CRI until the integration stages land.


## Step 2 checkpoint (2026-10-30)

Added CapabilityRun frozen inputs and append-only CapabilityRunEvent checkpoints via additive migration 0009.
Publication locks the run, revalidates 216 decisions and tenant-scoped quotes, and writes the result,
actions, three pathways, traces and inference metadata in one completed event. Completed, failed and
cancelled runs cannot transition again. Model saves and queryset updates/deletes reject history mutation;
raw database access is outside this application guarantee. Sprint deletion is protected once runs exist.

The adapter reads current, non-rejected document versions and readable DocumentPage rows in the selected
institution/sprint, including unreviewed text. It freezes profile/headcounts, population, reference period,
rubric/hash, document/page manifest, and exact excerpts. Claims are evaluated from page text, so page IDs
are the citation units; legacy extracted-fact claims are not independently treated as evidence. Failed and
unreadable pages remain visible in the manifest. No automatic cross-sprint carry-over. Renamed replacements
must have explicit document lineage; no filename/content heuristic is added. Evidence changes invalidate
all 216 requirements, including requirements never previously cited.

Provider identity/settings and per-request usage have a storage contract; collecting these from the real
provider, authenticated API access, retry/idempotency/cost ceilings, and dispatch remain step 3. The adapter
is an internal service: its institution argument must come from the authorized caller, not untrusted input.
No live provider calls or production migrations were performed. Run snapshots can be large because exact
page text is retained; retention/access policy and production concurrency testing remain integration work.


## Step 3 checkpoint (2026-10-30)

Added authenticated tenant-scoped capability run start/history/detail/evidence/cancel APIs,
Celery execution with a unique ownership ledger, per-sprint idempotency and active-run
constraints, conservative pre-request cost reservations, counted HTTP attempts and bounded
transient retry. Existing provider/router/usage services are reused; SDK retries are disabled
only on capability clients. AIUsage rows now link to their capability run. Failed runs keep
partial decisions; a stopped or duplicate task cannot publish. Empty readable evidence yields
36 unknown indicators without inference. Live feature defaults off.

See STEP_3_ENGINEER_NOTES.md for exact endpoints, developer enablement, deployment checks,
budget limitations and worker-loss policy. Real provider, broker and PostgreSQL concurrency
behaviour remain unverified. The administrator frontend is still legacy; subsequent stages
are required before calling this a live automatic assessment product.

Step 4 audit, implementation details and API: [STEP_4_AUDIT.md](STEP_4_AUDIT.md) and [STEP_4_ENGINEER_NOTES.md](STEP_4_ENGINEER_NOTES.md). Frontend adoption and live quality/integration validation remain Steps 5–6.

Steps 5–6 implementation and validation: [STEP_5_6_ENGINEER_NOTES.md](STEP_5_6_ENGINEER_NOTES.md). Remaining live acceptance: [STEP_6_ACCEPTANCE.md](STEP_6_ACCEPTANCE.md). Step 5 provides printable HTML/JSON exports; native capability PDF/Word is not implemented.
