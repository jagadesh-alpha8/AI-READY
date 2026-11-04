# Bounded capability requests and provider recovery

This change separates output truncation, excessive input, provider timeout and
invalid advice. It does not establish that every timeout was caused by input
size. Diagnose the affected stage using its frozen policy and request ledger.

## Configuration for fresh executions

| Setting | Default | Meaning |
| --- | --- | --- |
| `CAPABILITY_OUTPUT_TOKENS` | `12000` | Shared output allowance, including provider thinking when applicable |
| `CAPABILITY_REQUEST_TIMEOUT_SECONDS` | `AI_REQUEST_TIMEOUT_SECONDS` (normally `300`) | Per-HTTP-request timeout |
| `CAPABILITY_ASSESSMENT_OUTPUT_TOKENS` | unset | Assessment override |
| `CAPABILITY_RECOMMENDATION_OUTPUT_TOKENS` | unset | Recommendation override |
| `CAPABILITY_ASSESSMENT_TIMEOUT_SECONDS` | unset | Assessment timeout override |
| `CAPABILITY_RECOMMENDATION_TIMEOUT_SECONDS` | unset | Recommendation timeout override |
| `CAPABILITY_MAX_INPUT_TOKEN_BOUND` | `131072` | Conservative whole-request bound: serialized UTF-8 bytes plus 4096 framing allowance |
| `CAPABILITY_MAX_DURATION_SECONDS` | `1800` | Execution deadline checked between requests, with SDK timeout clamped to remaining time |
| `AI_GEMINI_REASONING_EFFORT` | `low` | Thinking setting for supported models on Google's direct compatible endpoint; `default` omits it |

The input bound is an application guard, not an exact Gemini token count or a
claim about any model's context window. Configure it for the selected deployment.
The execution deadline does not forcibly terminate arbitrary non-network code.
Existing HTTP-call and configured-price cost ceilings remain enforced.

Explicit existing environment values still take precedence. In particular, an
existing `CAPABILITY_OUTPUT_TOKENS=3000` or timeout of `60` remains in force.
The output default follows the allowance that completed the reference workload.
Reduced thinking and split recovery still need a fresh live check; this is not
a model-quality benchmark. Additional retries reserve cost before sending.

Execution policies are frozen at start. Updating an environment variable does not
change a running execution. Leave an ongoing diagnostic run alone; deploy to the
backend and workers together, then use a fresh execution and idempotency key.
Changed prompts require fresh assessments; old queued snapshots are rejected by
the existing methodology checks.

## Provider behaviour

Google's direct compatible endpoint is identified by the exact hostname
`generativelanguage.googleapis.com`. Gemini 2.5 and Gemini 3 model names receive
the configured reasoning effort. They receive the JSON schema through native
`response_format`, without also copying the entire schema into the system prompt.
Schema rejection is surfaced rather than silently weakening structured output.
Unknown proxies keep the generic compatible-endpoint behaviour because their
support for Google-specific options is not established by a model name.

`finish_reason=length` (or Anthropic `stop_reason=max_tokens`) is a typed output
truncation. It is never resubmitted unchanged as a malformed-JSON correction.
Extraction callers also receive this distinction; capability-specific splitting
does not change extraction chunking.

For an assessment or recommendation batch, truncation or input preflight rejection
causes at most one split into two requirement groups. The evidence stays intact;
each child's requirement schema is smaller. This can help output pressure but
cannot guarantee relief when the evidence packet itself dominates input size.
No recursive splitting or additional validation repair follows that split.
Only IDs requested in a child can be accepted from it. Every accepted decision
and recommendation still passes existing citation, scope and dependency checks.
Ordinary malformed responses retain the existing bounded validation repair.
SDK transient retries remain separately metered, so three logical generations
can represent more than three HTTP attempts.

An exhausted transient failure becomes an explicit processing unknown in
assessment, or labelled deterministic advice in recommendations. Good neighbouring
items survive. After two consecutive wholly failed batches the remaining items
receive processing unknowns/basic labelled guidance without more provider calls.
Unknown capability does not become an asserted institutional deficiency.
Quota exhaustion, cancellation, missing usage, configuration/programming errors
and overall cost/request/deadline limits keep their terminal handling.

## Thinking usage and configured prices

For Google's direct compatible endpoint, billable output is `total_tokens -
prompt_tokens`. The reported visible completion count is retained in the
capability ledger; a positive difference from that count is recorded as inferred
thinking when explicit details are absent. If explicit reasoning details are
present, they are not added to the billable total again. The same normalization
feeds extraction `AIUsage`, capability assessment and recommendation ledgers.
A missing or inconsistent Google total fails capability usage validation.
Other providers keep their own completion-token semantics.

Hosted Gemini capability requests require positive configured input and output
rates in `AI_PRICING_JSON`, including for free-tier accounts where these rates
serve as a conservative estimate. Zero rates remain valid for local models.
General extraction records hosted Gemini zero prices as unpriced, rather than
claiming that usage was free. Configure the exact model's rates before starting
new capability inference. This change does not rewrite historical cost rows.
There is no automatic price lookup or invented fallback price.
The existing default `$2` ceiling is unchanged. Enabling real prices can exhaust
that conservative reservation ceiling even when expected actual usage costs less.
Review the full request envelopes and choose an explicit authorized budget before
the next live run; raising output allowances increases each reservation.

For example, Google's standard paid Gemini 3.8 Flash prices checked on
2026-11-04 were $0.75 input, $3.75 output (including thinking), and $0.075 cached
input per million tokens through 2026-12-31. Google lists higher prices starting
2027-01-01. Verify the account, tier and current prices before configuring them:
https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash
The configured-price ceiling is an estimate; provider billing remains authoritative.

## Reading the diagnostic trail

Request reservations record stage, output allowance, effective timeout, reasoning
effort and the conservative input bound. Outcomes record safe exception class,
finish reason, normalized billable token usage (including reasoning tokens), and duration.
Preflight rejections record the measured bound without reserving an HTTP call.
Request hashes and schema hashes allow comparisons without publishing prompts.
Assessment traces and recommendation validation records retain split attempts,
affected requirement IDs and item-level processing failures. Billing reservations
remain conservative when the provider fails without returning usage.

For the private workload, capture the tested commit, exact model identifier,
endpoint type (direct Google or proxy), failed stage, frozen execution policy,
finish reasons, reasoning/output token counts, request durations, and split,
repair and fallback counts. Compare recommendations marked `model_tailored`
with those marked `deterministic_fallback` or `processing_rerun`; completion alone
does not establish useful model-generated advice. A database copy does not isolate external services: use a separate
`PINECONE_NAMESPACE` (and an isolated index where appropriate), or disable Pinecone
configuration in the test process. Otherwise extraction can write and prune
shared vectors even when all database writes target a copy. Do not alter the
active deployment's configuration merely to prepare a diagnostic process.
Keep document text, credentials,
private exports and institutional findings outside the repository.

## Validation

`apps.scoring.test_request_recovery` uses mocked SDK responses and checks typed
truncation, native Google schema handling, bounded splitting, isolation of child
IDs, preservation of valid advice, processing unknowns, fatal error propagation,
stage policies, whole-request preflight, deadlines and reasoning telemetry.
The full backend suite also exercises the existing extraction and scoring paths.
These offline tests do not validate live Gemini latency, its accepted parameters
for the deployed model, or reference-document assessment quality. Confirm those
with the private test report before merging this draft.
