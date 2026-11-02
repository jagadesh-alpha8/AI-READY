# Post-merge audit and corrections

2 November 2026. Audited A1 at `eeeae893d27bdb64227180d7e4453f50aabc76ae`, after PRs #4 and #5 merged.
Corrections are isolated on `a1-post-merge-audit`. Main and production configuration are unchanged.

## Conclusion

The merged code is suitable for focused SWE integration testing. It is not evidence that the
complete intended product flow, the real institutional baseline or the score methodology has been
validated. The earlier automated suite covered arithmetic, provenance and execution well enough to
miss several gaps in model context, partial failure and exported warnings. This audit adds direct
regressions for those gaps rather than treating green CI as substantive product validation.

## New defects found and corrected

| ID | Severity | Finding before correction | Correction and verification |
|---|---|---|---|
| A01 | High | The plan improvement model received the plan, rubric, mappings and bounded asset passages, but not the assessed baseline or original calculated scenario results. Arithmetic was correctly pinned, yet the critique lacked essential institutional context. | Mapping, challenge and improvement calls now include the pinned condition states and compact actual-standing summary. Improvement also receives original conditional results. Request-content tests assert that the model actually receives them; unknowns/conflicts remain unresolved capability, not absence. |
| A02 | High | Failure during improvement or revised-plan interpretation hid a successfully completed original review. Only the final comparison was exposed. | Save the validated original review before improvement; retain it on later request-budget/provider/validation failure. API, UI and HTML/JSON exports expose it explicitly as an original-only review, without inventing an improved plan. Saved content, plan identity and baseline identity are checked. A three-request cap reproduces this failure and verifies preservation and unchanged actual standing. |
| A03 | High | Scope/identity warnings were visible in the workspace but not prominent in the leadership report. A shared report could lose a source-institution mismatch or refinement qualification. | Readable HTML/PDF carry source-scope/identity notices before the result and retain them in limitations. Identity review keeps the report provisional without changing canonical scores. Plan HTML also retains scope questions. Tests check HTML, first-page PDF text, score/history preservation and refinement wording. |
| A04 | Medium | Scope-label regex whitespace could cross a newline: an empty `Institution name:` or `Programme:` could consume the next field as its value. | Match horizontal whitespace only, exclude CR/LF from values and ignore blank values. Regression covers blank population/identity labels followed by valid year/regulation fields. Matching source labels remain unverified candidates, not verified ownership. |
| A05 | Medium | For duplicate complete mappings, one later results-dependent alternative moved the entire requirement to the results phase, even when an independent delivery-only mapping already sufficed. Adding an alternative could therefore reduce delivery credit. | Keep a sufficient delivery-only path when present; outcome/competence requirements are still forced to the results phase. Requirements count once, alternative mappings remain traceable, and contradictory presence/withdrawal actions are still rejected. Regression verifies unchanged scenario results after adding the later alternative. |

Plan interpretation and scenario protocol versions advance to 0.2. Queued plans pinned to the old
protocol fail safely and need an explicit new request; completed old comparisons stay readable.
Scope adapter/projection versions also advance. No schema migration or new score weights/tiers are
introduced by these corrections. Existing scoring 0012/extraction 0017 from PR #5 are still required
for deployments that have not applied them.

## Important gaps that remain

| Area | What the code currently does | What is still missing | Testing consequence |
|---|---|---|---|
| Reviewed evidence (D03/D04/D15) | Capability snapshots freeze document pages. Fact confirmation, verification and conflict-resolution services exist separately. | The authoritative adapter for accepted facts, resolutions and authorised declarations, with same-scope precedence and history. | Do not mark an edited fact or a resolved conflict as affecting the score merely because the review UI changed. Demonstrate that the specific decision entered a new snapshot; currently that bridge is not implemented. |
| Short review flow (D05/D06) | Individual fact/exception review and a guarded bulk-confirm endpoint exist. Verification defaults to shadow mode; high LLM confidence alone does not authorise automatic confirmation. | Grouped material questions, persisted presented/deferred status and an initial maximum of 25 questions. | Record actual review workload. The new report's five starting points are not a 25-question queue. Do not bulk-confirm all facts to conceal this gap. |
| Scope and currency (D07/D08) | Explicit-label source inventory, source-specific default overview, strict original rubric scope and immutable custom refinements. | General semantic claim-level beneficiaries, dates and identity interpretation; integration with reviewed claims. | A regex inventory is not complete inference. Test narrative/table/OCR sources and record missed labels or ambiguity. Historical attendance cannot prove current competence. |
| Ordinary recommendations (D13–D17) | Condition-based guidance; unknown conditions are limited to evidence requests, while documented shortfalls allow development advice. | Persisted cross-pillar institutional initiatives, conditional practical suggestions on sparse evidence, accepted-fact context, asset reuse and benefit/feasibility-based sequencing. | Sparse NAAC evidence can still produce a readable but document-request-heavy report. The new plan critique does not replace this unfinished ordinary recommendation generator. |
| Single-action workflow (D18) | Assessment and advice are separate explicit jobs. Exports are inference-free. | Orchestration of important questions, assessment, advice and final report with coherent status/retry limits. | Test the actual separate steps; do not claim upload-to-bespoke-report is complete. |
| Methodology (D09–D11/D23) | Existing experimental cumulative capability method with fixed weights, gates and uncertainty bounds. | Empirical rubric/aggregation/tier validity and selection of the proposed revised readiness method. | Code correctness does not validate an institutional readiness score. No candidate rubric activation is part of this audit. |
| Live plan interpretation (D24) | Structured parse, exact citations, separate model challenge, deterministic overlays and plan comparison. | Reviewed-example measurements of parser completeness, semantic mapping, constraint retention and practical usefulness. The same configured model performs the separate challenge pass. | Mocked tests do not establish live accuracy or independence of review. Keep plan evaluation disabled in production pending staging evaluation. |
| Plan interfaces | Text input, separate HTML/JSON plan-comparison exports. | Direct plan-document upload and integration of the comparison into the leadership assessment PDF. | These are absent features, not upload/PDF bugs the SWE should spend time troubleshooting. |
| Production evidence (D01/D02/D12) | Ingestion fixes are merged. The assessment manifest intentionally contains active, non-rejected current sprint documents. | Deployed API/worker versions, applied migrations, configured import limits, full Drive inventory and a repaired same-sprint baseline. | The assessment source manifest is not a complete Drive scan or a record of all rejected/superseded/skipped files. Obtain and reconcile the import inventory separately. |

## Audit boundary

Inspected scope/start/idempotency, immutable snapshots and scenarios, interpretation payloads,
conditional arithmetic, provider accounting/cancellation, report identity/projection, UI/history,
existing fact-review guards and the earlier D01–D24 audit. No production environment or real corpus
was accessed. No live provider evaluation or new institutional score was generated.

Targeted regression results and the full scoring-suite result are recorded in the PR. The SWE
handoff is `SWE_TEST_HANDOFF_2026_11_02.md`. It separates expected implemented behavior from known
missing functionality and requires concrete exports/log evidence instead of a generic “tested OK.”

## Local verification

All 213 scoring-module tests passed, including 52 focused scope/plan/report checks. All 161
frontend tests and the production build passed. Migration-drift/configuration and whitespace
checks passed (expected unconfigured AI-key warning for offline tests). PDF export regressions
check the first-page warning text and existing long-scope layout boundaries. No browser visual
or real-provider semantic validation is claimed; T14 and the live plan cases remain SWE work.
Full repository SQLite/PostgreSQL CI is requested by the audit PR; local verification here does
not claim that full remote run has already completed.
