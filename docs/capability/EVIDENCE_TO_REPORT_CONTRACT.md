# AI Ready: evidence-to-report implementation contract

2 November 2026 · Working draft v0.1 · Prepared for Siddharth and the AI Readiness team

## 1. What this work advances

This document turns the diagnosis into proposed implementation rules and worked acceptance cases. It advances D03–D11 and D13–D23 at the contract/design level. It does not establish that those features are implemented or validated in production. D01–D02 deployment/import verification and D12's repaired institutional baseline remain dependent on operational evidence.

The intended experience remains: upload documents → Assess institution → answer a small set of important questions → receive a readable, shareable report → optionally refine its scope. No compulsory population/period form, consultant approval gate or scenario-planning interface is introduced.

### Current source checkpoint

Read during this session:

| Source | Observed state | Consequence |
|---|---|---|
| Attached diagnosis, pages 1–13 | Product requirements and D01–D24 backlog | Requirements baseline for this contract |
| A1 branch | `d468458410b438282efe1796905392c9d19cff05` | Same branch head recorded in the diagnosis |
| PR #3 | Open, draft, unmerged; head `cf79c107448ea378fbfc24123f69c8c3985cb982`; targets A1 | Ingestion fixes and rubric proposal are not assumed deployed |
| PR #3 rubric revision draft | Revises 36 foundation pairs; proposes separate enabling readiness and demonstrated AI activity | A proposal, not an activated methodology |
| A1 `engine.py`, `storage.py`, `recommendations.py` | Inspected at the pinned A1 commit | Basis for the integration observations below |

This checkpoint describes the initial contract-preparation pass, before the ingestion PR follow-up. That pass changed no application code, remote branch, deployment or active rubric and performed no new full-corpus assessment. The later ingestion changes and checks are recorded in `INGESTION_AUDIT_HANDOFF.md`; the later methodology proposal is in `METHODOLOGY_REVIEW.md`. This contract's proposed field names are conceptual and must be mapped to the engineer's actual models before integration.

### What can proceed now

- Specify the reviewed-evidence boundary, declaration rules and report states.
- Review rubric meaning and build fixed examples for methodology comparison.
- Develop initiative grouping, report presentation and quality evaluation against fixtures in isolation.
- Prepare the integration adapter once the engineer supplies the actual record shapes.

What still needs the engineer: deployed API and worker commits, applied migrations, configured scan limit, full-folder inventory with failures and supersession, same-sprint capability export, and details of unmerged work. Public branch state cannot establish what is deployed or being edited elsewhere.

## 2. The reviewed-evidence boundary

### Proposed frozen assessment input

| Record | Minimum content | Rule |
|---|---|---|
| Source manifest | Stable document identity/version, source path, checksum, processing status, readable/failed pages, supersession | Include failed and excluded sources in the inventory; do not treat them as evidence of absence |
| Source passage | Source ID, document version, PDF page, text and text hash | A quotation must match the frozen passage |
| Claim | Claim ID, subject, attribute, value/unit, institution, programme/unit, population, activity/effective dates, source links, review state | Preserve the narrowest supported scope; accepted means accepted as evidence, not automatically sufficient for a criterion |
| Review decision | Decision ID/version, reviewer, time, affected claim IDs, chosen value or disposition, rationale and scope | A decision resolves only the stated discrepancy; rejected alternatives remain historical |
| Declaration | Declaration ID, authorised respondent identity/role, exact answer, time, activity state, document availability, scope and qualification | A human answer has its own provenance; never fabricate a source-page quotation |
| Open issue | Issue ID, affected claims/requirements, unresolved alternatives, materiality reason and queue status | Omitted/deferred questions remain visible to the evaluator |
| Assessment scope | Selected institution, inferred identity/basis, evidence periods, population/unit scope, limitations and later user edits | Uncertain scope is explicit; upload dates are not activity dates |
| Methodology | Rubric snapshot/hash, scoring/aggregation version, declaration policy and applicability rules | One report must name one authoritative assessment method |

Snapshot identity covers all of these records, not just PDF pages. Freeze the relevant revisions atomically, or read them against a consistent revision token. If consistency cannot be established, retry snapshot creation rather than combining records from different moments. Institution and sprint checks apply to human records as well as documents.

### Precedence and invalidation

1. A valid same-scope review decision controls the disposition of the specific alternatives it resolves. The evaluator sees both the resolution and its source history.
2. The next run must not reopen the same discrepancy merely because both original passages still exist. The decision does not prove unrelated criteria or override a newer contradictory source.
3. New material evidence or a changed scope can invalidate applicability of a prior resolution. Record why it was reopened; do not silently discard the resolution.
4. A reviewer changing a numeric value must record its basis. A selected value is not independent verification of institutional performance.
5. Duplicate copies do not create multiple independent confirmations. Preserve all provenance while grouping equivalent content.

