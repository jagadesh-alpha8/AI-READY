# Diagnosis implementation audit: reports, default scope and plan evaluation

2 November 2026. Audited against *AI_READY_Product_Diagnosis_and_Report_Prototype(1).pdf*,
pages 1–13, and current A1 at `f837d86a3ee1bdd43c3b9df30e03a7e17a25b532`.

## Current post-merge checkpoint

PRs #4 and #5 are merged into A1 at `eeeae893d27bdb64227180d7e4453f50aabc76ae`.
The open-PR checkpoints below describe the earlier passes, not the current remote state.
A subsequent independent audit found and corrected five additional context/failure/export/scope/
alternative-mapping defects on `a1-post-merge-audit`. See `POST_MERGE_AUDIT_2026_11_02.md`
and `SWE_TEST_HANDOFF_2026_11_02.md`. These corrections do not complete the review bridge,
question queue, ordinary initiative generator, single-action flow or methodology validation.

## Finding

PR #3 is merged into A1. Its ingestion/diagnostic fixes and PostgreSQL account-lock repair are
implemented and tested. Its contracts, rubric review inventory and worked report cases are
design material. They did not implement the reviewed-evidence bridge, question queue, default
scope inference or initiative recommendation engine. A merged, tested ingestion PR does not
establish that the full product diagnosis has been addressed or deployed.

PR #4 implements a read-only report projection and its HTML/PDF presentation against
the existing frozen assessment/advice contract. That report-only change does not change extraction, human-review
records, scoring arithmetic, thresholds or provider generation. The later scope/plan additions below add a separately metered plan interpretation path; they still do not change actual scoring arithmetic or activate a new rubric. The advice remains as useful
as the stored generation produced; better presentation is not evidence of bespoke advice.

## Requirement-by-requirement comparison

Updated for the scope/plan branch on 2 November. PR #4 remains open with all three required test/build jobs green; its report changes are included locally as a dependency, not merged into remote A1. Current A1 remains `f837d86a3ee1bdd43c3b9df30e03a7e17a25b532`.

