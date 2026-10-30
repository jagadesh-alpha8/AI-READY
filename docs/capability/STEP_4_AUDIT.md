# Independent Step 4 audit — 30 October 2026

Scope: handoff, live branch/PR state, scoring/planning, frozen storage, provider metering,
authorization, worker lifecycle, usage accounting, and the recommendation integration boundary.
The handoff's feature-branch instructions override older A1-only direct-upload instructions.

## Starting state verified before implementation

- GitHub branch search and `git ls-remote` agreed: A1 at
  `eb2d0d9d105873c784309f554952fe91d3647adc`; main at
  `6fbfa988112330874a3df1d3b41a8b3c401ad166`. No published engineer branch or open PR was visible.
- A1 contained Steps 1–2, but none of the 16 files/changes in the tested Step 3 delta.
- Verified the incremental bundle and inspected its diff before importing exact commit
  `2d72b8efd078d1ac55a5918fc8137465c6fe4edd` by fast-forward onto the new local
  `a1-step4-recommendations` branch. Remote A1 was not moved.
- The earlier checkout had an untracked optional workflow. It was left untouched; implementation
  uses a separate clone. No applicable AGENTS.md was found in this checkout.

## Findings and implementation decisions

| Finding | Consequence | Resolution |
|---|---|---|
| Step 3 MeteredService assumes an active assessment ledger and appends assessment events | Reusing it directly would reopen or modify completed assessment history | Extract ledger hooks in the existing meter; separate recommendation snapshot, execution and events |
| Immediate next-level actions omit conditions needed for later tier scenarios | Tailoring only that list would leave tier pathways without advice | Deterministic union of next-level, next-overall and all three tier requirement IDs |
| No versioned next-overall threshold policy | A hardcoded target could masquerade as an agreed product rule | Pin explicit experimental policy AIQIF-NEXT-0.1; select target using exact weighted levels |
| Missing evidence does not prove a capability shortfall | LLM intervention advice could prescribe unnecessary purchases or development | Unknown actions receive deterministic scoped evidence requests and are excluded from model payloads |
| Conflicting sources require reconciliation | Advice could suppress the inconvenient side of a conflict | Retain all conflict citations; operation fixed to source reconciliation |
| Model dependencies may introduce cycles or unknown action IDs | Unsafe or incoherent action ordering | Restrict dependencies to the current indicator batch and reject cycles; cross-indicator dependencies are not invented |
| Existing recommendation/CRI workflows represent different semantics | Reusing their records could imply score changes or legacy approval requirements | Add capability-specific endpoints and independent user workflow state |
| Advice generation can fail after billable requests | Partial advice must not appear as a complete institutional plan | Atomic completed artifact; all-or-nothing tailoring publication, pinned deterministic fallback, bounded request reservations |

## Review boundary and limitations

Grounding validation establishes exact condition/citation membership and constrained operation types.
It does not prove semantic entailment of every proposed step, sensible effort estimates or advice quality.
Suggested roles are hypotheses, not confirmed institutional positions. Proven-shortfall and contradiction
prose still require corpus-based quality evaluation; source prompt-injection defenses need live testing.

The scorer, assessment records, legacy CRI and baseline approval records are unchanged. Action completion
updates workflow only. No existing consultant approval gate is added. Recommendation inference defaults off.

Real provider output quality, provider billing guarantees, PostgreSQL concurrent starts, Redis/Celery
delivery and worker termination remain integration checks. Application-level immutability does not protect
against privileged raw SQL. Raw source retention and access policy remain inherited operational concerns.

The PR initially includes the exact Step 3 prerequisite plus separate Step 4 work. After the engineer's
Step 3 PR lands in A1, reconcile the feature branch against his actual changes. Do not replace his files
wholesale or force-push a shared branch. No merge or deployment is authorized here.
