# Bounded correction of model decision failures

New assessments use prompt AIQIF-EVAL-0.8, the unchanged independent 0.3 rubric/engine and retrieval assertion-balanced-windows-0.3. This release fixes incomplete model outputs without changing evidence requirements, numerical weights or historical assessments.

The output schema now requires a named property for every requested condition. This prevents a strict schema implementation from emitting six copies of one ID while omitting other IDs. Historical list-shaped decisions remain readable and are still validated for duplicates, scope, period and quotations. Keyed values cannot override their property identity.

After an incomplete or invalid response, the evaluator makes at most one extra corrective batch for the failed requirements in that indicator. Successful initial decisions are preserved. The correction sees the same exact source windows and only the failed requirements, not speculative earlier positive claims. Ordinary valid unknowns do not trigger a paid correction. A correction can still return unknown. No missing response or unsupported quotation receives points. Initial and corrective response audits are retained separately; the assembled audit is explicitly labelled.

All SDK calls, including correction and provider-format fallbacks, pass through the existing request/cost reservation boundary. The total configured request and USD limits remain unchanged. Exhaustion, cancellation and provider exceptions retain the existing terminal behavior; no extra allowance is granted. Per-indicator input limits remain unchanged. `indicator_calls` counts initial indicator evaluations; `correction_calls` counts logical corrective batches, not total billed requests. The inference ledger owns actual SDK accounting.

The OpenAI-compatible JSON reader also rejects duplicate object members and invalid outer JSON instead of silently retaining the final member or salvaging a nested fragment. Fenced or prose-wrapped complete values remain supported. A compatible provider may use its existing bounded corrective retry; that request is also metered. Parsed historical exports cannot establish whether duplicate keys occurred in an original provider string, so this safeguard does not claim that specific historical cause.

Prompt guidance makes the exact assertion authoritative: an AI-themed title does not introduce an AI requirement into a digital-or-AI enabling assertion. General enabling provision still cannot establish AI use, skills, workload suitability or outcomes.

## Test and rollout

Deploy matching A1 web and workers, restart both, and inspect `python manage.py readiness_smoke_test`. The expected prompt is now AIQIF-EVAL-0.8. Run the opt-in synthetic provider probe before a fresh institutional assessment. Confirm all required decisions return and inspect initial/corrective audits when they do not. The actual provider must still be evaluated for semantic correctness; synthetic SDK fixtures are not a live-provider result.

One summary document can omit syllabus, governance, training or delivery evidence located in other files. Adding those files can improve coverage, but cannot repair malformed model responses. Verify institution, programme and period compatibility before combining them. Neither document count nor generic digital provision proves AI adoption. An all-unknown remainder cannot be converted into a point estimate by arithmetic changes.
