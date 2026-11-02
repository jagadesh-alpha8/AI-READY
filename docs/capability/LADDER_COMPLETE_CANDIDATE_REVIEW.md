# Complete readiness candidate and proposed profile gates

Historical candidate 0.2 design review. The audited current candidate is 0.3 with profile rules 0.2; use `LADDER_CANDIDATE_AUDIT_2026_11_02.md` for corrections, current paths and commands. The files and examples below describe the prior revision.

Candidate 0.2, 2026-11-02. **Offline, experimental and not active.** This completes the assertion-level review begun in candidate 0.1; it does not claim empirical calibration.

## Completed work

All 216 requirements now have an explicit source mapping and separately adjudicated candidate identity: 72 foundations, 72 adoption requirements and 72 outcome requirements. The 144 adoption/outcome replacements are readable in `LADDER_ADOPTION_OUTCOME_REVIEW.md`; the full release is `ladder_candidate_v0_2.json`. Candidate 0.1 remains a historical snapshot. Even its foundation findings cannot be silently copied into the new version.

The review distinguishes enabling capacity, AI-specific preparation, observed AI activity, enabling/assurance practice, measured results and improvement practice. F/A/O remain source-stage labels; they do not mean Silver/Gold/Platinum and do not themselves form a capacity/activity/results headline.

The principal changes to adoption and outcomes are:

- Evidence of actual scoped delivery can establish activity without universal institutional deployment. Declared reach remains visible and must be verified separately before an institutional badge.
- A completed evaluation can establish measurement capability without waiting for two completed academic years. Sustained benefit still needs comparable repeated observations and cannot be inferred from first measurement credit.
- A follow-up evaluation need not report a positive result to demonstrate an institution's ability to learn. A null or adverse result can support measurement/improvement practice, while failing a separate positive-impact claim. The candidate must not be sold as an impact score.
- Records of agreements, plans or attendance do not establish delivery, competence or career outcomes. Generic digital operations do not establish AI-enabled operations. Broad enabling practice remains labelled separately.
- Intervention evaluations must disclose baseline, method and limitations. Correlation is not automatically AI causation. Dates and programme/cohort identity must support the actual assertion.

Some assertions deliberately retain necessary relationships, such as comparing a result with an objective. Removing the objective would weaken the claim rather than make it meaningfully more atomic. Administrative metadata and multiple independent capability claims are separated where possible; this is not a claim that every meaningful requirement consists of one noun and one verb.

## Overlap handling implemented

`experimental_candidate.py` assigns one experimental component budget to each of these paired areas:

| Shared credit group | Source indicators |
|---|---|
| Literacy provision | C3.2 and C5.1 |
| Student AI projects | C3.4 and C5.3 |
| Learning compute | C6.1 and C6.4 |
| Career pathways | C5.4 and C8.3 |

The other indicators retain separate groups, giving 32 groups. Within each F/A/O component, assertions are averaged within a group, then groups are averaged. This prevents each overlapping indicator from receiving an additional full budget. Shared evidence can still support distinct assertions; a citation is not itself a unit of score and is not automatically deduplicated away.

This is a reproducible weighting proposal, not proof that these are the only overlaps or that 32 groups deserve equal weight. In particular, project curriculum versus individual achievement, compute provision versus accessibility, and literacy provision versus learner attainment remain distinct claims inside their shared budget. Future calibration may separate their budgets with appropriate weights. Industry collaboration, applied inquiry and faculty skills also require cross-checking for reused beneficiaries/results. The experiment exposes group detail and assertion counts, and still returns **no headline score**.

## Profile and Silver gate prototype

`ladder_profiles_candidate_v0_1.json` proposes evidence routes for Engineering, Polytechnic, Arts & Science and ITI. An applied or vocational inquiry project can establish inquiry capability; a publication, patent or dedicated centre is not the only permitted evidence format. The profiles preserve all 216 assertions. They do not silently exempt an ITI from research or change a denominator because its type was selected.