### Keep three meanings separate

| Dimension | Proposed values | Meaning |
|---|---|---|
| Document availability | Available; unavailable; unknown | Whether the requested record can be supplied |
| Activity state | Reported present; reported absent; planned; in progress; unknown | What the respondent says happens |
| Criterion decision | `met`; `not_met`; `unknown`; `conflicting` | Outcome under the pinned rubric and evidence rules |

Partial support belongs in the finding and evidence explanation. Do not add a fifth engine state to A1 without explicitly versioning and implementing its arithmetic. For a two-part requirement, one supported part can be described while the unsatisfied evidential part remains unknown.

### Declaration policy

| Answer | Evidence treatment | Scoring treatment | Appropriate advice |
|---|---|---|---|
| We do it; document unavailable | Unverified positive declaration, scoped and dated | Does not by itself prove operational use, competence or outcomes | Explain how to substantiate existing work; offer conditional next steps |
| We do not do it | Scoped negative declaration | `not_met` only where the rubric permits that respondent and declaration type for that criterion | Suggest establishing the activity using documented assets |
| It is planned | Record plan and approval/stage evidence | Only explicit planning conditions can receive credit | Identify the next implementation step and what evidence it would produce |
| It is in progress | Record what is actually complete | Award only requirements already satisfied, not projected completion | Distinguish completed work from remaining work |
| I do not know / cannot access it | Record uncertainty and request closure for this version | Remains `unknown` | State the limitation without repeatedly asking the same question |

A negative declaration is not a blanket institutional negative. A programme coordinator's answer about one programme cannot establish absence across all departments. Reopen a closed request only for a material new reason, which must be explained.

## 3. Review queue and default scope

### Group one decision, not many facts

Use a grouping key based on institution, entity, attribute, compatible units, population and relevant period. Normalise equivalent dates and units before identifying a conflict. Different departments or years are ordinarily different observations. Related requests can share one question only when one answer genuinely resolves them; the interface must show the scope of that answer.

Use this proposed deterministic ordering, with a stable ID as the final tie-breaker:

1. Institution identity and other issues affecting validity of the whole assessment.
2. Same-scope contradictions affecting a criterion, report finding or recommendation.
3. Uncertainty preventing a consequential criterion decision or feasible first action.
4. Lower-impact clarification and supporting detail.

Within a category, prefer issues with broader valid impact and fewer alternative requests. Use score impact only when calculable under the pinned method. Do not invent an expected uplift or a numerical probability of resolution.

### Initial budget

- Target 15–20 grouped questions, with at most 25 presented in the initial review flow.
- Count the grouped questions already presented, not only answers submitted. Do not refill the queue indefinitely to evade the budget.
- When fewer questions are useful, ask fewer. The target is not a quota.
- Question 26 and later remain in the assessment's unresolved set. Show how many material issues remain, their affected areas, and the consequence for confidence in the findings and numerical bounds.
- The administrator may finish early and receive a provisional report. Offer a focused follow-up separately; no consultant approval is required.

The budget covers grouped review questions, including essential scope clarifications. It does not imply that 25 questions can validate an arbitrarily poor or incomplete corpus.

### Default assessment scope

Start with a provisional “latest evidence-supported institutional overview.” Resolve identity using source identifiers and the selected institution; flag a material mismatch. Hold institution-specific assertions whose attribution is unresolved, while still producing a report explaining the limitation.

Attach scope and dates to each claim. A currently effective policy, a curriculum under a stated regulation, and a past cohort's attendance can coexist in a mixed-period baseline, but must retain their distinct meanings. Do not pool incompatible denominators, sum overlapping cohorts, infer current delivery from a syllabus, or extrapolate a departmental example institution-wide.

Unknown population size can prevent a percentage or universal-access claim without preventing a supported existence finding. Later period/population edits create a new assessment/report revision.

## 4. Methodology review before activation

### A decision the existing documents leave open

The PR #3 rubric draft proposes separate enabling-readiness and AI-activity scores. The later diagnosis proposes one headline AI readiness score with explicit capacity, activity and results components. These are not equivalent presentation choices: combining them changes the construct being measured.

Proposed direction for review: retain one eventual headline score and nine readable pillar areas; show the contribution of enabling capacity, demonstrated AI activity and measured results. Keep unresolved evidence separate from those components. Do not publish a composite until component definitions, weights, aggregation and missing-evidence behavior have been reviewed together. Meanwhile, supported narrative findings and an explicitly incomplete report remain useful.

