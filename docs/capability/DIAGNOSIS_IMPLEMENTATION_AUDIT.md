# Diagnosis implementation audit and readable-report change

2 November 2026. Audited against *AI_READY_Product_Diagnosis_and_Report_Prototype(1).pdf*,
pages 1–13, and current A1 at `f837d86a3ee1bdd43c3b9df30e03a7e17a25b532`.

## Finding

PR #3 is merged into A1. Its ingestion/diagnostic fixes and PostgreSQL account-lock repair are
implemented and tested. Its contracts, rubric review inventory and worked report cases are
design material. They did not implement the reviewed-evidence bridge, question queue, default
scope inference or initiative recommendation engine. A merged, tested ingestion PR does not
establish that the full product diagnosis has been addressed or deployed.

This follow-up implements a read-only report projection and its HTML/PDF presentation against
the existing frozen assessment/advice contract. It does not change extraction, human-review
records, scoring arithmetic, thresholds or provider generation. The advice remains as useful
as the stored generation produced; better presentation is not evidence of bespoke advice.

## Requirement-by-requirement comparison

| Diagnosis item | Status after this change | Evidence and remaining work |
|---|---|---|
| D01 Deployment and complete import | Awaiting operational evidence | Need API/worker commits, configured limits and a fresh reconciled import; no production access assumed |
| D02 Ingestion PR | Code merged; deployment unverified | PR #3 is in A1; additive migration and restart still need deployment confirmation |
| D03 Reviewed facts/resolutions in assessment | Contract only | `storage.evidence_snapshot` still supplies pages; coordinate actual record adapter with Jagadesh |
| D04 Availability versus activity | Contract only | No new declaration model or scoring rule activated |
| D05 Grouped review questions | Not implemented | No changes to engineer-owned normalisation/review services |
| D06 Initial 25-question budget | Not implemented | A report's five displayed follow-ups is not the question budget; deferred questions still need their own persisted queue |
| D07 Default identity and scope | Not implemented | Export preserves the saved scope; it does not infer or rename institutions |
| D08 Claim-level currency | Not implemented | Export retains saved population/period and limitations; no new activity-date inference |
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
| D22 Scope revisions | Not implemented | Existing frozen versions remain unchanged; no new scope-edit/revision interface |
| D23 Substantive evaluation | Partially addressed | Automated presentation cases and visual PDF QA; real-corpus advisory quality and a blind business-reader review remain necessary |
| D24 Scenario planning | Deferred | No plan-entry or simulator interface introduced |

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