The proposed Silver minimum combines accountable governance, AI policy application, privacy/risk assessment, security-response practice, assessed faculty literacy, delivered student literacy, an actual AI-enabled institutional service and at least one relevant teaching/project delivery route. Profile-specific alternatives concern that learning route. Most proposed gate requirements are intentionally common: institution type is not a reason to weaken basic safety or responsibility.

The checker additionally requires separately adjudicated institutional scope, currency and coverage checks and a critical-risk disposition. False verification or an open critical risk blocks the checklist. Unknown checks leave it unresolved. All positive requirements and context produce `satisfied_for_review`, never a badge. The profiles are explicitly uncalibrated and the engine refuses to treat them as calibrated releases.

These flags are **inputs from an evidence adjudication process**, not proofs created by the arithmetic engine. Coverage thresholds, acceptable risk/materiality definitions, consequential-use oversight, assessment validity and sufficient policy operation still need complete standards. The minimum checklist is therefore not an exhaustive Silver specification. Gold and Platinum gates are deliberately not inferred from numeric percentages; their sustained-impact and leadership standards remain to be designed and tested.

No consultant permission is needed to run an assessment, report, recommendation or hypothetical scenario. Formal achievement attestation, if introduced, is a separate product decision. No budget is mandatory; no prices, delivery promises or equal-cost routes are invented. Tasks and proposed plans never change the verified baseline.

## Executable checks and fixtures

The evaluator is isolated from production. Run this offline command from `backend`:

```sh
python manage.py evaluate_ladder_candidate \
  ../docs/capability/ladder_candidate_v0_2.json \
  ../docs/capability/ladder_profiles_candidate_v0_1.json \
  /path/to/newly-adjudicated-candidate-snapshot.json
```

A snapshot declares `methodology`, canonical-JSON `candidate_hash`, canonical-JSON `profile_release_hash`, `profile`, `decisions` and `gate_context`. Hashes are computed with `experimental_candidate.digest`; the command rejects release mismatches, old condition IDs and implicit N/A. Missing decisions remain unknown. Output includes input/release identities, exact rational bounds, per-group results, evidence-resolution counts and proposed-gate diagnostics. It performs no inference or assessment writes and prints no evidence passages.

Six synthetic, hand-adjudicated cases in `ladder_candidate_acceptance_cases.json` cover sparse digital capacity, scoped AI delivery with missing foundations, an approved plan without delivery, an open critical risk, conflicting literacy evidence and a complete proposed checklist that still does not award a badge. Extract a case object as a command snapshot for an offline smoke test. These cases test arithmetic and policy boundaries; they do not validate a model's interpretation of PDFs.

Twenty pure tests across the two candidate modules pass. The actual management-command handler also passes all six fixture snapshots and rejects a stale release hash, without database or provider access. They cover the six cases, all 216 mappings, independent partial credit, exhaustive possible-world bounds for the simple component engine, shared-budget saturation, all-met/all-negative extremes, profile denominator preservation, critical-risk/coverage blockers, unknown context, alternative learning routes, old-ID/N/A rejection, version binding, deterministic identities and immutability. The earlier 231-test scoring run applied to the preceding candidate commit; do not confuse it with a rerun of this extension.

## What is ready and what still requires evidence

The requirement rewrite, overlap proposal, draft profile routes, proposed Silver checks, executable comparison and acceptance cases are prepared without waiting on the SWE. The SWE can now exercise these exact artifacts rather than inventing a second implementation.

Next empirical work needs representative institutional evidence, fresh candidate adjudication with exact provenance, and independent subject-matter review. The same passages should first be compared under the old and candidate wording; retrieval improvements should be varied separately. Record disagreement and unsupported inferences instead of selecting whichever version produces a higher score. Resolve the earlier export's institution/period mismatch before treating it as a verified candidate baseline.

Threshold selection requires defensible readiness/achievement labels and stakeholder objectives. Synthetic tests cannot establish those labels, safe coverage thresholds or causal impact. We can propose and implement policies and run sensitivity tests, but should not describe self-authored fixtures as independent validation. Live activation remains a separate explicit methodology release after this evidence work; it is not blocked by an invented approval step.