| Diagnosis item | Status after this change | Evidence and remaining work |
|---|---|---|
| D01 Deployment and complete import | Awaiting operational evidence | Need API/worker commits, configured limits and a fresh reconciled import; no production access assumed |
| D02 Ingestion PR | Code merged; deployment unverified | PR #3 is in A1; additive migration and restart still need deployment confirmation |
| D03 Reviewed facts/resolutions in assessment | Contract only | `storage.evidence_snapshot` still supplies pages; coordinate actual record adapter with Jagadesh |
| D04 Availability versus activity | Contract only | No new declaration model or scoring rule activated |
| D05 Grouped review questions | Not implemented | No changes to engineer-owned normalisation/review services |
| D06 Initial 25-question budget | Not implemented | A report's five displayed follow-ups is not the question budget; deferred questions still need their own persisted queue |
| D07 Default identity and scope | Conservative implementation; semantic adapter incomplete | Start accepts an explicit default overview, freezes a versioned source-label inventory and unresolved identity/scope questions; custom callers retain their contract. Does not claim exhaustive semantic inference or rename the institution |
| D08 Claim-level currency | Partially addressed | Explicit activity-period, policy-interval and curriculum-regulation declarations stay distinct; prompts prohibit timestamp/current-operation assumptions. General semantic claim/date extraction and reviewed-claim integration remain open |
| D09 Authoritative score meaning | Partially addressed | Leadership report labels the recorded capability method and its experimental status; legacy score paths remain separate in the application |
| D10 Full rubric review | Candidate review exists | 216-condition matrix is proposed; no empirical validation or activation claimed |
| D11 Aggregation and tiers | Pending methodology work | No new weights, partial credit, applicability rules or tier cut-offs |
| D12 Repaired Vels baseline | Awaiting operational evidence | No score recalculated from the single-SSR example or synthetic preview |
| D13 Initiative records | Not implemented | Read-only action-area grouping is not a persisted, cross-pillar institutional initiative model |
| D14 Grounded conditional advice | Not implemented in generator | Basic report follow-ups say to check existing provision; generator restrictions and asset-grounded conditional advice still need revision |
| D15 Accepted facts as advice context | Not implemented | Do not substitute a renderer's narrative for the missing reviewed-evidence context |
| D16 Feasible prioritisation | Partially addressed in presentation | Earlier capability steps precede advanced outcomes; weight-only threshold scenarios move to supporting detail. Benefit, budget, prerequisites across initiatives and feasibility remain unassessed |
| D17 Advice at every layer | Partially addressed | Overall starting points, nine area results and 36 readable subarea cards/next steps; underlying advice quality still requires the advisory redesign |
| D18 One-action workflow | Not implemented | Assessment and advisory generation controls remain separate; exports continue to make no provider calls |
| D19 Explicit report/advice state | Implemented for completed assessments | No selected advice, pending, failed, cancelled, deterministic-only and empty tailoring are explicitly basic; valid model-tailored advice is labelled separately |
| D20 Plain-language view model | Implemented | Shared HTML/PDF projection; readable 9/36 labels, unknown versus shortfall, explanatory score ranges, suggested roles and completion evidence |
| D21 Leadership report and evidence export | Implemented | Default readable HTML/leadership PDF; separate full evidence PDF; raw JSON retained with an added presentation object |
| D22 Scope revisions | Implemented for completed assessment versions | Post-result refinement creates a labelled new run with parent identity, a new evidence snapshot and new dependent advice/scenarios; old records remain unchanged. Retry checks normalized intent before resolving again |
| D23 Substantive evaluation | Partially addressed | Automated presentation cases and visual PDF QA; real-corpus advisory quality and a blind business-reader review remain necessary |
| D24 Scenario planning | Experimental implementation; validation pending | User now requested this. Immutable original/suggested plans; separately metered scenario lifecycle; parse/map/separate semantic review; deterministic overlays, paired uncertainty bounds, delivery/results separation, original-action critique, optional budget envelope, comparison UI and HTML/JSON exports. Disabled by default pending deployment configuration and model/corpus quality evaluation |

## Implemented behavior

- Default HTML/PDF exports lead with the institution, saved population/period, score/status,
  evidence basis, readable pillar results and first follow-ups. A full 0–100 unresolved range
  reads **Not established**, never an estimated 50 or a zero score.
- The capability method remains explicit. A curriculum, attendance record or plan cannot gain
  adoption or outcome credit merely because its presentation changes.
- The report differentiates assessment uncertainty from advisory execution. Failed or unfinished
  advice produces a clearly labelled basic report while retaining valid assessment results.
  Completed deterministic evidence requests are also basic, never labelled bespoke.
- The HTML provides all 36 readable subareas and complete selected action instructions. The
  leadership PDF uses compact summaries and identifies where full instructions are available.
  Supporting evidence retains all conditions, citations, identities and conditional calculations.
- Exports check the assessment input digest, selected advice digest, run and assessment-event
  linkage, assessment payload hash and completed advice input hash. A mismatched stored pair
  is rejected with a safe 409 response rather than producing a mixed report.
- Page/source quotations remain original; generated condition references become readable
  area/stage labels. Django escaping, existing tenant checks and no-store/CSP headers remain.
- No inference, writes to assessment/advice histories, automatic score uplift or provider costs
  are introduced by report viewing/exporting.

## API compatibility and use

The report endpoint is unchanged. Add `audience=leadership` (default) or `audience=evidence`
for HTML/PDF. The evidence audience retains the previous full technical HTML/PDF behavior.
`file=json` retains the full canonical assessment and recommendation, adds `report_view`, and
uses format version `AIQIF-REPORT-0.2`. The deterministic replay validator still operates on
the unchanged assessment fields. Filenames include the audience to distinguish downloads.

