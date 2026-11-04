# Comparable measures and bounded evidence probes

## Current disagreement versus stored review history

A normalized field key can collapse distinct counts. `read_scope` now records an
explicit `count_basis` for a small, conservative set of count labels: exam passes
versus appearances, national versus international versus industry agreement
counts, and clear student headcount/intake/beneficiary counts. Mixed or unknown
labels stay unknown. Arbitrary differing labels or includes lists do not suppress
a disagreement. Matching aliases still compare, and different values of the same
measure remain conflicts. Labels distinguish measures; they do not prove source
truth, scope completeness or period currency.

New frozen review snapshots reconstruct every alternative for field-wide conflict
gaps. Each stored conflict retains its original status and events, but additionally
records `comparison_status` and the IDs of currently comparable disagreeing
alternatives. A historical open flag alone no longer blocks a substantive decision
when its current alternatives do not disagree under compatible scopes. This is
not a human resolution or proof that all sources agree. Resolved conflicts can
still be challenged by newly disagreeing current evidence. No stored review gap
or prior frozen ledger is rewritten by assessment snapshotting.

Ledger version: `reviewed-evidence-2`. Bounded context version: `review-context-4`.
The evaluator protocol is `AIQIF-EVAL-0.13` so mismatched web and worker versions
are rejected by existing protocol checks. Deploy both processes together and
start a new assessment boundary; old frozen inputs are not retroactively repaired.

## Requirement-owned packet ablation

```bash
HF_HUB_OFFLINE=1 PYTHON_DOTENV_DISABLED=1 \
CAPABILITY_EMBEDDING_PATH=/private/provisioned-encoder \
python manage.py capability_packet_compare \
  --replay-inputs /private/frozen-retrieval-replay.json \
  --evidence-cases /private/reviewed-evidence-cases.json \
  --output /private/new-packet-comparison.json --budget 18000
```

This offline comparator reserves a share of the fixed context budget for each
assertion. It compares lexical and combined candidate pools and an exact adjoining
source-span expansion. Relevance chooses an anchor; bounded lexical novelty can
propose complementary candidates. These features do not establish evidence
sufficiency. A length-normalized first ablation selected short topical fragments
and was rejected; the implementation explicitly tests against that failure.

Report both shared-union inclusion and actual requirement-owned inclusion. A
quotation elsewhere in the indicator union does not demonstrate that the target
requirement received it. Repeated material in different owned packets pays for
its context each time. Fixed shares can starve requirements needing more context;
no automatic completeness or efficiency advantage is claimed. The command never
changes the active BM25 policy, calls an evaluator or writes to the database.
Gold labels are used only for measurement after selection.

## Bounded live decision and advice probe

The probe requires the private plan JSON and a disposable copy of the same
institutional database, retaining the plan's document/page IDs. Configure provider
credentials, model, positive token prices and existing assessment/advice flags on
that copy. Do not paste credentials into a report, plan or repository.

First inspect the command without executing requests:

```bash
python manage.py capability_bounded_probe /private/expanded-probe-input.json \
  --output /private/new-live-probe.json
```

Execution is explicit:

```bash
python manage.py capability_bounded_probe /private/expanded-probe-input.json \
  --output /private/new-live-probe.json --execute \
  --sprint-id <copied-sprint-id> \
  --disposable-database '<exact configured database NAME>' --advice-cases 3
```

Set the database connection before running; `--disposable-database` checks its
configured name, it does not make a copy. The command verifies every supplied
source window against a fresh source snapshot before inference, rebuilds the
review ledger from current database facts, and binds current prompts and schemas.
It discards any cached responses from the input. Schema/rubric mismatch or changed
source text fails before requests. Missing credentials, disabled execution, and
unpriced/zero-priced models also block execution.

A single normal `MeteredService` ledger covers every actual SDK request, client
retry, evaluator-format repair and normal recommendation repair. Probe-specific
bounds are at most 16 requests, $1 at configured conservative reservation rates,
and 600 seconds, narrowed further by existing configuration. Output and timeout
allowances use the smaller configured assessment/advice stage allowance. No global
limit is raised, and the provider billing estimate is not a billing guarantee.

These are isolated diagnostic requests, not full indicator-batch replay. Raw and
validated decisions, source packets, review projections, scope/period flags,
scoring replay, actual model/usage/rates and request reservations are recorded.
Completed cases are checkpointed into diagnostic-only database events. Up to
three non-met cases use the production `tailor_batch` advice path; processing
failures receive explicitly labelled processing guidance. Verified met strengths
can ground advice but never create missing-capability rebuild actions. Advice
repairs and fallbacks remain visible and spend the same shared allowance.

The command creates a diagnostic run/execution on the disposable copy and never
publishes an institutional assessment or dispatches a worker. If interrupted,
inspect its reserved requests and partial case events before retrying: a request
may already have been billed. Do not treat simulated SDK contract tests as model
quality evidence. A successful live response still needs substantive human review.

## Partial probe recovery

The runner preflights every initial OpenAI-compatible decision packet before any
provider request. Its `input_token_bound` is serialized UTF-8 request bytes plus
4,096 framing units, matching the conservative meter policy; it is not an actual
model tokenizer count or proof that the provider context window was exceeded.
Client format repairs can add content later and still pass through runtime guards.

An initial or runtime input-bound failure is recorded per case as unevaluated,
with zero or more already reserved requests explicitly recorded. It creates no
synthetic model judgement. Other cases and advice on completed decisions can
continue within the unchanged shared request/cost/deadline limits. Global request,
cost, deadline and provider failures still stop execution. Any skipped case keeps
the overall run partial/failed; `case_errors`, completed decisions, advice-stage
status and meter history explain exactly what happened.

Live decisions use `live_response_validated`; offline audit replay retains its
separate replay status. A valid response still does not establish semantic quality.
Do not rerun completed cases merely to obtain missing advice or a corrected case:
review the private output first and prepare an explicitly bounded follow-up plan.