This is a design recommendation, not a claim that weights or thresholds have been agreed. Do not multiply readiness by evidence coverage, average only known items, or use the midpoint of unknown bounds as the headline. Each can make missingness look like performance or create unjustified precision.

### Why changing foundation wording is insufficient

A1 requires 36 indicators, six conditions per indicator and cumulative F/A/O stages. Its stage scores are 0, one-third, two-thirds and full credit; later stages cannot supply missing earlier prerequisites. The draft changes 72 foundation conditions but leaves 144 adoption/outcome conditions needing semantic review. A general digital foundation followed by an AI-specific adoption requirement may be defensible, but the transition and its score meaning must be explicit.

Create one review row for every condition, covering:

| Review field | Required decision |
|---|---|
| Construct | Enabling capacity, AI-specific activity or measured results |
| Substantive requirement | What must actually be true, independently of document titles |
| Stage credit | Why this requirement belongs at its stage; whether cumulative prerequisites are justified |
| Scope and denominator | Which programme, users, systems or projects count; coverage needed for the claim |
| Currency | Activity period, policy effective interval, or other applicable date rule |
| Admissible evidence | Equivalent sources, declarations allowed, and evidence insufficient on its own |
| Counterexample | A plausible-looking document that must not receive this credit |
| Score effect | Explicit arithmetic, applicability treatment and relation to tiers |
| Plain-language finding | How a business reader would understand satisfaction and uncertainty |

Start with curriculum (C3.1), faculty learning (C4.1), advanced student pathway (C5.2), computing suitability (C6.1), learning environment (C6.4) and innovation support (C7.2). Use AI-system governance (C2.3) and security (C6.3) as checks against over-crediting general IT evidence. This is a review sample, not validation of all 216 conditions.

### Score publication rules proposed now

- Preserve exact arithmetic internally; round for display only.
- An exact numerical score is publishable only when the pinned method yields a single defensible value and its assessed scope is supported. This need not require every condition to be resolved if remaining uncertainty cannot change that value.
- Where unresolved decisions can change the score, retain bounds and explain them. A 0–100 bound is not a useful point estimate; use “Not established” prominently.
- An exact mathematical result under an experimental method is still experimental. It is not independent validation of the institution or the method.
- Do not award Silver/Gold/Platinum using draft revised criteria with old unreviewed thresholds. Keep tier eligibility unavailable until the release defines those rules coherently.
- Use the same frozen corpus for old/new methodology comparison. Classify changes as evidence, review resolution, scope, methodology or presentation effects. Higher scores alone are not proof of improvement.

## 5. Initiative-level recommendations

### Proposed recommendation record

Each initiative has: a reader-facing title; why it matters; linked findings and requirements; cited existing assets; an evidence-status-aware opening; concrete steps; suggested responsible role; dependencies; deliverable; success check; effort assumptions; remaining unknowns; and any defensible score implication. Link it to the exact assessment snapshot and advisory version.

Group requirements sharing a real activity or deliverable. One inventory or training pathway can support several areas. Show it once with several links; do not award the same evidence multiple independent score increments. Separate linked criteria still require their own decisions under the rubric.

### Advice rules

- For demonstrated absence: explain how to establish the capability.
- For uncertainty: first check existing provision, then give conditional steps if it is absent or incomplete. The report must never convert “not found” into “does not exist.”
- For contradictory evidence: resolve the specific discrepancy before choosing an intervention that depends on either alternative.
- For documented strengths: explain how to use or extend them within their proven scope. A centre name alone does not establish an active mentoring service.
- Suggested roles are suggestions. Do not invent a named officeholder, available budget, staffing level, deadline or infrastructure specification.
- Existing accepted facts from across the institution may support an initiative, provided their provenance, scope and dates are supplied. Citation access must not be limited to one condition's attached excerpts.
- Score improvement is not automatic when a task is checked off. New evidence must satisfy the relevant criteria in a new assessment. Numerical uplift remains unavailable when baseline or assumptions are unresolved.

### Proposed priority policy

Respect prerequisites first. Then consider institutional benefit, reuse of demonstrated assets, feasibility and uncertainty, with a written reason for the order. Avoid presenting a weight-sorted arithmetic path as the preferred institutional plan. If effort is unknown, say what must be checked before estimating it. Do not invent numerical utility weights at this stage.

The institution summary selects three to five priorities; each pillar and subarea links to its relevant initiative or explains why no new action is justified. This supplies advice at every layer without producing 36 unrelated projects.

## 6. Report and workflow contract

Keep assessment completeness and advisory generation as separate state dimensions:

| Dimension | States | Reader-facing consequence |
|---|---|---|
| Assessment | Complete; provisional; failed | Show supported results, uncertainty, or an explicit inability to assess |
| Advisory | Pending; tailored and validated; basic fallback; failed | Clearly distinguish bespoke advice from a basic report |
| Revision | Initial; revised with reason | Identify the period/population and why this version differs |

“Complete” means the assessment process completed under its contract; it does not mean every capability is known. A provisional assessment can still have tailored advice. An advisory failure must not overwrite valid assessment results.

One user action orchestrates the workflow, with an intentional review pause where needed. Resume from persisted answers. Use stage-specific idempotency tied to the snapshot and generation request so ordinary retries do not create duplicate runs or inference calls. Explicit regeneration creates a new advisory version. Report viewing/exporting reads stored content and never starts paid inference.

### Leadership report outline

Aim for five to eight pages when the material supports it; use a separate appendix for detail.

1. Institution, assessment basis, headline result/status, key limitations and three to five priorities.
2. Nine-pillar overview with readable labels, score/status and useful next action.
3. Key strengths and constraints, distinguishing documented capacity, activity and results.
4. Prioritised initiatives with first steps, suggested owners, dependencies and completion evidence.
5. Scope, score meaning, material unresolved issues and how to refine the assessment.

Readable subarea cards and source detail can continue in a companion appendix. Each card explains the question, supported finding, uncertainty and next step. Main pages use human titles, not raw condition IDs. Neutral styling represents unknowns; poor-performance colours require demonstrated shortfalls.

For a report with no defensible score, keep the same useful hierarchy. State “Overall score: Not established”; explain the reason and provide supported findings and actions. A report must remain available even when an exact numerical score is not.

## 7. Worked acceptance cases

These are proposed fixtures and expected behavior, not executed application tests. All invented institutions, counts and source labels below are synthetic. The Vels example is separately identified as derived from the diagnosis rather than newly verified here.

| Case | Input | Required result | Must reject |
|---|---|---|---|
| T01 Sparse evidence | A readable general SSR; no AI-specific candidate passages | Unknown AI activity; conditional, practical advice; score bounds or Not established | Zero readiness inferred from silence |
| T02 Documented curriculum | Approved BBA syllabus with substantive ML content and applicable regulation; no delivery/assessment records | Curriculum finding only, subject to the full criterion; next step checks delivery and assessed work | Student competence, universal access or current delivery asserted |
| T03 Planned work | Approved future AI module with a named responsible role but no delivery | Credit only explicit satisfied planning requirements; implementation remains unestablished | Adoption/outcome credit from the plan |
| T04 Scoped absence | Authorised programme respondent declares no AI training in that programme during a stated period | Negative decision only for criteria permitting that declaration and scope | Institution-wide absence or multiple unrelated negatives |
| T05 Missing document | “We run the activity but cannot supply its records” | Unverified positive declaration; availability unavailable; criterion unknown unless other sufficient evidence exists | `not_met` because no document, or `met` solely from the assertion |
| T06 Resolved contradiction | Two same-period records disagree on participation; an accepted scoped resolution selects one with a recorded basis | New snapshot includes resolution; use chosen value only where applicable; retain rejected claim historically | Reopening the identical discrepancy every run |
| T07 False conflict | Marine department founded in 1920; mathematics department founded in 1930 | Two compatible claims; no conflict question | Grouping on “founding year” without entity identity |
| T08 Mixed periods | Currently effective 2024 policy; 2022–23 attendance; regulation-2024 syllabus | Distinct dates and scope; labelled mixed-period findings; current participation unresolved | One global current-year label applied to all evidence |
| T09 Budget overflow | 30 material grouped issues after deduplication | At most 25 presented initially; five deferred issues retained in findings/bounds; follow-up optional | Deleting, auto-accepting or hiding the rest; endless refill |
| T10 Asset reuse | Documented AI-centre existence; current lead/service unknown | Verify the existing support route before proposing a new centre; cite the existence claim | Invented active services or immediate purchase/build advice |
| T11 Import failure | Training evidence is an unreadable PDF; other files processed | Processing limitation and recovery step; affected capability unresolved | Institutional absence inferred from the unreadable file |
| T12 Advisory failure | Assessment persisted; tailoring provider fails | Useful labelled basic report; retained score/status and evidence; explicit advisory retry | Fallback labelled bespoke; export silently triggering inference |
| T13 Identity mismatch | Selected profile ABCD; sources identify VISTAS | Material identity question; attribution-sensitive claims withheld pending resolution; useful limitation report | Automatic rename or attaching VISTAS findings to ABCD |
| T14 New scope revision | User narrows the cohort or changes the reporting period after first report | New snapshot and labelled report; previous version unchanged; explain scope effect | Old score overwritten or change reported as institutional improvement |
| T15 Weak participation evidence | Attendance list shows 40 faculty at an AI session; no eligible-faculty denominator or assessed task | Scoped participation finding; no percentage or competence claim | “40% trained” or “AI-competent faculty” |
| T16 Shared initiative | One access inventory supports infrastructure and teaching preparation | One initiative with multiple links; criteria assessed independently; unique evidence/dependency handling | Duplicate projects, repeated requests or automatic additive score credit |
| T17 New contradictory evidence | A later same-scope source challenges a previously resolved value | Reopen with a material-change reason and retain prior decision history | Permanent suppression of all future contradictions |
| T18 Immaterial unknown | Some unresolved conditions cannot change a stage already capped by a valid unmet prerequisite | Preserve unresolved findings; exact arithmetic may still be possible under the pinned method | Requiring every unknown to be answered solely to compute an unchanged score |