The workspace now offers leadership PDF, printable HTML, supporting-evidence PDF and full JSON
downloads for the same selected assessment/advice version. It does not select a newer advice
version silently or generate advice during export.

## Verification and limits

Presentation fixtures cover sparse evidence, documented starting capability without delivery,
planning evidence, scoped shortfalls, contradictory sources, earlier-step ordering, different
advisory states, unchanged scope/results and mismatched frozen identities. They are synthetic
fixtures, not claims that real institutional evidence was interpreted correctly.

Targeted backend report/recommendation tests, frontend tests/build, migration checks and the
rendered synthetic PDF are checked for this change. The PR records final test counts and CI
results. No production inference, full-folder assessment, real institutional score validation or
deployment was performed. The preview is explicitly synthetic and carries no institutional score.

## Work still needed from Jagadesh

1. Deployed branch/commit for both API and workers, migration status and configured limits.
2. Fresh full-folder scan/import inventory, including skips, duplicates, supersession and failures.
3. Extraction completion/readability counts and a capability export from that same sprint.
4. Unmerged changes and actual reviewed-fact, resolution and declaration record/API shapes.

With those, implement the reviewed-evidence adapter and paired baseline first; then validate the
revised methodology and initiative recommendation pipeline. The report renderer can consume
that later assessment without pretending those missing integrations already exist.


## Additional independent fixes in the scope/plan branch

- Removed compulsory population/period entry from initial capability assessment. The remaining
  Sprint Setup academic-year label is now optional and blank, with no scoring-period implication.
- Updated assessment-start tour guidance to explain default overview and later refinement.
- Replaced the September status page's obsolete claims (no OCR, zero frontend tests, compulsory
  consultant approval, invented completion percentages, removed standalone modules) with an
  explicitly maintained implementation snapshot and open-work list. It makes no deployment claim.
- Added actual frozen scope/refinement provenance to assessment JSON exports.
- Plan interpretation uses bounded original-source asset passages. It does not substitute for
  accepted-fact context in the ordinary recommendation generator.

## What can proceed without waiting for the engineer

| Work | Next concrete step | External dependency |
|---|---|---|
| Grouped question queue, 25-question budget (D05/D06) | Implement and test a pure grouping/priority contract plus persisted presented/deferred counts; integrate actual review records later | Actual source/resolution shapes needed for final bridge, not for contract/fixture work |
| Conditional institutional initiatives (D13/D14/D16/D17) | Group requirements into useful initiatives with retained unknowns, documented assets, dependencies and benefit-first sequencing | Fixtures suffice initially; actual reviewed context needed for institutional validation |
| One-action orchestration (D18) | Explicit workflow state machine linking assessment and advice; preserve independent failures, retries and spending limits | Deployment configuration needed to run, not to implement |
| Methodology validation (D09–D11/D23) | Blindly score and critique fixed reviewed examples; compare methods before choosing weights/tiers | Domain review needed before activating a new method; no need to await a production export to build evaluation fixtures |
| Plan quality evaluation (D24) | Evaluate parser completeness, mapping entailment, constraint retention and practical critique on a reviewed plan set | Real configured provider required for empirical model evaluation; tests here use injected fixtures/mocks |

D03/D04/D15 remain an integration task: inspection of current public models alone cannot establish
whether the engineer has unpublished changes or an authoritative reviewed-evidence/declaration
contract. Build adapters against explicit fixtures now, then reconcile with the actual contract.
Do not describe those code gaps as fully blocked on an operational export.

## What genuinely requires operational evidence

D01/D02/D12: deployed API and worker commits, applied migrations and scan/request limits, full-folder
inventory including exclusions/supersession/failures, extraction/readability counts and capability
export from the same repaired sprint. A passing repository test cannot supply these facts.

See `SCOPE_AND_PLAN_IMPLEMENTATION.md` for the new contract, acceptance coverage and limitations.