### Vels content anchor, not a new baseline

The diagnosis describes an AI centre and incubation support in SSR excerpts and AI/ML content in a BBA syllabus. Those observations support a candidate initiative: “Confirm the existing AI support route and connect it to a documented learning pathway.” First identify current contacts/services and the relevant course/cohort; then inspect delivery and assessed work. Do not claim the centre is currently active, all learners have access, or competence/outcomes are established. Do not publish a new exact Vels score from this contract.

## 8. Review and integration sequence

### Independent workstream

1. Use this contract and T01–T18 to draft advisory/report fixtures with no live institutional rescore.
2. Review the 216-condition methodology matrix, beginning with the focused examples in section 4. Keep all candidate arithmetic isolated from active scoring.
3. Have a colleague unfamiliar with internal metrics read sample reports. They should identify the first action, its reason, a suggested owner and completion evidence without decoding variables.
4. Check repeat-run substance: supported facts, scope, grouping and priority rationale should remain consistent; prose need not be byte-identical. A citation's existence is not proof it entails the claim.

Release-blocking substantive failures include fabricated institutional facts, scope/date inflation, unsupported absence claims, advice that assumes unknown resources, hidden unresolved questions, and mismatched assessment/advisory snapshots. This is product QA, not an end-user consultant gate.

### Integration after the engineer's update

1. Map actual fact/resolution/declaration records to section 2. Confirm ownership before editing overlapping services.
2. Establish the deployed API/worker revisions and apply/review PR #3 independently.
3. Reconcile a fresh full-folder import and freeze one usable corpus. Retain all exclusions and failures.
4. Run old and candidate methodologies on the same corpus and explain each changed decision. Do not activate a revised rubric by silently replacing its JSON file.
5. Connect reviewed evidence to evaluation, then connect initiative generation and the report view model to that same assessment.
6. Verify user-flow and acceptance cases end to end, including failed/retried advisory calls and read-only exports.

### Remaining decisions, stated rather than guessed

- Final meaning and weighting of the headline score and its components.
- Adoption/outcome criteria, granularity of partial credit, applicability rules and tier thresholds.
- Which authorised declaration types can satisfy which criteria.
- Actual integration ownership and record/API shapes.
- Current production state and repaired full-corpus results.

The first three need methodology review and representative examples; the last two need engineering evidence. None prevents the fixture, advisory-policy and report-design work defined here.

### References

- Attached *AI_READY_Product_Diagnosis_and_Report_Prototype(1).pdf*, especially pages 3–8 and 13. Read locally in this session.
- [A1 source checkpoint](https://github.com/jagadesh-alpha8/AI-READY/tree/d468458410b438282efe1796905392c9d19cff05).
- [PR #3](https://github.com/jagadesh-alpha8/AI-READY/pull/3).
- [Rubric revision proposal](https://github.com/jagadesh-alpha8/AI-READY/blob/cf79c107448ea378fbfc24123f69c8c3985cb982/docs/capability/NAAC_RUBRIC_REVISION_DRAFT.md).
- [Engine](https://github.com/jagadesh-alpha8/AI-READY/blob/d468458410b438282efe1796905392c9d19cff05/backend/apps/scoring/capability/engine.py), [snapshot storage](https://github.com/jagadesh-alpha8/AI-READY/blob/d468458410b438282efe1796905392c9d19cff05/backend/apps/scoring/capability/storage.py), [recommendation inputs and validation](https://github.com/jagadesh-alpha8/AI-READY/blob/d468458410b438282efe1796905392c9d19cff05/backend/apps/scoring/capability/recommendations.py).
